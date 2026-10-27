"""Offline end-to-end test of the agent: no keys, no internet, no cost.

Runs a full carousel and a full reel (research -> copy -> visuals -> design/edit -> publish) with stand-ins for
Claude, Higgsfield, the voice service, Instagram and GitHub, using generated placeholder images and clips.
Needs Python packages from requirements.txt and FFmpeg.

    .venv\\Scripts\\python.exe tests\\smoke_test.py          (add --keep to inspect the output folder)
"""
from __future__ import annotations

import datetime as dt
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
TMP = Path(tempfile.mkdtemp(prefix="agent-smoke-"))
os.environ.update(HF_API_KEY_ID="test-id", HF_API_KEY_SECRET="test-secret")

from agent import copywriter, higgsfield, pipeline, research, state, tokens, voice  # noqa: E402
from agent.settings import load_config  # noqa: E402

cfg = load_config()
COLORS = ["#FF5C39", "#0FA37F", "#7B5CFF", "#F29A00", "#2F7DED", "#E8457C"]


def placeholder_sticker(path: Path, seed: int, size=(1152, 1536)) -> None:
    rnd = random.Random(seed)
    img = Image.new("RGB", size, (227, 218, 255))
    d = ImageDraw.Draw(img)
    w, h = size
    box = (w * 0.25, h * 0.3, w * 0.75, h * 0.66)
    d.rounded_rectangle([box[0] - 18, box[1] - 18, box[2] + 18, box[3] + 18], 120, fill="white")
    d.rounded_rectangle(box, 100, fill=rnd.choice(COLORS))
    d.ellipse((w * 0.4, h * 0.42, w * 0.44, h * 0.45), fill="black")
    d.ellipse((w * 0.56, h * 0.42, w * 0.6, h * 0.45), fill="black")
    img.save(path)


# ---------------------------------------------------------------------------------------------- stand-ins
class FakeClaude:
    def __init__(self, *args, **kwargs):
        self.cost = 0.1

    def ask_json(self, system, prompt, schema):
        assert "stickerul.tau" in system and "Romanian" in system
        props = schema["properties"]
        if "chosen" in props:
            return {"ideas": [{"theme": "t", "angle": "a", "pillar": "p", "score": 8}],
                    "chosen": {"theme": "Stickere pentru programatori", "angle": "deploy vinerea",
                               "pillar": "Profesii", "occasion": "", "why": "test"}}
        common = {"caption": "Hook de test\nA doua linie", "hashtags": ["stickere", "#Programare", "#dev ops"]}
        if "items" in props:
            items = [{"name": f"Stickerul ş {i}", "line": "O replică de test ţ", "design": "a cute cat",
                      "alt_text": "alt"} for i in range(1, 7)]
            return {"kicker": "PACHETUL ZILEI", "title": "Stickere pentru *devii* de vineri", "items": items,
                    "mockup_scene": "a laptop", "mockup_label": "Așa arată pe laptop",
                    "cta_title": "Care e preferatul tău?", "cta_sub": "Scrie numărul", **common}
        clips = [{"name": f"Clip {i}", "design": "d", "surface": "desk", "target": "laptop",
                  "narration": "O replică de test pentru acest clip."} for i in range(1, 4)]
        return {"hook": "Trei stickere de test", "cta": "Scrie preferatul în comentarii", "clips": clips,
                "end_title": "Care e preferatul tău?", "end_sub": "Scrie numărul", **common}


class FakeHiggsfield:
    def __init__(self):
        self.spent = 0.0

    def generate(self, chain, prompt, out, kind="image", required=None, extra=None, refs=None):
        out.parent.mkdir(parents=True, exist_ok=True)
        if kind == "video":
            assert required and required["image_url"].startswith("https://")
            frame = out.with_name(out.name.replace("clip_", "frame_").replace(".mp4", ".jpg"))
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(frame), "-t", "5",
                            "-vf", "scale=1080:1920,fps=30", "-pix_fmt", "yuv420p", str(out)], check=True)
        else:
            if out.stem == "mockup":
                assert refs, "the mockup needs the sticker images as references"
            placeholder_sticker(out, hash(out.stem) % 1000)
        self.spent += 0.01
        return {"path": str(out), "url": f"https://cdn.example/{out.name}", "model": chain[0]["id"]}


def fake_voice(lines, voice_name, rate, folder):
    folder.mkdir(parents=True, exist_ok=True)
    segments = []
    for i, text in enumerate(lines):
        words = text.split()
        length = 0.4 * len(words) + 0.3
        out = folder / f"voice_{i:02d}.mp3"
        subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-f", "lavfi", "-i", "anullsrc=r=24000:cl=mono",
                        "-t", f"{length:.2f}", str(out)], check=True)
        timings = [(0.1 + 0.4 * j, 0.45 + 0.4 * j, w) for j, w in enumerate(words)]
        segments.append({"file": out.name, "text": text, "duration": length, "words": timings})
    return segments


published = {}


class FakeInstagram:
    account = {"username": "stickerul.zilei", "account_type": "MEDIA_CREATOR"}

    def refresh_if_needed(self):
        pass

    def quota_left(self):
        return 100

    def publish_carousel(self, urls, caption, alt_texts, collaborators):
        assert len(urls) == len(alt_texts) and all(u.endswith(".jpg") for u in urls)
        published["carousel"] = urls
        return {"media_id": "1", "permalink": "https://www.instagram.com/p/TEST/"}

    def publish_reel(self, video_url, caption, cover_url, collaborators):
        assert video_url.endswith("reel.mp4") and cover_url.endswith("cover.jpg")
        published["reel"] = video_url
        return {"media_id": "2", "permalink": "https://www.instagram.com/reel/TEST/"}


class FakeMediaHost:
    def publish(self, files, message):
        assert all(Path(p).exists() for p in files.values())
        return {name: f"https://cdn.jsdelivr.net/gh/owner/repo@sha/{name}" for name in files}


pipeline.Claude, pipeline.Higgsfield = FakeClaude, FakeHiggsfield
pipeline.Instagram, pipeline.GitHubMediaHost = FakeInstagram, FakeMediaHost
pipeline.OUTPUT = TMP / "output"
state.HISTORY = TMP / "history.json"
voice.synthesize = fake_voice
research.google_trends = lambda *args, **kwargs: []


def main() -> int:
    try:
        # Small units
        occasions = research.upcoming_occasions(cfg["page"]["occasions"], dt.date(2026, 10, 27))
        assert occasions and "Halloween" in occasions[0]
        assert copywriter.clean_hashtags(["stickere", "#dev ops"], ["#stickere"]) == ["#stickere", "#devops"]
        assert copywriter.fix_ro("şţ") == "șț"
        print("ok  occasions, hashtags, Romanian letters")

        hf = higgsfield.Higgsfield()
        calls = []

        def fake_submit(model, arguments):
            calls.append(dict(arguments))
            if model == "missing/model":
                raise higgsfield.ModelRejected("missing/model: HTTP 404")
            if "aspect_ratio" in arguments:
                raise higgsfield.ModelRejected("HTTP 422 aspect_ratio")
            return {"request_id": "r", "status_url": "u"}

        hf.submit = fake_submit
        hf.wait = lambda job, timeout, interval: {"status": "completed", "images": [{"url": "https://x/i.png"}]}
        hf.download = lambda url, path: path
        result = hf.generate([{"id": "missing/model"}, {"id": "good/model", "max_refs": 2}], "p", TMP / "a.jpg",
                             extra={"aspect_ratio": "3:4"}, refs=["r1", "r2", "r3"])
        assert result["model"] == "good/model" and "aspect_ratio" not in calls[-1]
        assert calls[-1]["image_urls"] == ["r1", "r2"]
        print("ok  model fallback, optional settings, reference limit")

        tokens.ENCRYPTED, tokens.PLAIN = TMP / "t.enc", TMP / "t.json"
        os.environ["TOKEN_KEY"] = tokens.new_key()
        os.environ["IG_ACCESS_TOKEN"] = "IGAA-test-1"
        data = tokens.load()
        data["refreshed_at"] = 123
        tokens.save(data)
        assert tokens.read_encrypted()["refreshed_at"] == 123 and b"IGAA" not in tokens.ENCRYPTED.read_bytes()
        os.environ["IG_ACCESS_TOKEN"] = "IGAA-test-2"
        assert tokens.load()["access_token"] == "IGAA-test-2"
        print("ok  encrypted token storage")

        # Full runs
        for fmt in ("carousel", "reel"):
            post_dir = pipeline.create(cfg, fmt)
            pipeline.publish(cfg, post_dir)
            post = json.loads((post_dir / "post.json").read_text(encoding="utf-8"))
            assert post["published"]["permalink"].startswith("https://www.instagram.com/")
            print(f"ok  {fmt}: {len(post['media'])} file(s) -> {post['published']['permalink']}")
        assert len(published["carousel"]) == 2 + cfg["formats"]["carousel"]["items"] + 1  # cover, items, mockup, cta
        assert [h["format"] for h in state.load()] == ["carousel", "reel"]
        print("\nALL CHECKS PASSED")
        return 0
    finally:
        if "--keep" in sys.argv:
            print(f"Output kept in {TMP}")
        else:
            shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
