"""把逐帧按下集合转为事件序列（短按乐器版本）。"""


def _all_keys(frame_results):
    keys = set()
    for s in frame_results:
        keys |= s
    return keys


# ============================================================
# 短按乐器（风物之诗琴）：基于“上升沿 + 合并”，无空键
# ============================================================
def frames_to_events(frame_results, fps, merge_window_ms=100,
                     min_gap_ms=150, min_note_ms=60, **_kwargs):
    """短按识别：基于“上升沿 + 合并”的事件生成。

    参数：
        frame_results   : list[set[str]]，每帧稳定按下的键集合
        fps             : 视频帧率
        merge_window_ms : 起点差小于此值的音符合并为和弦（默认 100）
        min_gap_ms      : 同键最短重复间隔，过滤视觉残留假触发（默认 150）
        min_note_ms     : 最后一个音的收尾时长（默认 60）

    返回：
        events: [(keys_sorted_list, dur_ms, start_ms), ...]  无空键
    """
    if not frame_results:
        return []

    frame_ms = 1000.0 / max(fps, 1.0)
    n = len(frame_results)
    all_keys = _all_keys(frame_results)

    # 1) 逐键找 0->1 上升沿
    prev = {k: False for k in all_keys}
    last_on_frame = {}
    note_ons = []

    for i in range(n):
        cur = frame_results[i]
        for k in cur:
            if not prev.get(k, False):
                if k not in last_on_frame or \
                   (i - last_on_frame[k]) * frame_ms >= min_gap_ms:
                    note_ons.append((i * frame_ms, k))
                    last_on_frame[k] = i
        for k in set(prev.keys()) | set(cur):
            prev[k] = k in cur

    if not note_ons:
        return []

    # 2) 按起点合并为和弦
    note_ons.sort()
    chords = []
    cur_start, cur_keys = note_ons[0][0], {note_ons[0][1]}

    for t, k in note_ons[1:]:
        if t - cur_start < merge_window_ms:
            cur_keys.add(k)
        else:
            chords.append((cur_start, cur_keys))
            cur_start, cur_keys = t, {k}
    chords.append((cur_start, cur_keys))

    # 3) 生成连续时间轴事件
    events = []
    base_start = chords[0][0]

    for i, (start, keys) in enumerate(chords):
        if i < len(chords) - 1:
            dur = chords[i + 1][0] - start
        else:
            dur = min_note_ms
        events.append((sorted(keys), dur, start - base_start))

    return events


# ============================================================
# 通用输出格式
# ============================================================
def events_to_tokens(events):
    """纯交替格式 token 列表。"""
    tokens = []
    for keys, dur, _ in events:
        if not keys:
            tokens.append(str(int(round(dur))))
        else:
            tokens.append("".join(keys))
            tokens.append(str(int(round(dur))))
    return tokens


def events_to_text(events):
    """给测试区文本框显示用。"""
    lines = []
    for keys, dur, _ in events:
        if not keys:
            lines.append(f"{int(round(dur))}")
        else:
            lines.append(f"{''.join(keys)} {int(round(dur))}")
    return "\n".join(lines)