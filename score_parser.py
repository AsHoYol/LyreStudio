"""谱子解析与音频合成（供 player.py 和其他模块共用）"""

import numpy as np

VALID_KEYS = set("qwertyuasdfghjzxcvbnm")
SAMPLE_RATE = 44100
DEFAULT_DUR_MS = 500.0

KEY_FREQ = {
    "z": 261.63, "x": 293.66, "c": 329.63, "v": 349.23,
    "b": 392.00, "n": 440.00, "m": 493.88,
    "a": 523.25, "s": 587.33, "d": 659.25, "f": 698.46,
    "g": 783.99, "h": 880.00, "j": 987.77,
    "q": 1046.50, "w": 1174.66, "e": 1318.51, "r": 1396.91,
    "t": 1567.98, "y": 1760.00, "u": 1975.53,
}


def is_number(tok):
    try:
        float(tok)
        return True
    except ValueError:
        return False


def parse_events(tokens):
    """tokens -> [(keys, dur_ms, start_ms), ...]"""
    events = []
    i = 0
    n = len(tokens)
    cursor_ms = 0.0
    while i < n:
        tok = tokens[i]
        if is_number(tok):
            dur_ms = float(tok)
            events.append(([], dur_ms, cursor_ms))
            cursor_ms += dur_ms
            i += 1
        else:
            note_tok = tok.lower()
            keys = [ch for ch in note_tok if ch in VALID_KEYS]
            if i + 1 < n and is_number(tokens[i + 1]):
                dur_ms = float(tokens[i + 1])
                i += 2
            else:
                dur_ms = DEFAULT_DUR_MS
                i += 1
            events.append((keys, dur_ms, cursor_ms))
            cursor_ms += dur_ms
    return events


def total_duration_ms(events):
    return (events[-1][2] + events[-1][1]) if events else 0.0


def synth_note(freq, dur_s, sr=SAMPLE_RATE):
    """短按乐器音色：快速起音，指数衰减"""
    tail_s = 0.8
    total_s = dur_s + tail_s
    n = int(sr * total_s)
    if n <= 0:
        return np.zeros(0, dtype=np.float32)
    t = np.arange(n) / sr
    wave = (
        1.00 * np.sin(2 * np.pi * freq * t) +
        0.45 * np.sin(2 * np.pi * 2 * freq * t) +
        0.25 * np.sin(2 * np.pi * 3 * freq * t) +
        0.12 * np.sin(2 * np.pi * 4 * freq * t) +
        0.06 * np.sin(2 * np.pi * 5 * freq * t) +
        0.03 * np.sin(2 * np.pi * 6 * freq * t)
    )
    wave += 0.15 * np.sin(2 * np.pi * (freq * 1.001) * t)
    env = np.ones(n, dtype=np.float32)
    attack = min(int(0.003 * sr), n // 2)
    if attack > 0:
        env[:attack] = np.linspace(0, 1, attack, endpoint=False)
    decay_rate = 3.0 + freq / 800.0
    env *= np.exp(-decay_rate * t)
    release = min(int(0.05 * sr), n // 2)
    if release > 0:
        env[-release:] *= np.linspace(1, 0, release, endpoint=False)
    peak = np.max(np.abs(wave))
    if peak > 0:
        wave = wave / peak
    return (wave * env * 0.35).astype(np.float32)


def build_audio(events, sr=SAMPLE_RATE):
    total_ms = total_duration_ms(events)
    total_samples = int(sr * (total_ms / 1000.0 + 1.0))
    audio = np.zeros(total_samples, dtype=np.float32)
    for keys, dur_ms, start_ms in events:
        if not keys:
            continue
        dur_s = dur_ms / 1000.0
        start_sample = int(sr * start_ms / 1000.0)
        for k in keys:
            note = synth_note(KEY_FREQ[k], dur_s, sr)
            end_sample = min(start_sample + len(note), total_samples)
            audio[start_sample:end_sample] += note[:end_sample - start_sample]
    peak = np.max(np.abs(audio))
    if peak > 0.9:
        audio *= 0.9 / peak
    return audio