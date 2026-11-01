"""播放列表查看/编辑弹窗"""

import customtkinter as ctk
from tkinter import messagebox


class PlaylistDialog(ctk.CTkToplevel):
    """可查看、删除、上下移动、清空、双击播放的播放列表编辑窗。

    外部接口：
      playlist        : list[str]  —— 直接传入 App 的 playlist 引用（同对象）
      on_changed      : () -> None —— 列表内容变化后的回调
      on_play_index   : (int) -> None —— 双击某行请求播放
      display_name    : (filename) -> str
    """

    def __init__(self, master, playlist, on_changed, on_play_index, display_name):
        super().__init__(master)
        self._playlist = playlist
        self._on_changed = on_changed
        self._on_play_index = on_play_index
        self._display_name = display_name

        self.title("播放列表")
        self.geometry("420x520")
        self.minsize(360, 400)
        self.transient(master)
        self.grab_set()

        self._build()
        self._refresh()

    def _build(self):
        header = ctk.CTkFrame(self, fg_color="transparent")
        header.pack(fill="x", padx=12, pady=(12, 4))

        self.count_label = ctk.CTkLabel(
            header, text="0 首", font=ctk.CTkFont(size=13, weight="bold")
        )
        self.count_label.pack(side="left")

        ctk.CTkButton(
            header, text="清空", width=70, height=26, corner_radius=6,
            fg_color="#b23a3a", hover_color="#8f2f2f",
            command=self._clear_all,
        ).pack(side="right")

        self.list_container = ctk.CTkScrollableFrame(self, corner_radius=8)
        self.list_container.pack(fill="both", expand=True, padx=12, pady=8)

        footer = ctk.CTkFrame(self, fg_color="transparent")
        footer.pack(fill="x", padx=12, pady=(0, 12))
        ctk.CTkLabel(
            footer, text="双击播放 · 选中后可用按钮调整",
            text_color="#9aa0a6", font=ctk.CTkFont(size=11),
        ).pack(side="left")

    def _refresh(self):
        for w in self.list_container.winfo_children():
            w.destroy()

        self.count_label.configure(text=f"{len(self._playlist)} 首")

        if not self._playlist:
            ctk.CTkLabel(
                self.list_container, text="（空）", text_color="#9aa0a6"
            ).pack(pady=20)
            return

        for i, filename in enumerate(self._playlist):
            row = ctk.CTkFrame(self.list_container, corner_radius=6)
            row.pack(fill="x", pady=3, padx=2)

            idx_label = ctk.CTkLabel(
                row, text=f"{i + 1:02d}", width=32,
                font=ctk.CTkFont(size=12), text_color="#9aa0a6",
            )
            idx_label.pack(side="left", padx=(6, 4))

            name_btn = ctk.CTkButton(
                row, text=self._display_name(filename),
                anchor="w", height=30, corner_radius=4,
                fg_color="transparent", hover_color="#2f3b52",
                text_color="#e6e6e6",
                font=ctk.CTkFont(size=13),
                command=lambda idx=i: self._on_play_index(idx),
            )
            name_btn.pack(side="left", fill="x", expand=True)

            # 双击也播放
            name_btn.bind("<Double-Button-1>", lambda _e, idx=i: self._on_play_index(idx))

            up_btn = ctk.CTkButton(
                row, text="↑", width=28, height=28, corner_radius=4,
                fg_color="#444444", hover_color="#555555",
                command=lambda idx=i: self._move(idx, -1),
            )
            up_btn.pack(side="left", padx=2)

            down_btn = ctk.CTkButton(
                row, text="↓", width=28, height=28, corner_radius=4,
                fg_color="#444444", hover_color="#555555",
                command=lambda idx=i: self._move(idx, +1),
            )
            down_btn.pack(side="left", padx=2)

            del_btn = ctk.CTkButton(
                row, text="✕", width=28, height=28, corner_radius=4,
                fg_color="#b23a3a", hover_color="#8f2f2f",
                command=lambda idx=i: self._remove(idx),
            )
            del_btn.pack(side="left", padx=(2, 6))

    def _move(self, index, delta):
        target = index + delta
        if not (0 <= index < len(self._playlist) and 0 <= target < len(self._playlist)):
            return
        self._playlist[index], self._playlist[target] = (
            self._playlist[target], self._playlist[index]
        )
        self._after_change()

    def _remove(self, index):
        if not (0 <= index < len(self._playlist)):
            return
        del self._playlist[index]
        self._after_change()

    def _clear_all(self):
        if not self._playlist:
            return
        if not messagebox.askyesno("清空播放列表", "确定清空所有条目？", parent=self):
            return
        self._playlist.clear()
        self._after_change()

    def _after_change(self):
        if self._on_changed:
            self._on_changed()
        self._refresh()