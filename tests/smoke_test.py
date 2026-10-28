"""Offline end-to-end test of the agent: no keys, no internet, no cost.

Runs a full carousel and a full reel (research -> copy -> visuals -> quality checks -> design/edit -> publish) with
stand-ins for Claude, Higgsfield, Instagram and GitHub, using generated placeholder images and clips.
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

from agent import copywriter, costs, higgsfield, pipeline, research, state, tokens, video  # noqa: E402
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


def green_screen_sticker(path: Path, size: int = 1024) -> None:
    """A die-cut sticker on a green screen, with green inside its artwork (which must survive the cut-out)."""
    img = Image.new("RGB", (size, size), (0, 255, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle((200, 220, 820, 800), 120, fill="white")
    d.rounded_rectangle((236, 256, 784, 764), 100, fill=(40, 200, 60))
    d.ellipse((380, 420, 440, 480), fill="black")
    d.ellipse((580, 420, 640, 480), fill="black")
    img.save(path, "PNG")


def with_engine(engine: str) -> dict:
    return {**cfg, "formats": {**cfg["formats"], "reel": {**cfg["formats"]["reel"], "engine": engine}}}


# ---------------------------------------------------------------------------------------------- stand-ins
class FakeClaude:
    themes = 0

    def __init__(self, *args, **kwargs):
        self.cost = 0.1

    def ask_json(self, system, prompt, schema):
        props = schema["properties"]
        if "x0" in props:  # where the target area is on the photo
            assert isinstance(prompt, list) and prompt[0]["type"] == "image"
            return {"x0": 120, "y0": 260, "x1": 880, "y1": 720}
        if "ok" in props:  # quality check of an edit, a clip or a cut-out: it must be shown pictures
            assert isinstance(prompt, list) and any(block["type"] == "image" for block in prompt)
            return {"ok": True, "score": 9, "issues": []}
        assert "stickerul.tau" in system and "Romanian" in system
        if "chosen" in props:
            FakeClaude.themes += 1   # a new theme each time, so every post gets its own folder
            return {"ideas": [{"theme": "t", "angle": "a", "pillar": "p", "score": 8}],
                    "chosen": {"theme": f"Stickere pentru programatori {FakeClaude.themes}", "angle": "deploy vinerea",
                               "pillar": "Profesii", "occasion": "", "why": "test"}}
        common = {"caption": "Hook de test\nA doua linie", "hashtags": ["stickere", "#Programare", "#dev ops"]}
        if "items" in props:
            materials = ["holografic", "EPOXY 3d", "unknown finish", "vinil mat", "transparent", "vinil lucios"]
            items = [{"name": f"Stickerul ş {i}", "line": "O replică de test ţ", "design": "a cute cat",
                      "material": materials[i - 1], "alt_text": "alt"} for i in range(1, 7)]
            return {"kicker": "PACHETUL ZILEI", "title": "Stickere pentru *devii* de vineri", "items": items,
                    "mockup_scene": "a car's rear window", "mockup_label": "Așa arată pe mașină",
                    "cta_title": "Care e preferatul tău?", "cta_sub": "Scrie numărul",
                    "shop_cta": "Le vrei pe mașină? Le printăm și holografic", **common}
        materials = ["vinil lucios", "holografic", "Vinil lucios", "EPOXY 3d", "transparent", "vinil mat"]
        stickers = [{"name": f"Stickerul ţ {i}", "design": "a cute cat", "material": materials[i - 1]}
                    for i in range(1, cfg["formats"]["reel"]["stickers"] + 1)]
        return {"hook": "Ultimul e pentru tine", "surface": "the lid of a closed matte black laptop on a walnut desk",
                "target": "the laptop lid", "stickers": stickers, "shop_cta": "", **common}


class FakeHiggsfield:
    def __init__(self):
        self.spent = 0.0

    def generate(self, chain, prompt, out, kind="image", required=None, extra=None, refs=None):
        out.parent.mkdir(parents=True, exist_ok=True)
        if kind == "video":
            # A clip from the scene before to the scene after, with a "slap" (loud moment) at 2 s.
            assert required["first_frame_url"].startswith("https://") and required["last_frame_url"] != required["first_frame_url"]
            seconds = required["duration"]
            assert seconds == cfg["formats"]["reel"]["clip_seconds"]
            last = out.parent / required["last_frame_url"].rsplit("/", 1)[-1]
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-loop", "1", "-i", str(last),
                            "-f", "lavfi", "-i", f"sine=frequency=700:duration={seconds}",
                            "-filter_complex", "[0:v]scale=1080:1912,fps=24,format=yuv420p[v];"
                            "[1:a]volume='if(between(t,2,2.15),1,0.03)':eval=frame[a]",
                            "-map", "[v]", "-map", "[a]", "-t", str(seconds), "-c:v", "libx264", "-c:a", "aac",
                            str(out)], check=True)
        else:
            if out.stem == "mockup":
                assert refs, "the mockup needs the sticker images as references"
            if out.stem.startswith("scene_") and out.stem != "scene_00":
                assert refs and len(refs) == 1, "each reel edit starts from the previous picture"
            if out.stem.startswith("sticker_"):
                green_screen_sticker(out)
            else:
                size = (720, 1280) if out.stem.startswith("scene_") else (1152, 1536)
                placeholder_sticker(out, hash(out.stem) % 1000, size)
        self.spent += 0.01
        return {"path": str(out), "url": f"https://cdn.example/{out.name}", "model": chain[0]["id"], "usd": 0.01}


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


costs.LEDGER = TMP / "costs.jsonl"   # never write to the real cost log
pipeline.Claude, pipeline.Higgsfield = FakeClaude, FakeHiggsfield
pipeline.Instagram, pipeline.GitHubMediaHost = FakeInstagram, FakeMediaHost
pipeline.OUTPUT = TMP / "output"
state.HISTORY = TMP / "history.json"
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
        hf.estimate = lambda model, arguments: 0.05  # no network
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

        costs.LEDGER.unlink(missing_ok=True)
        costs.set_post("p1")
        costs.record("higgsfield", "model-a", 0.5)
        costs.record("anthropic", "claude", 0.1)
        assert costs.total(post="p1") == 0.6 and costs.total() == 0.6 and "of $60.00 budget" in costs.report(60)
        try:
            pipeline.create({**cfg, "budget": {"monthly_usd": 0.5}}, "carousel")
            raise AssertionError("the budget cap did not stop the post")
        except RuntimeError as exc:
            assert "budget" in str(exc)
        print("ok  cost ledger and monthly budget cap")

        # Full runs
        shop = "@" + cfg["page"]["shop_handle"]
        for fmt, run_cfg in (("carousel", cfg), ("reel", with_engine("ai_clips")), ("reel", with_engine("placed"))):
            post_dir = pipeline.create(run_cfg, fmt)
            pipeline.publish(run_cfg, post_dir)
            post = json.loads((post_dir / "post.json").read_text(encoding="utf-8"))
            copy = json.loads((post_dir / "copy.json").read_text(encoding="utf-8"))
            assert post["published"]["permalink"].startswith("https://www.instagram.com/")
            assert copy["shop_cta"].endswith(shop) or copy["shop_cta"] == cfg["page"]["cta_line"]
            label = fmt
            if fmt == "carousel":
                assert [i["material"] for i in copy["items"]] == \
                    ["holografic", "epoxy 3D", "vinil lucios", "vinil mat", "transparent"], copy["items"]
            else:
                n, engine = cfg["formats"]["reel"]["stickers"], run_cfg["formats"]["reel"]["engine"]
                label = f"reel ({engine})"
                # every sticker in a different material: the repeated "vinil lucios" became "vinil mat"
                assert [s["material"] for s in copy["stickers"]] == ["vinil lucios", "holografic", "vinil mat", "epoxy 3D"]
                assert post["qa_ok"] and abs(video.duration(post_dir / "reel.mp4") - post["length_s"]) < 0.2
                assert 6 <= post["length_s"] <= 11, post["length_s"]
                assert all((post_dir / "overlays" / f"state_{k}.jpg").exists() for k in range(n + 1))
                if engine == "ai_clips":
                    timeline = video.plan([post_dir / "media" / f"clip_{k:02d}.mp4" for k in range(1, n + 1)])
                    first = timeline["parts"][0]
                    assert abs(timeline["landings"][0] - (first["start"] + 2.07 / first["rate"])) < 0.1  # on the slap
                else:
                    media = json.loads((post_dir / "media.json").read_text(encoding="utf-8"))
                    assert media["engine"] == "placed" and media["box"] == [0.12, 0.26, 0.88, 0.72]
                    cut = Image.open(post_dir / "media" / "sticker_01_cut.png")
                    assert cut.getpixel((0, 0))[3] == 0, "the green screen must be cut away"
                    assert cut.getpixel((cut.width // 2, cut.height // 2))[3] == 255, "green inside the sticker stays"
            print(f"ok  {label}: {len(post['media'])} file(s), shop line \"{copy['shop_cta']}\"")
        assert len(published["carousel"]) == 2 + cfg["formats"]["carousel"]["items"] + 1  # cover, items, mockup, cta
        assert [h["format"] for h in state.load()] == ["carousel", "reel", "reel"]

        # A reel that failed the quality check is published only with --force.
        post = json.loads((post_dir / "post.json").read_text(encoding="utf-8"))
        post.pop("published")
        post["qa_ok"] = False
        (post_dir / "post.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        try:
            pipeline.publish(cfg, post_dir)
            raise AssertionError("a reel that failed the quality check was published")
        except RuntimeError as exc:
            assert "quality check" in str(exc)
        assert pipeline.publish(cfg, post_dir, force=True)["permalink"]
        print("ok  quality gate: a reel that failed the check needs --force")

        # remake: new visuals for an unpublished post, same text
        again = post_dir.with_name(post_dir.name + "_again")
        shutil.copytree(post_dir, again)
        post = json.loads((again / "post.json").read_text(encoding="utf-8"))
        post.pop("published")
        (again / "post.json").write_text(json.dumps(post, ensure_ascii=False), encoding="utf-8")
        pipeline.remake(run_cfg, again)
        remade = json.loads((again / "post.json").read_text(encoding="utf-8"))
        assert remade["cost_usd"] > post["cost_usd"] and remade["qa_ok"] and (again / "reel.mp4").exists()
        try:
            pipeline.remake(cfg, post_dir)
            raise AssertionError("a published post was remade")
        except RuntimeError as exc:
            assert "already published" in str(exc)
        print("ok  remake: new visuals for the same text, never for a published post")
        print("\nALL CHECKS PASSED")
        return 0
    finally:
        if "--keep" in sys.argv:
            print(f"Output kept in {TMP}")
        else:
            shutil.rmtree(TMP, ignore_errors=True)


if __name__ == "__main__":
    sys.exit(main())
