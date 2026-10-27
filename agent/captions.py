"""Animated word-by-word captions (TikTok/Reels style) as an ASS subtitle file for FFmpeg."""
from __future__ import annotations

import re
from pathlib import Path

PUNCT_END = re.compile(r"[.,!?;:…]$")


def _ass_color(hex_color: str) -> str:
    h = hex_color.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}".upper()


def _t(seconds: float) -> str:
    seconds = max(0.0, seconds)
    h, rem = divmod(seconds, 3600)
    m, s = divmod(rem, 60)
    return f"{int(h)}:{int(m):02d}:{s:05.2f}"


def _escape(word: str) -> str:
    return word.replace("\\", "").replace("{", "(").replace("}", ")")


def chunk_words(words: list[tuple[float, float, str]], max_words: int = 3, max_chars: int = 16) -> list[list]:
    chunks, current = [], []
    for word in words:
        text = word[2]
        if current and (len(current) >= max_words or len(" ".join(w[2] for w in current + [word])) > max_chars):
            chunks.append(current)
            current = []
        current.append(word)
        if PUNCT_END.search(text):
            chunks.append(current)
            current = []
    if current:
        chunks.append(current)
    return chunks


def build(words: list[tuple[float, float, str]], path: Path, ink: str, highlight: str = "#FFD84D",
          font: str = "Brand Caption", size: int = 94, y: int = 1250) -> None:
    """`words` are (start, end, text) in absolute reel time."""
    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: 1080
PlayResY: 1920
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Word,{font},{size},&H00FFFFFF,&H00FFFFFF,{_ass_color(ink)},&H64000000,0,0,0,0,100,100,0,0,1,7,3,5,80,80,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    hl = _ass_color(highlight)
    events = []
    chunks = chunk_words(words)
    for ci, chunk in enumerate(chunks):
        chunk_end = chunk[-1][1] + 0.25
        if ci + 1 < len(chunks):
            chunk_end = min(chunk_end, chunks[ci + 1][0][0])
        for wi, (start, _end, _text) in enumerate(chunk):
            end = chunk[wi + 1][0] if wi + 1 < len(chunk) else chunk_end
            parts = []
            for wj, (_, _, other) in enumerate(chunk):
                other = _escape(other)
                parts.append(f"{{\\c{hl}}}{other}{{\\c&H00FFFFFF&}}" if wj == wi else other)
            pop = r"\fscx92\fscy92\t(0,90,\fscx104\fscy104)\t(90,160,\fscx100\fscy100)" if wi == 0 else ""
            text = f"{{\\an5\\pos(540,{y}){pop}}}" + " ".join(parts)
            events.append(f"Dialogue: 0,{_t(start)},{_t(max(end, start + 0.05))},Word,,0,0,0,,{text}")
    path.write_text(header + "\n".join(events) + "\n", encoding="utf-8")
