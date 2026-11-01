"""桌面浮窗：顶置、无边框、可拖动、显示播放信息 + 快捷按键"""

import customtkinter as ctk


class FloatWindow(ctk.CTkToplevel):
    """浮窗控制器。需要外部传入一组回调：

    on_play_pause  : 播放/暂停切换
    on_stop        : 停止
    on_prev        : 上一首
    on_next        : 下一首
    on_close       : 关闭浮窗
    get_state      : () -> dict(title, mode, playing, paused, pos_ms, dur_ms, next_title)
    """

    def __init__(self, master, on_play_pause, on_stop, on_prev, on_next,
                 on_close, get_state):
        super().__init__(master)
        self._on_play_pause = on_play_pause
        self._on_stop = on_stop
        self._on_prev = on_prev
        self._on_next = on_next
        self._on_close = on_close
        self._get_state = get_state

        self._drag_x = 0
        self._drag_y = 0

        self.title("浮窗")
        self.overrideredirect(True)          # 无边框
        self.attributes("-topmost", True)    # 顶置
        try:
            self.attributes("-alpha", 0.92)  # 半透明
        except Exception:
            pass
        self.geometry("320x128+40+40")
        self.configure(fg_color="#1e1e1e")

        self._build()
        self._poll()

    # ---------- UI ----------
    def _build(self):
        # 顶部：标题 + 关闭
        top = ctk.CTkFrame(self, fg_color="transparent")
        top.pack(fill="x", padx=8, pady=(6, 0))

        self.title_label = ctk.CTkLabel(
            top, text="未播放", anchor="w",
            font=ctk.CTkFont(size=13, weight="bold"),
        )
        self.title_label.pack(side="left", fill="x", expand=True)

        self.mode_label = ctk.CTkLabel(
            top, text="", text_color="#9aa0a6",
            font=ctk.CTkFont(size=11),
        )
        self.mode_label.pack(side="left", padx=(0, 6))

        close_btn = ctk.CTkButton(
            top, text="✕", width=22, height=22, corner_radius=4,
            fg_color="transparent", hover_color="#b23a3a",
            text_color="#cccccc", command=self._on_close,
        )
        close_btn.pack(side="right")

        # 进度条（细线）
        self.progress = ctk.CTkProgressBar(
            self, height=6, corner_radius=3,
            progress_color="#2f5fa8", fg_color="#333333",
        )
        self.progress.pack(fill="x", padx=8, pady=(4, 2))
        self.progress.set(0)

        # 时间
        self.time_label = ctk.CTkLabel(
            self, text="00:00 / 00:00", anchor="w",
            text_color="#9aa0a6", font=ctk.CTkFont(size=11),
        )
        self.time_label.pack(fill="x", padx=8)

        # 下一首
        self.next_label = ctk.CTkLabel(
            self, text="下一首：—", anchor="w",
            text_color="#7fa8d8", font=ctk.CTkFont(size=11),
        )
        self.next_label.pack(fill="x", padx=8, pady=(0, 2))

        # 控制按钮
        bar = ctk.CTkFrame(self, fg_color="transparent")
        bar.pack(fill="x", padx=6, pady=(4, 6))

        btn_style = {"width": 52, "height": 28, "corner_radius": 6,
                     "font": ctk.CTkFont(size=12)}

        ctk.CTkButton(bar, text="⏮", command=self._on_prev,
                      **btn_style).pack(side="left", padx=3)
        self.play_btn = ctk.CTkButton(bar, text="▶", command=self._on_play_pause,
                                      **btn_style)
        self.play_btn.pack(side="left", padx=3)
        ctk.CTkButton(bar, text="■", command=self._on_stop,
                      fg_color="#b23a3a", hover_color="#8f2f2f",
                      **btn_style).pack(side="left", padx=3)
        ctk.CTkButton(bar, text="⏭", command=self._on_next,
                      **btn_style).pack(side="left", padx=3)

        # 拖动绑定
        for w in (self, top, self.title_label, self.mode_label,
                  self.time_label, self.next_label, bar):
            w.bind("<ButtonPress-1>", self._on_drag_start)
            w.bind("<B1-Motion>", self._on_drag_move)

    # ---------- 拖动 ----------
    def _on_drag_start(self, e):
        self._drag_x = e.x_root - self.winfo_x()
        self._drag_y = e.y_root - self.winfo_y()

    def _on_drag_move(self, e):
        x = e.x_root - self._drag_x
        y = e.y_root - self._drag_y
        self.geometry(f"+{x}+{y}")

    # ---------- 状态刷新 ----------
    def _fmt(self, ms):
        s = int(ms / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"

    def _poll(self):
        try:
            state = self._get_state()
            title = state.get("title") or "未播放"
            mode = state.get("mode") or ""
            playing = state.get("playing", False)
            paused = state.get("paused", False)
            pos = state.get("pos_ms", 0.0)
            dur = state.get("dur_ms", 0.0)
            next_title = state.get("next_title", "—")

            self.title_label.configure(text=title)
            self.mode_label.configure(text=f"（{mode}）" if mode else "")

            if playing and paused:
                self.play_btn.configure(text="⏵")
            else:
                self.play_btn.configure(text="⏸" if playing else "▶")

            self.time_label.configure(text=f"{self._fmt(pos)} / {self._fmt(dur)}")
            self.progress.set((pos / dur) if dur > 0 else 0)

            self.next_label.configure(text=f"下一首：{next_title}")
        except Exception:
            pass
        self.after(200, self._poll)