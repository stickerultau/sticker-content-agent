# Stickerul Zilei: Instagram content agent

Runs the Instagram page [@stickerul.zilei](https://www.instagram.com/stickerul.zilei/) on autopilot: original sticker
designs every day, turned into polished posts that send buyers to [@stickerul.tau](https://www.instagram.com/stickerul.tau/).

```
Topic research ─► Copy ─► Visuals ─► Design & edit ─► Publish ─► (repeats on schedule)
Claude + trends   Claude   Higgsfield  brand templates   Instagram API
                                       + voice + captions
```

| What | When (Romania time) | Made of |
|---|---|---|
| Carousel: a themed pack of 5 sticker designs | every day, 19:00 | cover, 5 numbered stickers (each in one of the shop's materials: glossy, matte, holographic, transparent, electrostatic, epoxy 3D), a real-life mockup (laptop, car, shop window…), "pick your favorite" slide |
| Reel: 3 stickers peeled and stuck on objects | Tue, Thu, Sat, 13:00 | AI video clips, Romanian voiceover, animated captions, end card |

It runs on **GitHub Actions**, so no computer needs to be on. Each run picks a fresh theme from upcoming occasions,
today's Google Trends in Romania and the post history, so themes don't repeat. Cost: about **$8–15/month**
(Claude ≈ $0.10 per post, Higgsfield ≈ $0.05–0.20 per carousel and ≈ $0.40–0.60 per reel; Instagram's API,
GitHub Actions and the voiceover are free).

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)**: set everything up from zero (Instagram page, Meta app and token, Claude and
  Higgsfield keys, install, deploy) and the inventory of what exists today.
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)**: where the secrets live and how to update them, changing content or
  schedule, reviewing posts, costs, troubleshooting, moving to a new computer.

## Everyday commands (PowerShell, in the project folder)

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python.exe run.py check` | checks every key, the Instagram account, media hosting, FFmpeg and fonts |
| `.\.venv\Scripts\python.exe run.py create --format carousel` | makes a post in `output/` without publishing (`--format reel` for a reel) |
| `.\.venv\Scripts\python.exe run.py publish output\<folder>` | publishes a post made earlier (then push `state/`, see OPERATIONS) |
| `.\.venv\Scripts\python.exe run.py render output\<folder>` | re-renders slides or the reel after you edit its `copy.json` |
| `.\.venv\Scripts\python.exe tests\smoke_test.py` | offline end-to-end test: no keys, no internet, no cost |
| `powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1` | prepares a computer (Python environment, packages, `.env`) |
| `powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1` | first deployment to GitHub (safe to re-run) |
| `powershell -ExecutionPolicy Bypass -File scripts\update-secrets.ps1` | sends changed keys or a new Instagram token to GitHub |

## Project layout

```
run.py                       command line
config/page.yaml             the page's brief: audience, voice, pillars, occasions, palettes, models
agent/research.py            1. topic research (occasions, Google Trends, history) with Claude
agent/copywriter.py          2. sticker concepts, slide text, voiceover lines, caption, hashtags
agent/visuals.py             3. image and video prompts -> Higgsfield API (agent/higgsfield.py)
agent/design.py              4. brand templates: carousel slides, reel overlays, covers
agent/video.py, voice.py, captions.py   4. reel editing (FFmpeg), voiceover, word-by-word captions
agent/hosting.py             5. public media URLs (the repo's `media` branch, served by jsDelivr)
agent/instagram.py, tokens.py           5. publishing and Instagram token renewal
state/                       post history and the encrypted Instagram token (committed by the schedule)
assets/                      brand fonts (OFL), profile picture, optional music
.github/workflows/autopost.yml          the schedule
scripts/                     setup, deploy and secret-update scripts
tests/smoke_test.py          offline end-to-end test
```
