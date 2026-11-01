import os
import random
import customtkinter as ctk
from tkinter import messagebox

import score_repo
import player
from float_window import FloatWindow
from playlist_dialog import PlaylistDialog
from video_to_score.v2s_panel import VideoTestApp


class App(ctk.CTk):
    def __init__(self):
        super().__init__()
        self.title("原神弹琴播放器")
        self.geometry("1100x760")
        self.minsize(960, 680)

        ctk.set_appearance_mode("dark")
        ctk.set_default_color_theme("blue")

        self.player = player.Player()
        self.player.on_finished = lambda: self.after(0, self._on_play_finished)

        self.current_file = None
        self.events = None
        self._files = []
        self._row_buttons = {}
        self._dirty = False
        self._playing_name = None
        self._playing_mode = None
        self._seeking = False

        self.playlist = []
        self._play_index = -1

        self._float_win = None
        self._playlist_dialog = None

        # 视图控制
        self.is_video_view = False
        self.video_view = None

        # 编辑器视图模式
        self._view_mode = "edit"
        self._lyric_events = []
        self._current_lyric_idx = -1

        self._build_ui()
        self.refresh_list()
        self._poll_status()

        self.protocol("WM_DELETE_WINDOW", self._on_close_app)

    def _build_ui(self):
        header = ctk.CTkFrame(self, corner_radius=0, fg_color="transparent")
        header.pack(fill="x", padx=20, pady=(16, 8))

        ctk.CTkLabel(
            header, text="原神弹琴播放器",
            font=ctk.CTkFont(size=22, weight="bold")
        ).pack(side="left")

        # ====== 视图切换按钮 ======
        view_frame = ctk.CTkFrame(header, fg_color="transparent")
        view_frame.pack(side="left", padx=30)

        self.view_btn_main = ctk.CTkButton(
            view_frame, text="本地乐谱", width=80, height=28,
            command=self.show_main_view,
            fg_color=["#3B8ED0", "#1F6AA5"],
        )
        self.view_btn_main.pack(side="left", padx=5)

        self.view_btn_video = ctk.CTkButton(
            view_frame, text="视频转谱", width=80, height=28,
            command=self.show_video_view,
            fg_color="#555555",
        )
        self.view_btn_video.pack(side="left", padx=5)

        # ====== 模式切换 ======
        self.mode_var = ctk.StringVar(value="keys")
        mode_frame = ctk.CTkFrame(header, fg_color="transparent")
        mode_frame.pack(side="right")
        for text, val in (("音频", "audio"), ("按键", "keys")):
            ctk.CTkRadioButton(
                mode_frame, text=text, variable=self.mode_var, value=val,
                radiobutton_width=16, radiobutton_height=16
            ).pack(side="left", padx=6)

        # ====== 主容器 ======
        self.main_container = ctk.CTkFrame(self, fg_color="transparent")
        self.main_container.pack(fill="both", expand=True)

        # ---------- 主体 ----------
        body = ctk.CTkFrame(self.main_container, fg_color="transparent")
        body.pack(fill="both", expand=True, padx=20, pady=8)
        body.grid_columnconfigure(0, weight=1)
        body.grid_columnconfigure(1, weight=2)
        body.grid_rowconfigure(0, weight=1)

        # --- 左侧列表 ---
        left = ctk.CTkFrame(body, corner_radius=12)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 8))

        search_frame = ctk.CTkFrame(left, fg_color="transparent")
        search_frame.pack(fill="x", padx=10, pady=(10, 4))

        self.search_var = ctk.StringVar()
        self.search_var.trace_add("write", lambda *_: self.refresh_list())
        ctk.CTkEntry(
            search_frame, textvariable=self.search_var,
            placeholder_text="搜索谱子…"
        ).pack(side="left", fill="x", expand=True)
        ctk.CTkButton(
            search_frame, text="刷新", width=60, command=self.refresh_list
        ).pack(side="left", padx=(6, 0))

        self.list_container = ctk.CTkScrollableFrame(
            left, corner_radius=8, fg_color="transparent"
        )
        self.list_container.pack(fill="both", expand=True, padx=10, pady=10)

        # --- 右侧编辑器 ---
        right = ctk.CTkFrame(body, corner_radius=12)
        right.grid(row=0, column=1, sticky="nsew", padx=(8, 0))

        edit_header = ctk.CTkFrame(right, fg_color="transparent")
        edit_header.pack(fill="x", padx=12, pady=(10, 4))

        self.file_label = ctk.CTkLabel(
            edit_header, text="未选择乐谱",
            font=ctk.CTkFont(size=14, weight="bold")
        )
        self.file_label.pack(side="left")

        self.dirty_label = ctk.CTkLabel(
            edit_header, text="", text_color="#e0a030",
            font=ctk.CTkFont(size=12)
        )
        self.dirty_label.pack(side="left", padx=8)

        self.view_btn = ctk.CTkButton(
            edit_header, text="歌词模式", width=70, height=28, corner_radius=6,
            command=self._toggle_view_mode
        )
        self.view_btn.pack(side="right", padx=6)

        ctk.CTkButton(
            edit_header, text="重命名", width=70, height=28, corner_radius=6,
            command=self.rename_current
        ).pack(side="right")

        self.editor = ctk.CTkTextbox(
            right, corner_radius=8, font=ctk.CTkFont(size=13),
            wrap="word"
        )
        self.editor.pack(fill="both", expand=True, padx=12, pady=6)
        self.editor.bind("<KeyRelease>", self._mark_dirty)

        self.lyric_view = ctk.CTkTextbox(
            right, corner_radius=8, font=ctk.CTkFont(size=13),
            wrap="word"
        )
        self.lyric_view._textbox.tag_config("current", background="#2f5fa8", foreground="#ffffff")

        action = ctk.CTkFrame(right, fg_color="transparent")
        action.pack(fill="x", padx=12, pady=(4, 12))

        btn_style = {"width": 90, "height": 32, "corner_radius": 8}
        ctk.CTkButton(action, text="保存", command=self.save_current, **btn_style).pack(side="left", padx=4)
        ctk.CTkButton(action, text="另存为", command=self.save_as, **btn_style).pack(side="left", padx=4)
        ctk.CTkButton(action, text="新建", command=self.new_score, **btn_style).pack(side="left", padx=4)
        ctk.CTkButton(action, text="删除", command=self.delete_current,
                      fg_color="#b23a3a", hover_color="#8f2f2f", **btn_style).pack(side="left", padx=4)

        # --- 播放列表 ---
        playlist_frame = ctk.CTkFrame(self.main_container, corner_radius=12)
        playlist_frame.pack(fill="x", padx=20, pady=(0, 8))

        ctk.CTkLabel(playlist_frame, text="播放列表", font=ctk.CTkFont(size=13, weight="bold")).pack(
            side="left", padx=(12, 8), pady=10
        )
        self.playlist_label = ctk.CTkLabel(
            playlist_frame, text="0 首", font=ctk.CTkFont(size=12), text_color="#9aa0a6"
        )
        self.playlist_label.pack(side="left", padx=6, pady=10)

        ctk.CTkButton(
            playlist_frame, text="加入当前", width=90, height=30, corner_radius=6,
            command=self.add_current_to_playlist
        ).pack(side="left", padx=4, pady=10)
        ctk.CTkButton(
            playlist_frame, text="加入全部", width=90, height=30, corner_radius=6,
            command=self.add_all_to_playlist
        ).pack(side="left", padx=4, pady=10)
        ctk.CTkButton(
            playlist_frame, text="查看", width=70, height=30, corner_radius=6,
            fg_color="#3a6e3a", hover_color="#2f5a2f",
            command=self.open_playlist_dialog
        ).pack(side="left", padx=4, pady=10)
        ctk.CTkButton(
            playlist_frame, text="清空", width=70, height=30, corner_radius=6,
            fg_color="#555555", hover_color="#444444",
            command=self.clear_playlist
        ).pack(side="left", padx=4, pady=10)

        self.loop_var = ctk.StringVar(value="sequential")
        loop_frame = ctk.CTkFrame(playlist_frame, fg_color="transparent")
        loop_frame.pack(side="right", padx=(0, 12))
        for text, val in (("顺序", "sequential"), ("单曲循环", "repeat_one"), ("随机", "shuffle")):
            ctk.CTkRadioButton(
                loop_frame, text=text, variable=self.loop_var, value=val,
                radiobutton_width=16, radiobutton_height=16
            ).pack(side="left", padx=6)

        # --- 进度条 ---
        progress_frame = ctk.CTkFrame(self.main_container, corner_radius=12)
        progress_frame.pack(fill="x", padx=20, pady=(0, 8))

        self.time_label = ctk.CTkLabel(
            progress_frame, text="00:00 / 00:00",
            font=ctk.CTkFont(size=12), width=110
        )
        self.time_label.pack(side="left", padx=(12, 6), pady=10)

        self.progress = ctk.CTkSlider(
            progress_frame, from_=0, to=1000, command=self._on_seek_drag,
            button_corner_radius=8, height=18
        )
        self.progress.pack(side="left", fill="x", expand=True, padx=6, pady=10)
        self.progress.bind("<ButtonPress-1>", self._on_seek_start)
        self.progress.bind("<ButtonRelease-1>", self._on_seek_commit)
        self.progress.set(0)

        self.pos_label = ctk.CTkLabel(
            progress_frame, text="就绪",
            font=ctk.CTkFont(size=12), text_color="#9aa0a6", width=160
        )
        self.pos_label.pack(side="left", padx=(6, 12), pady=10)

        # --- 播放控制栏 ---
        controls = ctk.CTkFrame(self.main_container, corner_radius=12)
        controls.pack(fill="x", padx=20, pady=(0, 16))

        play_style = {"width": 120, "height": 34, "corner_radius": 8}
        ctk.CTkButton(controls, text="加载", command=self.load_selected, **play_style).pack(side="left", padx=8, pady=12)
        ctk.CTkButton(controls, text="开始 (F8)", command=self.start, **play_style).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(controls, text="暂停/继续 (F9)", command=self.toggle_pause,
                      **play_style).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(controls, text="停止 (Esc)", command=self.stop,
                      fg_color="#b23a3a", hover_color="#8f2f2f", **play_style).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(controls, text="上一首", command=self.prev_track,
                      fg_color="#555555", hover_color="#444444", **play_style).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(controls, text="下一首", command=self.next_track,
                      fg_color="#555555", hover_color="#444444", **play_style).pack(side="left", padx=4, pady=12)
        ctk.CTkButton(controls, text="浮窗", command=self.toggle_float_window,
                      fg_color="#3a6e3a", hover_color="#2f5a2f",
                      **play_style).pack(side="left", padx=(16, 4), pady=12)

        # --- 底部状态栏 ---
        self.status_var = ctk.StringVar(value="就绪")
        ctk.CTkLabel(
            self.main_container, textvariable=self.status_var,
            font=ctk.CTkFont(size=12), text_color="#9aa0a6"
        ).pack(fill="x", padx=24, pady=(0, 12))

    # ====== 视图切换 ======
    def show_main_view(self):
        if self.is_video_view:
            if self.video_view:
                self.video_view.pack_forget()
            self.main_container.pack(fill="both", expand=True)
            self.is_video_view = False
            self.view_btn_main.configure(fg_color=["#3B8ED0", "#1F6AA5"])
            self.view_btn_video.configure(fg_color="#555555")

    def show_video_view(self):
        if not self.is_video_view:
            self.main_container.pack_forget()
            if self.video_view is None:
                self.video_view = VideoTestApp(self)
            self.video_view.pack(fill="both", expand=True, padx=12, pady=8)
            self.is_video_view = True
            self.view_btn_main.configure(fg_color="#555555")
            self.view_btn_video.configure(fg_color=["#3B8ED0", "#1F6AA5"])

    # ====== 歌词滚动逻辑 ======
    def _toggle_view_mode(self):
        if self._view_mode == "lyric":
            self._view_mode = "edit"
            self.view_btn.configure(text="歌词模式")
            self.lyric_view.pack_forget()
            self.editor.pack(fill="both", expand=True, padx=12, pady=6)
        else:
            self._view_mode = "lyric"
            self.view_btn.configure(text="编辑模式")
            self._build_lyrics()
            self.editor.pack_forget()
            self.lyric_view.pack(fill="both", expand=True, padx=12, pady=6)

    def _build_lyrics(self):
        content = self.editor.get("1.0", "end-1c")
        tokens = []
        for line in content.splitlines():
            line = line.split("#", 1)[0].strip()
            if line:
                tokens.extend(line.split())
        events = player.parse_events(tokens)
        self._lyric_events = events
        self._current_lyric_idx = -1

        self.lyric_view.configure(state="normal")
        self.lyric_view.delete("1.0", "end")
        for keys, dur, start in events:
            time_str = self._fmt_ms(start)
            key_str = "".join(keys) if keys else "..."
            self.lyric_view.insert("end", f"[{time_str}] {key_str}\n")
        self.lyric_view.configure(state="disabled")
        self._sync_lyric_to_pos()

    def _sync_lyric_to_pos(self):
        if not self._lyric_events:
            return
        pos = self.player.position_ms()
        idx = -1
        for i, (keys, dur, start) in enumerate(self._lyric_events):
            if start <= pos:
                idx = i
            else:
                break
        if idx != self._current_lyric_idx:
            self._current_lyric_idx = idx
            self._highlight_lyric(idx)

    def _highlight_lyric(self, idx):
        self.lyric_view._textbox.tag_remove("current", "1.0", "end")
        if 0 <= idx < len(self._lyric_events):
            line_start = f"{idx + 1}.0"
            line_end = f"{idx + 1}.end"
            self.lyric_view._textbox.tag_add("current", line_start, line_end)
            self.lyric_view._textbox.see(line_start)

    def _fmt_ms(self, ms):
        s = ms / 1000.0
        m = int(s // 60)
        sec = s % 60
        return f"{m:02d}:{sec:05.2f}"

    # ---------- 列表 ----------
    def refresh_list(self):
        keyword = self.search_var.get()
        self._files = score_repo.search_scores(keyword)

        for w in self.list_container.winfo_children():
            w.destroy()
        self._row_buttons.clear()

        for f in self._files:
            shown = score_repo.display_name(f)
            btn = ctk.CTkButton(
                self.list_container,
                text=shown,
                anchor="w",
                height=38,
                corner_radius=6,
                font=ctk.CTkFont(size=15),
                fg_color="transparent",
                hover_color="#2f3b52",
                text_color="#e6e6e6",
                command=lambda name=f: self._open_file(name),
            )
            btn.pack(fill="x", pady=3, padx=2)
            self._row_buttons[f] = btn

        if self.current_file in self._row_buttons:
            self._highlight(self.current_file)
        self.status_var.set(f"共 {len(self._files)} 个谱子")
        self._update_playlist_label()

    def _highlight(self, filename):
        for f, btn in self._row_buttons.items():
            if f == filename:
                btn.configure(fg_color="#2f5fa8", text_color="#ffffff")
            else:
                btn.configure(fg_color="transparent", text_color="#e6e6e6")

    def _open_file(self, filename):
        if self._dirty:
            if not messagebox.askyesno("未保存", "当前乐谱有未保存修改，切换将丢失。继续？"):
                return
        self.player.stop()
        self.current_file = filename
        self._highlight(filename)
        self.file_label.configure(text=score_repo.display_name(filename))
        self.dirty_label.configure(text="")
        self._dirty = False
        try:
            with open(score_repo.score_path(filename), "r", encoding="utf-8") as f:
                content = f.read()
        except Exception as e:
            messagebox.showerror("读取失败", str(e))
            return
        self.editor.delete("1.0", "end")
        self.editor.insert("1.0", content)
        self.events = None
        self.progress.set(0)
        self.time_label.configure(text="00:00 / 00:00")
        self.status_var.set(f"选中: {score_repo.display_name(filename)}")

        if self._view_mode == "lyric":
            self._build_lyrics()

    # ---------- 播放列表 ----------
    def _update_playlist_label(self):
        self.playlist_label.configure(text=f"{len(self.playlist)} 首")

    def add_current_to_playlist(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先选择一个谱子")
            return
        if self.current_file not in self.playlist:
            self.playlist.append(self.current_file)
            self._update_playlist_label()
            self.status_var.set(f"已加入播放列表: {score_repo.display_name(self.current_file)}")
            self._refresh_playlist_dialog()

    def add_all_to_playlist(self):
        added = 0
        for f in self._files:
            if f not in self.playlist:
                self.playlist.append(f)
                added += 1
        self._update_playlist_label()
        self.status_var.set(f"已加入 {added} 首到播放列表")
        self._refresh_playlist_dialog()

    def clear_playlist(self):
        if not self.playlist:
            return
        if not messagebox.askyesno("清空播放列表", "确定清空所有条目？"):
            return
        self.playlist.clear()
        self._play_index = -1
        self._update_playlist_label()
        self.status_var.set("播放列表已清空")
        self._refresh_playlist_dialog()

    def open_playlist_dialog(self):
        if self._playlist_dialog is not None and self._playlist_dialog.winfo_exists():
            self._playlist_dialog.lift()
            self._playlist_dialog.focus_force()
            return
        self._playlist_dialog = PlaylistDialog(
            self,
            playlist=self.playlist,
            on_changed=self._on_playlist_dialog_changed,
            on_play_index=self._play_playlist_index,
            display_name=score_repo.display_name,
        )

    def _refresh_playlist_dialog(self):
        if self._playlist_dialog is not None and self._playlist_dialog.winfo_exists():
            self._playlist_dialog._refresh()
            self._playlist_dialog.count_label.configure(text=f"{len(self.playlist)} 首")

    def _on_playlist_dialog_changed(self):
        self._update_playlist_label()
        if self._play_index >= len(self.playlist):
            self._play_index = -1

    def _current_playlist_file(self):
        if 0 <= self._play_index < len(self.playlist):
            return self.playlist[self._play_index]
        return None

    def _pick_next_index(self):
        if not self.playlist:
            return -1
        mode = self.loop_var.get()
        if mode == "repeat_one":
            return self._play_index if self._play_index >= 0 else 0
        if mode == "shuffle":
            if len(self.playlist) == 1:
                return 0
            choices = [i for i in range(len(self.playlist)) if i != self._play_index]
            return random.choice(choices)
        return (self._play_index + 1) % len(self.playlist)

    def _play_playlist_index(self, index):
        if not (0 <= index < len(self.playlist)):
            return
        self._play_index = index
        self._play_index_file(index)

    def _play_index_file(self, index):
        if not (0 <= index < len(self.playlist)):
            return
        filename = self.playlist[index]
        if not os.path.exists(score_repo.score_path(filename)):
            self.status_var.set(f"文件不存在: {score_repo.display_name(filename)}")
            return
        self._play_index = index
        self._open_file(filename)
        self.start()

    def next_track(self):
        if not self.playlist:
            return
        self.player.stop()
        idx = self._pick_next_index()
        self._play_index = idx
        self._play_index_file(idx)

    def prev_track(self):
        if not self.playlist:
            return
        self.player.stop()
        mode = self.loop_var.get()
        if mode == "shuffle":
            idx = random.randrange(len(self.playlist))
        else:
            idx = (self._play_index - 1) % len(self.playlist)
        self._play_index = idx
        self._play_index_file(idx)

    def _on_play_finished(self):
        if not self.playlist:
            self.status_var.set("就绪")
            return
        if self.loop_var.get() == "repeat_one" and self._play_index >= 0:
            self._play_index_file(self._play_index)
            return
        idx = self._pick_next_index()
        if idx < 0:
            self.status_var.set("就绪")
            return
        self._play_index = idx
        self._play_index_file(idx)

    # ---------- 编辑 ----------
    def _mark_dirty(self, _event=None):
        self._dirty = True
        self.dirty_label.configure(text="● 未保存")

    def save_current(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先选择或新建一个谱子")
            return
        content = self.editor.get("1.0", "end-1c")
        try:
            with open(score_repo.score_path(self.current_file), "w", encoding="utf-8") as f:
                f.write(content)
            self._dirty = False
            self.dirty_label.configure(text="")
            self.status_var.set(f"已保存: {score_repo.display_name(self.current_file)}")
            if self._view_mode == "lyric":
                self._build_lyrics()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def _ask_name(self, title, default):
        dialog = ctk.CTkToplevel(self)
        dialog.title(title)
        dialog.geometry("380x170")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        result = {"value": None}

        ctk.CTkLabel(dialog, text="输入文件名（不含 .txt）:").pack(padx=16, pady=(16, 6), anchor="w")
        entry = ctk.CTkEntry(dialog, width=340)
        entry.pack(padx=16, pady=4)

        def fill_and_focus():
            entry.delete(0, "end")
            entry.insert(0, default)
            entry.focus_set()
            entry.select_range(0, "end")
            entry.icursor("end")

        dialog.after(50, fill_and_focus)

        def ok(_event=None):
            result["value"] = entry.get().strip()
            dialog.destroy()

        def cancel(_event=None):
            result["value"] = None
            dialog.destroy()

        btn = ctk.CTkFrame(dialog, fg_color="transparent")
        btn.pack(pady=12)
        ctk.CTkButton(btn, text="确定", width=90, command=ok).pack(side="left", padx=8)
        ctk.CTkButton(btn, text="取消", width=90, fg_color="#555555", hover_color="#444444",
                      command=cancel).pack(side="left", padx=8)

        entry.bind("<Return>", ok)
        dialog.bind("<Escape>", cancel)

        self.wait_window(dialog)
        return result["value"]

    def _next_new_name(self):
        base = "新乐谱"
        existing = set(score_repo.list_scores())
        name = base
        i = 2
        while score_repo.ensure_txt(name) in existing:
            name = f"{base}{i}"
            i += 1
        return name

    def save_as(self):
        content = self.editor.get("1.0", "end-1c")
        default = score_repo.display_name(self.current_file) if self.current_file else "新乐谱"
        name = self._ask_name("另存为", default)
        if not name:
            return
        filename = score_repo.ensure_txt(name)
        path = score_repo.score_path(filename)
        if os.path.exists(path):
            if not messagebox.askyesno("覆盖", f"{score_repo.display_name(filename)} 已存在，覆盖？"):
                return
        try:
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            self.current_file = filename
            self.file_label.configure(text=score_repo.display_name(filename))
            self._dirty = False
            self.dirty_label.configure(text="")
            self.refresh_list()
            self.status_var.set(f"已另存为: {score_repo.display_name(filename)}")
            if self._view_mode == "lyric":
                self._build_lyrics()
        except Exception as e:
            messagebox.showerror("保存失败", str(e))

    def rename_current(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先选择一个谱子")
            return
        old_name = score_repo.display_name(self.current_file)
        new_name = self._ask_name("重命名乐谱", old_name)
        if not new_name or new_name == old_name:
            return

        new_filename = score_repo.ensure_txt(new_name)
        new_path = score_repo.score_path(new_filename)
        if os.path.exists(new_path):
            messagebox.showwarning("已存在", f"{score_repo.display_name(new_filename)} 已存在，请换名。")
            return

        try:
            os.rename(score_repo.score_path(self.current_file), new_path)
        except Exception as e:
            messagebox.showerror("重命名失败", str(e))
            return

        if self.current_file in self.playlist:
            idx = self.playlist.index(self.current_file)
            self.playlist[idx] = new_filename

        self.current_file = new_filename
        self.file_label.configure(text=score_repo.display_name(new_filename))
        self.refresh_list()
        self._highlight(new_filename)
        self._refresh_playlist_dialog()
        self.status_var.set(f"已重命名为: {score_repo.display_name(new_filename)}")

    def new_score(self):
        if self._dirty:
            if not messagebox.askyesno("未保存", "当前乐谱有未保存修改，新建将丢失。继续？"):
                return
        try:
            default = self._next_new_name()
            name = self._ask_name("新建乐谱", default)
            if not name:
                return
            filename = score_repo.ensure_txt(name)
            path = score_repo.score_path(filename)
            if os.path.exists(path):
                messagebox.showwarning("已存在", f"{score_repo.display_name(filename)} 已存在，请换名或直接打开编辑。")
                return

            title = score_repo.display_name(filename)
            with open(path, "w", encoding="utf-8") as f:
                f.write("# " + title + "\n")

            self._open_file(filename)
            self.refresh_list()
            self.status_var.set(f"已新建: {title}")
        except Exception as e:
            messagebox.showerror("新建失败", str(e))

    def delete_current(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先选择一个谱子")
            return
        shown = score_repo.display_name(self.current_file)
        if not messagebox.askyesno("删除", f"确定删除 {shown}？"):
            return
        try:
            os.remove(score_repo.score_path(self.current_file))
            self.player.stop()
            if self.current_file in self.playlist:
                self.playlist.remove(self.current_file)
            self.current_file = None
            self.file_label.configure(text="未选择乐谱")
            self.editor.delete("1.0", "end")
            self._dirty = False
            self.dirty_label.configure(text="")
            self.progress.set(0)
            self.time_label.configure(text="00:00 / 00:00")
            self.refresh_list()
            self._refresh_playlist_dialog()
            self.status_var.set("已删除")
        except Exception as e:
            messagebox.showerror("删除失败", str(e))

    # ---------- 播放 ----------
    def load_selected(self):
        if not self.current_file:
            messagebox.showwarning("提示", "请先在列表中选择一个谱子")
            return
        try:
            tokens = score_repo.load_tokens(self.current_file)
            self.events = player.parse_events(tokens)
            self.player.load(self.events, self.mode_var.get())
            self.progress.set(0)
            self.time_label.configure(text=f"00:00 / {self._fmt(self.player.duration_ms)}")
            self.status_var.set(f"已加载 {score_repo.display_name(self.current_file)}，共 {len(self.events)} 个事件")
        except Exception as e:
            messagebox.showerror("加载失败", str(e))

    def start(self):
        if not self.current_file:
            if not self.playlist:
                messagebox.showwarning("提示", "未选择歌曲，且播放列表为空")
                return
            idx = self._play_index if 0 <= self._play_index < len(self.playlist) else 0
            self._play_index = idx
            self._play_index_file(idx)
            return

        if self.current_file not in self.playlist:
            self.playlist.append(self.current_file)
            self._play_index = len(self.playlist) - 1
            self._update_playlist_label()
            self._refresh_playlist_dialog()
            self.status_var.set(f"已自动加入播放列表：{score_repo.display_name(self.current_file)}")
        else:
            self._play_index = self.playlist.index(self.current_file)

        if self.events is None:
            self.load_selected()
            if self.events is None:
                return
        mode = self.mode_var.get()
        if not self.player.is_loaded(self.events, mode):
            self.player.load(self.events, mode)
        self._playing_name = score_repo.display_name(self.current_file) if self.current_file else "未命名"
        self._playing_mode = "音频" if mode == "audio" else "按键"
        pos = self.player.position_ms()
        self.player.play(from_ms=pos)
        self.status_var.set(f"播放中：{self._playing_name}（{self._playing_mode}）")

    def toggle_pause(self):
        if not self.player.is_playing:
            return
        self.player.toggle_pause()
        if self.player.paused:
            self.status_var.set(f"已暂停：{self._playing_name}（{self._playing_mode}）")
        else:
            self.status_var.set(f"播放中：{self._playing_name}（{self._playing_mode}）")

    def stop(self):
        self.player.stop()
        self._playing_name = None
        self._playing_mode = None
        self.progress.set(0)
        self.time_label.configure(text=f"00:00 / {self._fmt(self.player.duration_ms)}")
        self.status_var.set("就绪")

        self._current_lyric_idx = -1
        if self._view_mode == "lyric":
            self._highlight_lyric(-1)

    def _on_seek_start(self, _event=None):
        self._seeking = True

    def _on_seek_drag(self, value):
        if self.player.duration_ms <= 0:
            return
        ms = self.player.duration_ms * float(value) / 1000.0
        self.time_label.configure(text=f"{self._fmt(ms)} / {self._fmt(self.player.duration_ms)}")

    def _on_seek_commit(self, _event=None):
        if self.player.duration_ms <= 0:
            self._seeking = False
            return
        ms = self.player.duration_ms * float(self.progress.get()) / 1000.0
        self.player.seek(ms)
        self._seeking = False
        if self.player.is_playing:
            self.status_var.set(f"播放中：{self._playing_name}（{self._playing_mode}）")

    def _fmt(self, ms):
        s = int(ms / 1000)
        return f"{s // 60:02d}:{s % 60:02d}"

    # ---------- 浮窗 ----------
    def toggle_float_window(self):
        if self._float_win is not None and self._float_win.winfo_exists():
            self._close_float_window()
            return

        self._float_win = FloatWindow(
            self,
            on_play_pause=self._float_play_pause,
            on_stop=self._float_stop,
            on_prev=self.prev_track,
            on_next=self.next_track,
            on_close=self._close_float_window,
            get_state=self._float_state,
        )

    def _close_float_window(self):
        if self._float_win is not None:
            try:
                self._float_win.destroy()
            except Exception:
                pass
            self._float_win = None

    def _float_play_pause(self):
        if self.player.is_playing:
            self.toggle_pause()
        else:
            self.start()

    def _float_stop(self):
        self.stop()

    def _float_state(self):
        next_title = "—"
        if self.playlist:
            if self.loop_var.get() == "shuffle":
                next_title = "随机"
            else:
                idx = self._pick_next_index()
                if 0 <= idx < len(self.playlist):
                    nxt = self.playlist[idx]
                    is_current = (idx == self._play_index)
                    suffix = "（单曲循环）" if is_current and self.loop_var.get() == "repeat_one" else ""
                    next_title = score_repo.display_name(nxt) + suffix

        return {
            "title": self._playing_name or "未播放",
            "mode": self._playing_mode or "",
            "playing": self.player.is_playing,
            "paused": self.player.paused,
            "pos_ms": self.player.position_ms(),
            "dur_ms": self.player.duration_ms,
            "next_title": next_title,
        }

    # ---------- 轮询 ----------
    def _poll_status(self):
        if self.events and self.player.duration_ms > 0:
            total = self.player.duration_ms
            pos = self.player.position_ms()
            if not self._seeking:
                self.time_label.configure(text=f"{self._fmt(pos)} / {self._fmt(total)}")
                self.progress.set(int(1000 * pos / total) if total > 0 else 0)

        if not self.player.is_playing:
            if self.status_var.get().startswith("播放中") or self.status_var.get().startswith("已暂停"):
                self.status_var.set("就绪")
                self._playing_name = None
                self._playing_mode = None

        if self._view_mode == "lyric":
            self._sync_lyric_to_pos()

        self.after(200, self._poll_status)

    # ---------- 关闭 ----------
    def _on_close_app(self):
        if self._float_win is not None:
            try:
                self._float_win.destroy()
            except Exception:
                pass

        if self._playlist_dialog is not None:
            try:
                self._playlist_dialog.destroy()
            except Exception:
                pass

        if self.video_view is not None and hasattr(self.video_view, 'cap') and self.video_view.cap:
            try:
                self.video_view.cap.release()
            except Exception:
                pass

        self.player.stop()
        self.destroy()