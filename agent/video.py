"""Step 4b — Video editing: assembles the reel with FFmpeg (clips, overlays, voiceover, captions, music)."""
from __future__ import annotations

import random
import shutil
import subprocess
from pathlib import Path

from . import captions, log
from .design import CAPTION_YELLOW, RH, RW
from .settings import FONTS, MUSIC
from .voice import duration as probe

FPS = 30
LEAD, GAP, TAIL = 0.25, 0.12, 0.45   # seconds of air before, between and after voice lines


def timeline(clip_files: list[Path], segments: list[dict]) -> dict:
    """segments = [hook, line for clip 1..n, cta]. Every clip lasts at least its natural length and long enough
    for its voice line; the hook plays over the start of clip 1."""
    n = len(clip_files)
    hook, lines, cta = segments[0], segments[1:1 + n], segments[1 + n]
    clips, placements = [], []
    start = 0.0
    for k, path in enumerate(clip_files):
        natural = min(probe(path), 6.0)
        if k == 0:
            placements.append((hook, LEAD))
            voice_at = LEAD + hook["duration"] + GAP
        else:
            voice_at = start + LEAD
        placements.append((lines[k], voice_at))
        length = max(natural, voice_at - start + lines[k]["duration"] + TAIL)
        clips.append({"file": path, "start": start, "length": length, "natural": probe(path)})
        start += length
    end_length = max(2.8, LEAD + cta["duration"] + 0.7)
    placements.append((cta, start + LEAD))
    hook_end = max(2.2, LEAD + hook["duration"] + 0.3)
    return {"clips": clips, "end_start": start, "end_length": end_length, "total": start + end_length,
            "placements": placements, "hook_end": hook_end}


def render_reel(post_dir: Path, clip_files: list[Path], segments: list[dict], ink: str, volume: float = 0.12) -> Path:
    plan = timeline(clip_files, segments)
    total = plan["total"]

    # Captions: every spoken word, shifted to its place on the reel's timeline.
    words = [(s + at, e + at, w) for seg, at in plan["placements"] for (s, e, w) in seg["words"]]
    captions.build(words, post_dir / "captions.ass", ink=ink, highlight=CAPTION_YELLOW)
    (post_dir / "fonts").mkdir(exist_ok=True)
    shutil.copy(FONTS / "BrandCaption.ttf", post_dir / "fonts" / "BrandCaption.ttf")

    rel = lambda p: Path(p).resolve().relative_to(post_dir.resolve()).as_posix()
    inputs, graph = [], []

    def add_input(*args) -> int:
        inputs.extend(args)
        return sum(1 for a in inputs if a == "-i") - 1

    # Video: clips (slowed down up to 1.3x or held on the last frame when the voice line needs more time).
    labels = []
    for k, clip in enumerate(plan["clips"]):
        i = add_input("-i", rel(clip["file"]))
        factor = min(max(clip["length"] / clip["natural"], 1.0), 1.3)
        hold = max(clip["length"] - clip["natural"] * factor, 0) + 0.1
        graph.append(
            f"[{i}:v]scale={RW}:{RH}:force_original_aspect_ratio=increase,crop={RW}:{RH},setsar=1,"
            f"setpts={factor:.4f}*(PTS-STARTPTS),fps={FPS},tpad=stop_mode=clone:stop_duration={hold:.3f},"
            f"trim=duration={clip['length']:.3f},setpts=PTS-STARTPTS,format=yuv420p[v{k}]"
        )
        labels.append(f"[v{k}]")
    e = add_input("-framerate", str(FPS), "-loop", "1", "-t", f"{plan['end_length']:.3f}", "-i", "overlays/end_card.png")
    graph.append(f"[{e}:v]scale={RW}:{RH},setsar=1,fps={FPS},format=yuv420p[vend]")
    graph.append("".join(labels) + f"[vend]concat=n={len(labels) + 1}:v=1:a=0[b0]")

    # Overlays: the hook, then one name label per clip.
    layers = [("overlays/hook.png", 0.0, plan["hook_end"])]
    for k, clip in enumerate(plan["clips"]):
        begin = plan["hook_end"] if k == 0 else clip["start"] + 0.15
        finish = clip["start"] + clip["length"] - 0.1
        if finish - begin > 0.6:
            layers.append((f"overlays/label_{k + 1}.png", begin, finish))
    last = "b0"
    for j, (png, t0, t1) in enumerate(layers):
        i = add_input("-framerate", str(FPS), "-loop", "1", "-t", f"{total:.3f}", "-i", png)
        graph.append(
            f"[{i}:v]format=rgba,fade=t=in:st={t0:.3f}:d=0.2:alpha=1,fade=t=out:st={t1 - 0.2:.3f}:d=0.2:alpha=1[ov{j}]"
        )
        graph.append(f"[{last}][ov{j}]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})'[b{j + 1}]")
        last = f"b{j + 1}"
    graph.append(f"[{last}]ass=captions.ass:fontsdir=fonts[vout]")

    # Audio: voice lines at their times, optional music ducked under the voice, loudness for social media.
    voices = []
    for j, (seg, at) in enumerate(plan["placements"]):
        i = add_input("-i", f"voice/{seg['file']}")
        ms = int(at * 1000)
        graph.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,adelay={ms}|{ms}[a{j}]")
        voices.append(f"[a{j}]")
    graph.append("".join(voices) + f"amix=inputs={len(voices)}:normalize=0:duration=longest,"
                 f"apad=whole_dur={total:.3f},atrim=duration={total:.3f}[voice]")
    tracks = sorted(p for p in MUSIC.glob("*") if p.suffix.lower() in (".mp3", ".m4a", ".wav", ".aac"))
    if tracks:
        track = random.choice(tracks)
        log.info(f"Music: {track.name}")
        i = add_input("-stream_loop", "-1", "-i", str(track.resolve()))
        graph.append(f"[{i}:a]aresample=48000,aformat=channel_layouts=stereo,volume={volume},"
                     f"atrim=duration={total:.3f},afade=t=in:d=0.6,afade=t=out:st={total - 1.5:.3f}:d=1.5[music]")
        graph.append("[voice]asplit=2[vk][vm]")
        graph.append("[music][vk]sidechaincompress=threshold=0.04:ratio=6:attack=15:release=350[duck]")
        graph.append("[vm][duck]amix=inputs=2:normalize=0:duration=first,loudnorm=I=-14:TP=-1.5:LRA=11[aout]")
    else:
        graph.append("[voice]loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    out = post_dir / "reel.mp4"
    for crf in (20, 25):
        cmd = ["ffmpeg", "-y", "-hide_banner", "-loglevel", "error", *inputs,
               "-filter_complex", ";".join(graph), "-map", "[vout]", "-map", "[aout]",
               "-c:v", "libx264", "-preset", "medium", "-crf", str(crf), "-maxrate", "8M", "-bufsize", "16M",
               "-pix_fmt", "yuv420p", "-profile:v", "high", "-r", str(FPS), "-g", str(FPS * 2),
               "-c:a", "aac", "-b:a", "160k", "-ar", "48000", "-movflags", "+faststart",
               "-t", f"{total:.3f}", out.name]
        result = subprocess.run(cmd, cwd=post_dir, capture_output=True, text=True)
        if result.returncode != 0:
            raise RuntimeError("FFmpeg failed:\n" + result.stderr[-2000:])
        size_mb = out.stat().st_size / 1e6
        if size_mb < 19:  # the media host serves files up to 20 MB
            break
        log.warn(f"reel is {size_mb:.1f} MB, re-encoding smaller")
    log.info(f"Reel: {total:.1f}s, {out.stat().st_size / 1e6:.1f} MB")
    return out
