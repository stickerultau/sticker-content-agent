"""Step 4b — Video editing: assembles the sticker bomb reel with FFmpeg.

Timeline: a split second of the finished surface, a fast rewind to empty, then one clip per sticker (faster and
faster, the last and best one slower), and a hold on the finished surface. The last picture is the first one, so the
reel loops. Overlays: the hook, a 1/4 ... 4/4 counter with each sticker's material, and the shop line after the payoff.
"""
from __future__ import annotations

import subprocess
from array import array
from pathlib import Path

from . import log
from .design import RH, RW

FPS = 30
OPEN_HOLD, REWIND_STEP, END_HOLD = 0.35, 0.1, 0.8   # seconds
HOOK_END = 2.2                                      # the hook stays this long
FIT = f"scale={RW}:{RH}:force_original_aspect_ratio=increase:flags=lanczos,crop={RW}:{RH},setsar=1"


def duration(path: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def has_audio(path: Path) -> bool:
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                          "-of", "csv=p=0", str(path)], capture_output=True, text=True).stdout
    return bool(out.strip())


def loudest_moment(path: Path, window: float = 0.04) -> float | None:
    """When the clip's sound peaks (the sticker's slap), in seconds; None without sound."""
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", str(path), "-vn", "-ac", "1", "-ar", "8000", "-f", "s16le", "-"],
                         capture_output=True).stdout
    samples = array("h", raw[: len(raw) // 2 * 2])
    step = int(8000 * window)
    energy = [sum(map(abs, samples[i:i + step])) for i in range(0, len(samples) - step, step)]
    if len(energy) < 10 or max(energy) == 0:
        return None
    first = len(energy) // 10   # skip the very start
    peak = max(range(first, len(energy)), key=energy.__getitem__)
    return (peak + 0.5) * window


def speeds(count: int) -> list[float]:
    """Playback speed per clip: faster and faster, the last (best) sticker slower so it gets its moment."""
    fast = [1.5 + 0.6 * k / max(count - 2, 1) for k in range(count - 1)]
    return [round(s, 2) for s in fast] + [1.2]


def plan(clips: list[Path]) -> dict:
    rewind = OPEN_HOLD + REWIND_STEP * len(clips)
    t, parts, landings = rewind, [], []
    for clip, rate in zip(clips, speeds(len(clips))):
        natural = duration(clip)
        length = natural / rate
        peak = loudest_moment(clip)
        landing = peak / rate if peak is not None and peak > 0.15 * natural else 0.72 * length
        parts.append({"file": clip, "rate": rate, "start": t, "length": length, "audio": has_audio(clip)})
        landings.append(t + landing)
        t += length
    return {"rewind": rewind, "parts": parts, "landings": landings, "total": t + END_HOLD}


def frame_at(video: Path, out: Path, last: bool) -> Path:
    seek = ["-sseof", "-0.1"] if last else ["-ss", "0"]
    subprocess.run(["ffmpeg", "-y", "-v", "error", *seek, "-i", str(video), "-frames:v", "1", "-q:v", "2", str(out)],
                   check=True)
    return out


def render_reel(post_dir: Path, clips: list[Path], layers: dict) -> dict:
    """`layers`: {"hook": png, "counters": [one png per sticker], "shop": png}, full-frame transparent overlays.
    Writes reel.mp4 and overlays/state_<k>.jpg (the surface with k stickers). Returns the timeline."""
    p = plan(clips)
    n, total, landings = len(clips), p["total"], p["landings"]
    work = post_dir / "overlays"
    work.mkdir(exist_ok=True)
    states = [frame_at(clips[0], work / "state_0.jpg", last=False)]
    states += [frame_at(clip, work / f"state_{k}.jpg", last=True) for k, clip in enumerate(clips, start=1)]

    rel = lambda path: Path(path).resolve().relative_to(post_dir.resolve()).as_posix()
    inputs, graph, pieces = [], [], []

    def add_input(*args) -> int:
        inputs.extend(args)
        return inputs.count("-i") - 1

    def still(path: Path, seconds: float, label: str) -> None:
        i = add_input("-framerate", str(FPS), "-loop", "1", "-t", f"{seconds:.3f}", "-i", rel(path))
        graph.append(f"[{i}:v]{FIT},fps={FPS},format=yuv420p[{label}]")
        pieces.append(f"[{label}]")

    # Picture: the finished surface, rewind steps back to empty, the clips, the hold (= the first picture: the loop).
    still(states[n], OPEN_HOLD, "r0")
    for j, k in enumerate(range(n - 1, -1, -1), start=1):
        still(states[k], REWIND_STEP, f"r{j}")
    for k, part in enumerate(p["parts"]):
        part["input"] = add_input("-i", rel(part["file"]))
        graph.append(f"[{part['input']}:v]{FIT},setpts=PTS/{part['rate']:.3f},fps={FPS},"
                     f"trim=duration={part['length']:.3f},setpts=PTS-STARTPTS,format=yuv420p[c{k}]")
        pieces.append(f"[c{k}]")
    still(states[n], END_HOLD, "hold")
    graph.append("".join(pieces) + f"concat=n={len(pieces)}:v=1:a=0[base]")

    # Overlays: the hook, the counter (it ticks on each slap), the shop line once the last sticker has landed.
    windows = [(layers["hook"], 0.0, HOOK_END)]
    windows += [(png, landings[k], landings[k + 1] if k + 1 < n else total) for k, png in enumerate(layers["counters"])]
    windows.append((layers["shop"], landings[-1] + 0.15, total))
    last = "base"
    for j, (png, t0, t1) in enumerate(windows):
        i = add_input("-framerate", str(FPS), "-loop", "1", "-t", f"{total:.3f}", "-i", rel(png))
        fades = "" if t0 == 0 else f",fade=t=in:st={t0:.3f}:d=0.12:alpha=1"
        if j == 0:
            fades += f",fade=t=out:st={t1 - 0.25:.3f}:d=0.25:alpha=1"
        graph.append(f"[{i}:v]format=rgba{fades}[ov{j}]")
        graph.append(f"[{last}][ov{j}]overlay=0:0:enable='between(t,{t0:.3f},{t1:.3f})'[v{j}]")
        last = f"v{j}"
    graph.append(f"[{last}]format=yuv420p[vout]")

    # Sound: each clip's own sound at its speed; the opening plays the whole build backwards, very fast (rewind).
    sounds = []
    for k, part in enumerate(p["parts"]):
        length = f"{part['length']:.3f}"
        if part["audio"]:
            graph.append(f"[{part['input']}:a]aresample=48000,aformat=channel_layouts=stereo,atempo={part['rate']:.3f},"
                         f"apad=whole_dur={length},atrim=duration={length}[ca{k}]")
        else:
            graph.append(f"anullsrc=r=48000:cl=stereo,atrim=duration={length}[ca{k}]")
        sounds.append(f"[ca{k}]")
    build = sum(part["length"] for part in p["parts"])
    rewind = p["rewind"]
    graph.append("".join(sounds) + f"concat=n={n}:v=0:a=1,asplit=2[build][back]")
    graph.append(f"[back]areverse,atempo={min(build / rewind, 100):.3f},apad=whole_dur={rewind:.3f},"
                 f"atrim=duration={rewind:.3f},volume=0.7,afade=t=out:st={rewind - 0.1:.3f}:d=0.1[rw]")
    graph.append(f"[rw][build]concat=n=2:v=0:a=1,apad=whole_dur={total:.3f},atrim=duration={total:.3f},"
                 "loudnorm=I=-14:TP=-1.5:LRA=11[aout]")

    out = post_dir / "reel.mp4"
    for crf in (19, 24):
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
    log.info(f"Reel: {total:.1f}s, {out.stat().st_size / 1e6:.1f} MB; stickers land at "
             + ", ".join(f"{t:.1f}s" for t in landings))
    return p
