"""琴键标定工具与通用函数。

注意：交互标定现在已集成到主界面的 Canvas 中，此处的 KeyLocator 类保留用于独立运行，
或者作为后备的高级工具。主界面主要使用此处的 grab_frame 和存取标定文件功能。
"""

import json
import os
import cv2
import numpy as np

# 标准 21 键顺序（与 score_parser.KEY_FREQ 一致）
KEY_LAYOUT = [
    ["q", "w", "e", "r", "t", "y", "u"],
    ["a", "s", "d", "f", "g", "h", "j"],
    ["z", "x", "c", "v", "b", "n", "m"],
]
ORDERED_KEYS = [k for row in KEY_LAYOUT for k in row]


class KeyLocator:
    """在给定帧上交互式标定琴键位置（独立的 OpenCV 窗口版本，主界面已改用 Canvas）。"""

    def __init__(self, frame, radius=12):
        self.frame = frame.copy()
        self.radius = radius
        self.points = {}          # key -> (x, y)
        self._order_idx = 0
        self._win = "Key Locator - 依次点击 21 个键中心 (ESC 取消, Z 撤销)"

    def run(self):
        """阻塞运行标定界面，返回 dict 或 None（取消）。"""
        cv2.namedWindow(self._win, cv2.WINDOW_NORMAL)
        cv2.setMouseCallback(self._win, self._on_mouse)
        while True:
            img = self._render()
            cv2.imshow(self._win, img)
            k = cv2.waitKey(30) & 0xFF
            if k == 27:  # ESC
                cv2.destroyWindow(self._win)
                return None
            if k == ord("z") and self._order_idx > 0:
                self._order_idx -= 1
                key = ORDERED_KEYS[self._order_idx]
                self.points.pop(key, None)
            if self._order_idx >= len(ORDERED_KEYS):
                cv2.destroyWindow(self._win)
                return dict(self.points)

    def _on_mouse(self, event, x, y, flags, param):
        if event == cv2.EVENT_LBUTTONDOWN and self._order_idx < len(ORDERED_KEYS):
            key = ORDERED_KEYS[self._order_idx]
            self.points[key] = (x, y)
            self._order_idx += 1

    def _render(self):
        img = self.frame.copy()
        for key, (x, y) in self.points.items():
            cv2.circle(img, (x, y), self.radius, (0, 255, 0), 2)
            cv2.putText(img, key, (x - 6, y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 1)
        if self._order_idx < len(ORDERED_KEYS):
            next_key = ORDERED_KEYS[self._order_idx]
            hint = f"Next: {next_key}  ({self._order_idx + 1}/{len(ORDERED_KEYS)})"
        else:
            hint = "Done! Press any key to close."
        cv2.putText(img, hint, (10, 30),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
        return img


def save_calibration(points, path):
    """保存绝对像素坐标（为了兼容旧测试，主界面现在直接写在 app 内部了）"""
    data = {
        "radius": 12,
        "keys": {k: list(v) for k, v in points.items()},
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_calibration(path):
    """加载绝对像素坐标"""
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    pts = {k: tuple(v) for k, v in data.get("keys", {}).items()}
    return pts, data.get("radius", 12)


def grab_frame(video_path, time_sec=None):
    """从视频指定时间抓取一帧画面，返回 (frame, fps)"""
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise RuntimeError(f"无法打开视频: {video_path}")
    fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
    if time_sec is not None:
        cap.set(cv2.CAP_PROP_POS_MSEC, time_sec * 1000)
    ok, frame = cap.read()
    cap.release()
    if not ok:
        raise RuntimeError("无法读取帧（时间点可能超出视频长度）")
    return frame, fps