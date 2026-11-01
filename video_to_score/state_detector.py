"""琴键按下状态判定：基线 + 阈值 + 防抖。"""

import cv2
import numpy as np

PATCH = 8  # 采样方块半边长


class StateDetector:
    def __init__(self, points, radius=12, diff_threshold=25.0, debounce_frames=2):
        self.points = points
        self.radius = radius
        self.diff_threshold = diff_threshold
        self.debounce_frames = debounce_frames
        self.baseline = {}
        self._hold_count = {k: 0 for k in points}
        self._release_count = {k: 0 for k in points}
        self._pressed = {k: False for k in points}

    def capture_baseline(self, frames):
        samples = {k: [] for k in self.points}
        for frame in frames:
            for k, (x, y) in self.points.items():
                patch = self._patch(frame, x, y)
                if patch is not None:
                    samples[k].append(patch.reshape(-1, 3).mean(axis=0))
        for k, arrs in samples.items():
            if arrs:
                self.baseline[k] = np.median(np.array(arrs), axis=0)
            else:
                self.baseline[k] = np.array([128.0, 128.0, 128.0])

    def _patch(self, frame, x, y):
        h, w = frame.shape[:2]
        x0, y0 = max(0, x - PATCH), max(0, y - PATCH)
        x1, y1 = min(w, x + PATCH), min(h, y + PATCH)
        if x1 <= x0 or y1 <= y0:
            return None
        return frame[y0:y1, x0:x1].astype(np.float32)

    def update(self, frame):
        pressed_now = set()
        for k, (x, y) in self.points.items():
            patch = self._patch(frame, x, y)
            if patch is None:
                continue
            mean = patch.reshape(-1, 3).mean(axis=0)
            diff = float(np.linalg.norm(mean - self.baseline[k]))
            is_on = diff > self.diff_threshold

            if is_on:
                self._hold_count[k] += 1
                self._release_count[k] = 0
            else:
                self._release_count[k] += 1
                self._hold_count[k] = 0

            if not self._pressed[k] and self._hold_count[k] >= self.debounce_frames:
                self._pressed[k] = True
            elif self._pressed[k] and self._release_count[k] >= self.debounce_frames:
                self._pressed[k] = False

            if self._pressed[k]:
                pressed_now.add(k)
        return pressed_now

    def render(self, frame, pressed_set):
        img = frame.copy()
        for k, (x, y) in self.points.items():
            color = (0, 0, 255) if k in pressed_set else (0, 200, 0)
            cv2.circle(img, (x, y), self.radius, color, 2)
            cv2.putText(img, k, (x - 6, y + 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
        return img

    def sensitivity(self, value):
        self.diff_threshold = max(5.0, 100.0 * (1.0 - value))