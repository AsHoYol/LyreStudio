import time
import threading
import numpy as np
import sounddevice as sd
import keyboard

from score_parser import (
    VALID_KEYS, SAMPLE_RATE, DEFAULT_DUR_MS, KEY_FREQ,
    parse_events, total_duration_ms, synth_note, build_audio,
)

PRESS_HOLD_MS = 30.0

__all__ = [
    "Player", "VALID_KEYS", "SAMPLE_RATE", "DEFAULT_DUR_MS",
    "KEY_FREQ", "parse_events", "synth_note", "build_audio",
]


class Player:
    """线程安全播放器：代际号控制，支持定位、暂停/停止、自然结束回调"""

    def __init__(self):
        self._lock = threading.Lock()
        self._thread = None
        self._generation = 0
        self._paused = False

        self._events = []
        self._audio = None
        self._mode = "audio"

        self._total_ms = 0.0
        self._start_wall = 0.0
        self._start_pos_ms = 0.0
        self._current_ms = 0.0

        self.on_finished = None

    @property
    def is_playing(self):
        return self._thread is not None and self._thread.is_alive()

    @property
    def paused(self):
        return self._paused

    @property
    def duration_ms(self):
        return self._total_ms

    @property
    def mode(self):
        return self._mode

    def has_events(self):
        return bool(self._events)

    def is_loaded(self, events, mode):
        return self._events is events and self._mode == mode

    def position_ms(self):
        if not self.is_playing:
            return self._current_ms
        if self._paused:
            return self._current_ms
        elapsed = (time.time() - self._start_wall) * 1000.0
        pos = self._start_pos_ms + elapsed
        return min(pos, self._total_ms)

    def load(self, events, mode):
        with self._lock:
            self._generation += 1
            self._thread = None
            self._paused = False
            self._events = events
            self._mode = mode
            self._total_ms = total_duration_ms(events)
            self._audio = build_audio(events) if mode == "audio" else None
            self._current_ms = 0.0

    def play(self, from_ms=0.0):
        with self._lock:
            if not self._events:
                return
            self._generation += 1
            gen = self._generation
            self._paused = False
            self._start_pos_ms = max(0.0, min(from_ms, self._total_ms))
            self._current_ms = self._start_pos_ms
            self._start_wall = time.time()

            target = self._run_audio if self._mode == "audio" and self._audio is not None else self._run_keys
            self._thread = threading.Thread(target=target, args=(gen, self._start_pos_ms), daemon=True)
            self._thread.start()

    def pause(self):
        with self._lock:
            if not self.is_playing or self._paused:
                return
            self._current_ms = self.position_ms()
            self._paused = True

    def resume(self):
        with self._lock:
            if not self.is_playing or not self._paused:
                return
            self._paused = False
            self._start_pos_ms = self._current_ms
            self._start_wall = time.time()

    def toggle_pause(self):
        if self._paused:
            self.resume()
        else:
            self.pause()

    def stop(self):
        with self._lock:
            self._generation += 1
            self._paused = False
            self._current_ms = 0.0
            self._thread = None

    def seek(self, ms):
        with self._lock:
            target = max(0.0, min(ms, self._total_ms))
            self._current_ms = target
            if self._thread is None or not self._thread.is_alive():
                return
            was_paused = self._paused
            self._generation += 1
            gen = self._generation
            self._start_pos_ms = target
            self._start_wall = time.time()
            self._paused = was_paused

            target_fn = self._run_audio if self._mode == "audio" and self._audio is not None else self._run_keys
            self._thread = threading.Thread(target=target_fn, args=(gen, target), daemon=True)
            self._thread.start()

    def _finish(self, gen):
        if gen != self._generation:
            return
        with self._lock:
            self._current_ms = self._total_ms
        if self.on_finished:
            self.on_finished()

    def _run_audio(self, gen, start_ms):
        audio = self._audio
        if audio is None:
            return
        total = len(audio)
        pos = int(SAMPLE_RATE * start_ms / 1000.0)
        block = 1024

        def callback(outdata, frames, time_info, status):
            nonlocal pos
            if gen != self._generation:
                outdata[:] = 0
                raise sd.CallbackStop
            if self._paused:
                outdata[:] = 0
                return
            remaining = total - pos
            if remaining <= 0:
                outdata[:] = 0
                raise sd.CallbackStop
            n = min(frames, remaining)
            outdata[:n, 0] = audio[pos:pos + n]
            if n < frames:
                outdata[n:, 0] = 0
            pos += n

        try:
            with sd.OutputStream(samplerate=SAMPLE_RATE, channels=1,
                                 blocksize=block, callback=callback):
                while pos < total and gen == self._generation:
                    time.sleep(0.05)
        except Exception as e:
            print("音频播放异常:", e)

        self._finish(gen)

    def _run_keys(self, gen, start_ms):
        kb = keyboard
        t0 = time.time()
        base_ms = start_ms
        pause_start = 0.0
        pause_accum = 0.0

        def wall_ms():
            return base_ms + (time.time() - t0) * 1000.0 - pause_accum

        def wait_until(target_ms):
            nonlocal pause_start, pause_accum
            while True:
                if gen != self._generation:
                    return False
                if self._paused:
                    if pause_start == 0.0:
                        pause_start = time.time()
                    time.sleep(0.02)
                    continue
                if pause_start != 0.0:
                    pause_accum += (time.time() - pause_start) * 1000.0
                    pause_start = 0.0
                if wall_ms() >= target_ms:
                    return True
                time.sleep(min(0.005, max(0.0, (target_ms - wall_ms()) / 1000.0)))

        for keys, dur_ms, event_ms in self._events:
            if gen != self._generation:
                return
            event_end = event_ms + dur_ms
            if event_end <= start_ms:
                continue

            if not wait_until(event_ms):
                return

            if not keys:
                if not wait_until(event_end):
                    return
                continue

            for k in keys:
                kb.press(k)
                
            # 固定按下时间（短按乐器）
            hold_end = wall_ms() + PRESS_HOLD_MS
            while True:
                if gen != self._generation:
                    for k in keys:
                        kb.release(k)
                    return
                if self._paused:
                    if pause_start == 0.0:
                        pause_start = time.time()
                    time.sleep(0.02)
                    continue
                if pause_start != 0.0:
                    pause_accum += (time.time() - pause_start) * 1000.0
                    pause_start = 0.0
                if wall_ms() >= hold_end:
                    break
                time.sleep(min(0.005, max(0.0, (hold_end - wall_ms()) / 1000.0)))
                
            for k in keys:
                kb.release(k)

            if not wait_until(event_end):
                return

        self._finish(gen)