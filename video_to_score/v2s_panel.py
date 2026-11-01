"""视频转谱工具（集成在主框架中的 Frame 版本，支持多种键位布局与鼠标微调）"""

import os
import sys
import threading
import tkinter as tk
from tkinter import filedialog, messagebox

import cv2
import customtkinter as ctk
from PIL import Image, ImageTk

try:
    from . import video_utils as VU
    from . import state_detector as SD
    from . import event_builder as EB
except ImportError:
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import video_utils as VU
    import state_detector as SD
    import event_builder as EB

# 预设键位布局
KEY_PRESETS = {
    "21键 (3排)": ["q", "w", "e", "r", "t", "y", "u",
                   "a", "s", "d", "f", "g", "h", "j",
                   "z", "x", "c", "v", "b", "n", "m"],
    "14键 (2排)": ["q", "w", "e", "r", "t", "y", "u",
                   "a", "s", "d", "f", "g", "h", "j"],
    "4键":       ["q", "w", "e", "r"],
}

CALIB_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "calibrations")
DEFAULT_CALIB_FILES = {
    "21键 (3排)": "21键标定.json",
    "14键 (2排)": "14键标定.json",
}


class VideoTestApp(ctk.CTkFrame):
    def __init__(self, master):
        super().__init__(master)

        self.video_path = None
        self.frame = None
        self.fps = 30.0
        self.points = {}
        self._base_points = {}   # 用于微调重置的基准
        self.radius = 12
        self.detector = None
        self.events = None
        self._scanning = False

        # 视频播放状态
        self.cap = None
        self.total_frames = 0
        self.current_frame = 0
        self.is_playing = False
        self.preview_mode = False
        self._update_job = None
        self._drag_slider = False
        self._last_display_frame = None

        # 标定状态
        self.is_calibrating = False
        self.calib_idx = 0
        self._render_scale = 1.0
        self._render_offx = 0
        self._render_offy = 0
        self._canvas_photo = None

        # 拖拽/缩放状态
        self._drag_mode = None      # None | "whole" | "single"
        self._drag_key = None
        self._drag_start_x = 0
        self._drag_start_y = 0
        self._drag_start_points = {}
        self._drag_moved = False

        # 动态键位
        self.current_keys = KEY_PRESETS["21键 (3排)"]
        self.key_layout_var = ctk.StringVar(value="21键 (3排)")

        self.single_frame_var = ctk.BooleanVar(value=False)
        self.start_var = ctk.StringVar(value="0")
        self.end_var = ctk.StringVar(value="")
        self.preview_mode_var = ctk.BooleanVar(value=False)

        self._build()

    def _build(self):
        # ====== 顶部控制栏 ======
        top_frame = ctk.CTkFrame(self, fg_color="transparent")
        top_frame.pack(fill="x", padx=4, pady=(4, 4))

        ctk.CTkButton(top_frame, text="选择视频", width=90, command=self.pick_video).pack(side="left", padx=4)
        self.path_label = ctk.CTkLabel(top_frame, text="未选择视频", anchor="w")
        self.path_label.pack(side="left", fill="x", expand=True, padx=8)

        self.calib_btn = ctk.CTkButton(top_frame, text="手动标定 21 键", width=110, command=self._start_calibration)
        self.calib_btn.pack(side="right", padx=4)
        ctk.CTkButton(top_frame, text="清空标定", width=80, command=self._clear_calibration).pack(side="right", padx=4)
        ctk.CTkButton(top_frame, text="重置标定", width=80, command=self._reset_calib).pack(side="right", padx=4)
        ctk.CTkButton(top_frame, text="载入标定", width=80, command=self.load_calib).pack(side="right", padx=4)
        ctk.CTkButton(top_frame, text="保存标定", width=80, command=self.save_calib).pack(side="right", padx=4)

        ctk.CTkLabel(top_frame, text="乐器键位:").pack(side="right", padx=(15, 2))
        ctk.CTkOptionMenu(
            top_frame, values=list(KEY_PRESETS.keys()), variable=self.key_layout_var,
            command=self._on_layout_change, width=110
        ).pack(side="right", padx=4)

        # ====== 中间主体区域 ======
        body = ctk.CTkFrame(self, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=4, pady=4)

        # ====== 左侧：视频显示区 ======
        video_panel = ctk.CTkFrame(body)
        video_panel.pack(side="left", fill="both", expand=True, padx=(0, 10))

        self.canvas = tk.Canvas(video_panel, bg="black", highlightthickness=0)
        self.canvas.pack(fill="both", expand=True, padx=4, pady=(4, 2))
        self.canvas.bind("<Configure>", self._on_video_resize)
        # 绑定新的鼠标事件
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_press)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<ButtonPress-3>", self._on_canvas_press)
        self.canvas.bind("<B3-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-3>", self._on_canvas_release)
        self.canvas.bind("<MouseWheel>", self._on_canvas_wheel)
        self.canvas.bind("<Button-4>", lambda e: self._on_canvas_wheel(e, force_zoom=1))
        self.canvas.bind("<Button-5>", lambda e: self._on_canvas_wheel(e, force_zoom=-1))

        ctrl_row = ctk.CTkFrame(video_panel, fg_color="transparent")
        ctrl_row.pack(fill="x", padx=4, pady=(2, 2))

        self.play_btn = ctk.CTkButton(ctrl_row, text="▶ 播放", width=70, command=self._toggle_play)
        self.play_btn.pack(side="left", padx=(0, 10))

        self.video_slider = ctk.CTkSlider(ctrl_row, from_=0, to=1000, command=self._on_slider_drag)
        self.video_slider.pack(side="left", fill="x", expand=True, padx=5)
        self.video_slider.bind("<ButtonPress-1>", self._on_slider_press)
        self.video_slider.bind("<ButtonRelease-1>", self._on_slider_release)
        self.video_slider.set(0)

        self.time_label = ctk.CTkLabel(ctrl_row, text="00:00 / 00:00", width=100)
        self.time_label.pack(side="left", padx=(10, 0))

        # --- 鼠标操作提示 ---
        hint_frame = ctk.CTkFrame(video_panel, fg_color="transparent")
        hint_frame.pack(fill="x", padx=4, pady=(0, 4))
        ctk.CTkLabel(
            hint_frame,
            text="操作提示: 左/右键拖拽画布=平移整体 | 拖拽单个圆圈=微调单点 | 滚轮=缩放 (Shift=横向, Ctrl=纵向)",
            text_color="#777777", font=ctk.CTkFont(size=11)
        ).pack(side="left")

        # ====== 右侧：控制面板 ======
        ctrl_panel = ctk.CTkFrame(body, width=320)
        ctrl_panel.pack(side="left", fill="y")
        ctrl_panel.pack_propagate(False)

        ctk.CTkLabel(ctrl_panel, text="参数设置", font=ctk.CTkFont(weight="bold")).pack(anchor="w", padx=10, pady=(10, 6))

        # 范围
        row_range = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        row_range.pack(fill="x", padx=10, pady=2)
        ctk.CTkLabel(row_range, text="范围(s):").pack(side="left")
        ctk.CTkEntry(row_range, textvariable=self.start_var, width=50).pack(side="left", padx=2)
        ctk.CTkLabel(row_range, text="-").pack(side="left")
        ctk.CTkEntry(row_range, textvariable=self.end_var, width=50).pack(side="left", padx=2)
        ctk.CTkButton(row_range, text="S", width=25, command=lambda: self._set_time('start')).pack(side="left", padx=(5, 2))
        ctk.CTkButton(row_range, text="E", width=25, command=lambda: self._set_time('end')).pack(side="left")

        # 基线
        row_base = ctk.CTkFrame(ctrl_panel, fg_color="transparent")
        row_base.pack(fill="x", padx=10, pady=6)
        ctk.CTkLabel(row_base, text="基线时长(s):").pack(side="left")
        self.baseline_var = ctk.StringVar(value="0.5")
        ctk.CTkEntry(row_base, textvariable=self.baseline_var, width=50).pack(side="left", padx=5)
        ctk.CTkButton(row_base, text="采集", width=50, command=self.capture_baseline).pack(side="right")

        # 灵敏度
        ctk.CTkLabel(ctrl_panel, text="识别灵敏度:").pack(anchor="w", padx=10, pady=(10, 0))
        self.sens_var = ctk.DoubleVar(value=0.5)
        ctk.CTkSlider(ctrl_panel, from_=0.0, to=1.0, variable=self.sens_var, command=self._on_sens).pack(fill="x", padx=10, pady=4)

        # 模式开关
        ctk.CTkCheckBox(ctrl_panel, text="单帧判定(无防抖)",
                        variable=self.single_frame_var,
                        command=self._on_debounce_change).pack(anchor="w", padx=10, pady=6)
        ctk.CTkCheckBox(ctrl_panel, text="开启红绿圈预览模式",
                        variable=self.preview_mode_var,
                        command=self._toggle_preview_mode).pack(anchor="w", padx=10, pady=6)

        # 扫描按钮
        ctk.CTkButton(ctrl_panel, text="开始扫描", height=40,
                      fg_color="#3a6e3a", hover_color="#2f5a2f",
                      command=self.scan).pack(fill="x", padx=10, pady=(15, 5))
        ctk.CTkButton(ctrl_panel, text="导出谱子 .txt", height=40,
                      command=self.export).pack(fill="x", padx=10, pady=5)

        # 状态标签
        self.status = ctk.StringVar(value="就绪")
        ctk.CTkLabel(ctrl_panel, textvariable=self.status,
                     text_color="#9aa0a6", wraplength=300).pack(fill="x", padx=10, pady=5)

        # 识别结果文本框
        ctk.CTkLabel(ctrl_panel, text="识别结果:",
                     font=ctk.CTkFont(size=12, weight="bold")).pack(anchor="w", padx=10, pady=(5, 0))
        self.text = ctk.CTkTextbox(ctrl_panel, font=ctk.CTkFont(size=12), wrap="word")
        self.text.pack(fill="both", expand=True, padx=10, pady=(5, 10))

        # 快捷键
        self.bind("<KeyPress-s>", lambda e: self._set_time('start'))
        self.bind("<KeyPress-S>", lambda e: self._set_time('start'))
        self.bind("<KeyPress-e>", lambda e: self._set_time('end'))
        self.bind("<KeyPress-E>", lambda e: self._set_time('end'))
        self.bind("<space>", lambda e: self._toggle_play())
        self.bind("<Left>", lambda e: self._seek_relative(-1))
        self.bind("<Right>", lambda e: self._seek_relative(1))

    # ============================================================
    # 鼠标拖动与缩放
    # ============================================================
    def _canvas_to_orig(self, cx, cy):
        """画布坐标转原图坐标"""
        if self._render_scale <= 0:
            return 0, 0
        ox = (cx - self._render_offx) / self._render_scale
        oy = (cy - self._render_offy) / self._render_scale
        return ox, oy

    def _on_canvas_press(self, event):
        if self.is_calibrating:
            self._on_video_click(event)
            return

        if not self.points or not self.cap:
            return

        self._drag_start_x = event.x
        self._drag_start_y = event.y
        self._drag_start_points = dict(self.points)
        self._drag_moved = False

        if event.num == 1:
            # 检查是否点中了某个点
            closest_key = None
            min_dist = 20
            for k, (px, py) in self.points.items():
                cx = px * self._render_scale + self._render_offx
                cy = py * self._render_scale + self._render_offy
                dist = ((event.x - cx) ** 2 + (event.y - cy) ** 2) ** 0.5
                if dist < min_dist:
                    min_dist = dist
                    closest_key = k
            if closest_key:
                self._drag_mode = "single"
                self._drag_key = closest_key
                return

        # 整体拖拽
        self._drag_mode = "whole"
        self._drag_key = None

    def _on_canvas_drag(self, event):
        if self._drag_mode is None:
            return

        self._drag_moved = True

        dx = (event.x - self._drag_start_x) / self._render_scale
        dy = (event.y - self._drag_start_y) / self._render_scale

        w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        if self._drag_mode == "whole":
            for k, (px, py) in self._drag_start_points.items():
                nx = max(0, min(w, int(round(px + dx))))
                ny = max(0, min(h, int(round(py + dy))))
                self.points[k] = (nx, ny)
        elif self._drag_mode == "single":
            px, py = self._drag_start_points[self._drag_key]
            nx = max(0, min(w, int(round(px + dx))))
            ny = max(0, min(h, int(round(py + dy))))
            self.points[self._drag_key] = (nx, ny)

        if self._last_display_frame is not None:
            self._render_frame(self._last_display_frame)

    def _on_canvas_release(self, event):
        if self._drag_mode is None:
            return
        self._drag_mode = None
        if self._drag_moved:
            if self.detector:
                self.detector.baseline = {}
            self.status.set("标定位置已调整，请重新采集基线。")

    def _on_canvas_wheel(self, event, force_zoom=None):
        if not self.points or not self.cap:
            return

        if force_zoom is not None:
            zoom_in = (force_zoom > 0)
        else:
            zoom_in = (event.delta > 0)

        factor = 1.05 if zoom_in else 0.95

        ox, oy = self._canvas_to_orig(event.x, event.y)

        state = event.state
        shift = (state & 0x0001) != 0
        ctrl = (state & 0x0004) != 0

        fx = factor if (not shift and not ctrl) or shift else 1.0
        fy = factor if (not shift and not ctrl) or ctrl else 1.0

        w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

        new_pts = {}
        for k, (x, y) in self.points.items():
            nx = ox + (x - ox) * fx
            ny = oy + (y - oy) * fy
            new_pts[k] = (max(0, min(w, int(round(nx)))), max(0, min(h, int(round(ny)))))

        self.points = new_pts

        if self.detector:
            self.detector.baseline = {}

        self.status.set("已缩放标定，请重新采集基线。")
        if self._last_display_frame is not None:
            self._render_frame(self._last_display_frame)

    # ============================================================
    # 标定其他逻辑
    # ============================================================
    def _snapshot_base_points(self):
        self._base_points = dict(self.points)

    def _reset_calib(self):
        if not self._base_points:
            self.status.set("无可重置的基准标定")
            return
        self.points = dict(self._base_points)
        self._ensure_detector(keep_baseline=False)
        self._seek_to_frame(self.current_frame)
        self.status.set("已重置为初始标定位置")

    def _on_layout_change(self, choice):
        self.current_keys = KEY_PRESETS[choice]
        self._clear_calibration()
        if self.cap and self._try_load_default_calib():
            return
        self.status.set(f"已切换为 {choice}，请重新标定。")

    def _try_load_default_calib(self):
        if not self.cap:
            return False
        layout = self.key_layout_var.get()
        fname = DEFAULT_CALIB_FILES.get(layout)
        if not fname:
            return False
        path = os.path.join(CALIB_DIR, fname)
        if not os.path.exists(path):
            return False
        try:
            import json
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            pts = {}
            for k, v in data.get("keys", {}).items():
                x, y = v[0], v[1]
                if x > 1.0 or y > 1.0:
                    pts[k] = (int(x), int(y))
                else:
                    pts[k] = (int(x * w), int(y * h))
            if pts:
                self.points = pts
                self._snapshot_base_points()
                self._ensure_detector()
                num_keys = len(pts)
                self.calib_btn.configure(text=f"重新标定 {num_keys} 键")
                self.status.set(f"已自动载入默认标定：{num_keys} 键")
                self._seek_to_frame(self.current_frame)
                return True
        except Exception as e:
            print(f"载入默认标定失败: {e}")
        return False

    # ---------- 视频加载与播放控制 ----------
    def pick_video(self):
        p = filedialog.askopenfilename(
            title="选择弹奏视频",
            filetypes=[("视频", "*.mp4 *.avi *.mov *.mkv *.flv"), ("所有文件", "*.*")]
        )
        if not p:
            return
        self.video_path = p
        self.path_label.configure(text=os.path.basename(p))
        self.status.set("已选择视频，正在加载...")

        if self.cap:
            self.cap.release()

        self.cap = cv2.VideoCapture(self.video_path)
        self.fps = self.cap.get(cv2.CAP_PROP_FPS) or 30.0
        self.total_frames = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.current_frame = 0
        self.points = {}
        self._base_points = {}
        self.detector = None

        self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
        ok, frame = self.cap.read()
        if ok:
            self.frame = frame
            self._render_frame(frame)
        self.status.set(f"视频加载完成 fps:{self.fps:.1f} 总帧数:{self.total_frames}")
        self._update_time_label()

        self._try_load_default_calib()

    def _toggle_play(self):
        if not self.cap:
            return
        self.is_playing = not self.is_playing
        if self.is_playing:
            self.play_btn.configure(text="⏸ 暂停")
            if self.current_frame >= self.total_frames - 1:
                self.current_frame = 0
            self._update_loop()
        else:
            self.play_btn.configure(text="▶ 播放")
            if self._update_job:
                self.after_cancel(self._update_job)
                self._update_job = None

    def _update_loop(self):
        if not self.is_playing or not self.cap:
            return

        if not self._drag_slider:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
            ok, frame = self.cap.read()
            if ok:
                self.frame = frame
                self._render_frame(frame)
                self.current_frame += 1
                self._update_time_label()
                self.video_slider.set(int((self.current_frame / self.total_frames) * 1000))
            else:
                self.is_playing = False
                self.play_btn.configure(text="▶ 播放")
                return

        self._update_job = self.after(max(1, int(1000 / self.fps)), self._update_loop)

    def _on_video_resize(self, event):
        if self._last_display_frame is not None:
            self._render_frame(self._last_display_frame)

    def _render_frame(self, frame_bgr):
        self._last_display_frame = frame_bgr.copy()

        pressed = set()
        if self.preview_mode and self.detector and self.detector.baseline:
            pressed = self.detector.update(frame_bgr)

        label_w = self.canvas.winfo_width()
        label_h = self.canvas.winfo_height()
        if label_w < 10 or label_h < 10:
            label_w, label_h = 960, 540

        h, w = frame_bgr.shape[:2]
        scale = min(label_w / w, label_h / h)
        new_w, new_h = int(w * scale), int(h * scale)

        self._render_scale = scale
        self._render_offx = (label_w - new_w) // 2
        self._render_offy = (label_h - new_h) // 2

        resized = cv2.resize(frame_bgr, (new_w, new_h), interpolation=cv2.INTER_AREA)
        frame_rgb = cv2.cvtColor(resized, cv2.COLOR_BGR2RGB)

        img = Image.fromarray(frame_rgb)
        photo = ImageTk.PhotoImage(image=img)

        self.canvas.delete("all")
        self.canvas.create_image(self._render_offx, self._render_offy, anchor="nw", image=photo)
        self._canvas_photo = photo

        if self.points:
            for k, (ox, oy) in self.points.items():
                cx = self._render_offx + ox * scale
                cy = self._render_offy + oy * scale

                is_pressed = k in pressed
                color = "red" if is_pressed else "lime"
                r = max(4, self.radius * scale)

                self.canvas.create_oval(cx - r, cy - r, cx + r, cy + r, outline=color, width=2)
                self.canvas.create_text(cx, cy, text=k, fill=color,
                                        font=("Arial", max(8, int(12 * scale)), "bold"))

    def _update_time_label(self):
        if not self.cap or self.total_frames == 0:
            return
        curr_s = self.current_frame / self.fps
        total_s = self.total_frames / self.fps
        self.time_label.configure(text=f"{self._fmt(curr_s)} / {self._fmt(total_s)}")

    def _fmt(self, sec):
        m = int(sec // 60)
        s = int(sec % 60)
        return f"{m:02d}:{s:02d}"

    def _seek_relative(self, seconds):
        if not self.cap:
            return
        target_f = self.current_frame + int(seconds * self.fps)
        target_f = max(0, min(target_f, self.total_frames - 1))
        self._seek_to_frame(target_f)

    def _seek_to_frame(self, f_idx):
        if not self.cap:
            return
        self.current_frame = f_idx
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ok, frame = self.cap.read()
        if ok:
            self.frame = frame
            self._render_frame(frame)
            self.video_slider.set(int((self.current_frame / self.total_frames) * 1000))
            self._update_time_label()

    # ---------- 进度条拖拽 ----------
    def _on_slider_press(self, _ev):
        self._drag_slider = True

    def _on_slider_drag(self, value):
        if not self.cap:
            return
        f_idx = int((float(value) / 1000.0) * self.total_frames)
        self.current_frame = max(0, min(f_idx, self.total_frames - 1))
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, self.current_frame)
        ok, frame = self.cap.read()
        if ok:
            self.frame = frame
            self._render_frame(frame)
            self._update_time_label()

    def _on_slider_release(self, _ev):
        self._drag_slider = False

    # ---------- 手动标定 ----------
    def _start_calibration(self):
        if not self.cap:
            messagebox.showwarning("提示", "请先选择视频")
            return
        if self.is_playing:
            self._toggle_play()
        self.is_calibrating = True
        self.calib_idx = 0
        self.points = {}
        self._base_points = {}
        self.detector = None
        
        num_keys = len(self.current_keys)
        self.calib_btn.configure(text=f"标定中: 0/{num_keys}", fg_color="#b23a3a")
        self.status.set(f"标定模式：请依次点击画面上的 {num_keys} 个琴键中心。")
        self._seek_to_frame(self.current_frame)

    def _clear_calibration(self):
        self.is_calibrating = False
        self.points = {}
        self._base_points = {}
        self.detector = None
        layout_name = self.key_layout_var.get()
        num_keys = len(KEY_PRESETS[layout_name])
        self.calib_btn.configure(text=f"手动标定 {num_keys} 键",
                                 fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
        self.status.set("标定已清空")
        self._seek_to_frame(self.current_frame)

    def _on_video_click(self, event):
        if not self.is_calibrating or self._last_display_frame is None:
            return
        if self._render_scale <= 0:
            return

        orig_x = (event.x - self._render_offx) / self._render_scale
        orig_y = (event.y - self._render_offy) / self._render_scale

        h, w = self._last_display_frame.shape[:2]
        if orig_x < 0 or orig_y < 0 or orig_x > w or orig_y > h:
            return

        key = self.current_keys[self.calib_idx]
        self.points[key] = (int(orig_x), int(orig_y))
        self.calib_idx += 1

        num_keys = len(self.current_keys)
        self.calib_btn.configure(text=f"标定中: {self.calib_idx}/{num_keys}")

        if self.calib_idx >= num_keys:
            self.is_calibrating = False
            self.calib_btn.configure(text=f"重新标定 {num_keys} 键",
                                     fg_color=ctk.ThemeManager.theme["CTkButton"]["fg_color"])
            self.status.set("标定完成！")
            self._snapshot_base_points()
            self._ensure_detector()

        self._seek_to_frame(self.current_frame)

    # ---------- 标定文件存取 ----------
    def load_calib(self):
        if not self.cap:
            messagebox.showwarning("提示", "请先选择视频以获取分辨率")
            return
        p = filedialog.askopenfilename(title="载入标定", filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            import json
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)

            w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)

            pts = {}
            for k, v in data.get("keys", {}).items():
                x, y = v[0], v[1]
                if x > 1.0 or y > 1.0:
                    pts[k] = (int(x), int(y))
                else:
                    pts[k] = (int(x * w), int(y * h))

            self.points = pts
            self._snapshot_base_points()
            self._ensure_detector()
            
            num_keys = len(self.points)
            self.calib_btn.configure(text=f"重新标定 {num_keys} 键")
            self.status.set(f"已载入标定：{num_keys} 键")
            self._seek_to_frame(self.current_frame)
        except Exception as e:
            messagebox.showerror("载入失败", str(e))

    def save_calib(self):
        if not self.points or not self.cap:
            messagebox.showwarning("提示", "无标定可保存或未加载视频")
            return
        p = filedialog.asksaveasfilename(title="保存标定", defaultextension=".json",
                                          filetypes=[("JSON", "*.json")])
        if not p:
            return
        try:
            import json
            w = self.cap.get(cv2.CAP_PROP_FRAME_WIDTH)
            h = self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
            ratio_keys = {k: [x / w, y / h] for k, (x, y) in self.points.items()}
            data = {"radius": self.radius, "keys": ratio_keys}
            with open(p, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.status.set(f"已保存标定：{p}")
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    # ---------- 识别逻辑 ----------
    def _set_time(self, mode):
        if not self.cap:
            return
        curr_s = self.current_frame / self.fps
        if mode == 'start':
            self.start_var.set(f"{curr_s:.2f}")
            self.status.set(f"设置起点: {curr_s:.2f}s")
        else:
            self.end_var.set(f"{curr_s:.2f}")
            self.status.set(f"设置终点: {curr_s:.2f}s")

    def _get_time_range(self):
        try:
            start = float(self.start_var.get())
        except ValueError:
            start = 0.0
        if start < 0:
            start = 0.0
        try:
            end_str = self.end_var.get().strip()
            end = float(end_str) if end_str else None
        except ValueError:
            end = None
        return start, end

    def _on_sens(self, _v=None):
        if self.detector:
            self.detector.sensitivity(float(self.sens_var.get()))

    def _on_debounce_change(self):
        if self.detector:
            db = 1 if self.single_frame_var.get() else 2
            self.detector.debounce_frames = db
            self.status.set(f"防抖已设为: {db} 帧")

    def _toggle_preview_mode(self):
        self.preview_mode = self.preview_mode_var.get()
        if self.preview_mode:
            self.status.set("已开启红绿圈预览。")
        else:
            self.status.set("已关闭预览。")
        self._seek_to_frame(self.current_frame)

    def _ensure_detector(self, keep_baseline=False):
        old_baseline = {}
        if keep_baseline and self.detector:
            old_baseline = dict(self.detector.baseline)

        db = 1 if self.single_frame_var.get() else 2
        self.detector = SD.StateDetector(self.points, self.radius, debounce_frames=db)
        self.detector.sensitivity(float(self.sens_var.get()))

        if old_baseline:
            self.detector.baseline = old_baseline

    def capture_baseline(self):
        if not self.video_path or not self.points:
            messagebox.showwarning("提示", "请先选择视频并标定琴键")
            return
        try:
            dur = float(self.baseline_var.get())
        except ValueError:
            messagebox.showerror("错误", "基线时长需为数字")
            return

        try:
            cap = cv2.VideoCapture(self.video_path)
            start_s, _ = self._get_time_range()
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            start_f = int(start_s * fps)
            cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)

            frames = []
            n = max(1, int(dur * fps))
            for _ in range(n):
                ok, fr = cap.read()
                if not ok:
                    break
                frames.append(fr)
            cap.release()
            if not frames:
                messagebox.showerror("基线采集失败", "读取不到任何帧")
                return
            self._ensure_detector()
            self.detector.capture_baseline(frames)
            self.status.set(f"基线采集完成（{len(frames)} 帧）")
        except Exception as e:
            messagebox.showerror("基线采集失败", str(e))

    def scan(self):
        if not self.video_path or not self.points or not self.detector or not self.detector.baseline:
            messagebox.showwarning("提示", "请先选择视频、标定琴键并采集基线")
            return
        if self._scanning:
            return
        if self.is_playing:
            self._toggle_play()

        self._scanning = True
        self.status.set("扫描中…")
        threading.Thread(target=self._scan_worker, daemon=True).start()

    def _scan_worker(self):
        try:
            cap = cv2.VideoCapture(self.video_path)
            start_s, end_s = self._get_time_range()
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0

            start_f = int(start_s * fps)
            end_f = int(end_s * fps) if end_s is not None else -1

            if start_f > 0:
                cap.set(cv2.CAP_PROP_POS_FRAMES, start_f)

            results = []
            idx = start_f
            while True:
                if end_f != -1 and idx >= end_f:
                    break
                ok, fr = cap.read()
                if not ok:
                    break
                pressed = self.detector.update(fr)
                results.append(pressed)
                idx += 1
                if idx % 30 == 0:
                    total_str = end_f if end_f != -1 else "?"
                    self.after(0, lambda i=idx, t=total_str:
                               self.status.set(f"扫描中… {i}/{t}"))
            cap.release()

            min_gap = 50 if self.single_frame_var.get() else 150
            events = EB.frames_to_events(results, self.fps, min_gap_ms=min_gap)

            self.events = events
            self.after(0, self._on_scan_done)
        except Exception as e:
            self.after(0, lambda err=e: messagebox.showerror("扫描失败", str(err)))
        finally:
            self._scanning = False

    def _on_scan_done(self):
        self.status.set(f"扫描完成：{len(self.events)} 个事件")
        self.text.delete("1.0", "end")
        self.text.insert("1.0", EB.events_to_text(self.events))

    def export(self):
        if not self.events:
            messagebox.showwarning("提示", "没有可导出的结果")
            return

        try:
            import score_repo
            init_dir = score_repo.SCORES_DIR
        except ImportError:
            init_dir = None

        p = filedialog.asksaveasfilename(
            title="导出谱子",
            initialdir=init_dir,
            defaultextension=".txt",
            filetypes=[("谱子", "*.txt")]
        )
        if not p:
            return
        try:
            tokens = EB.events_to_tokens(self.events)
            with open(p, "w", encoding="utf-8") as f:
                f.write("# 由视频转谱自动生成\n")
                for i in range(0, len(tokens), 8):
                    f.write(" ".join(tokens[i:i + 8]) + "\n")
            self.status.set(f"已导出：{p}")
        except Exception as e:
            messagebox.showerror("导出失败", str(e))

    def _on_close(self):
        if self.cap:
            self.cap.release()