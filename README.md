# Stickerul Zilei: Instagram content agent

Runs the Instagram page [@stickerul.zilei](https://www.instagram.com/stickerul.zilei/) on autopilot: original sticker
designs every day, turned into polished posts that send buyers to [@stickerul.tau](https://www.instagram.com/stickerul.tau/).

```
Topic research ─► Copy ─► Visuals ─► Design & edit ─► Publish ─► (repeats on schedule)
Claude + trends   Claude   Higgsfield  brand templates   Instagram API
                           + Claude quality check
```

| What | When (Romania time) | Made of |
|---|---|---|
| Carousel: a themed pack of 5 sticker designs | every day, 19:00 | cover, 5 numbered stickers (each in one of the shop's materials: glossy, matte, holographic, transparent, electrostatic, epoxy 3D), a real-life mockup (laptop, car, shop window…), "pick your favorite" slide |
| Reel: 4 stickers for the day's theme land one by one on a surface that fits it | every Friday, 20:00 (that day's carousel still comes at 19:00) | about 9 s, no voiceover: opens on the finished result and rewinds, a hook that only the last sticker answers, a 1/4 → 4/4 counter with each sticker's material (all different), funnier and funnier up to a punchline sticker that catches the light, ends where it began so it loops; every landing filmed by AI (Kling O3) with its own slap sound and checked by Claude |

It runs on **GitHub Actions**, so no computer needs to be on. Each run picks a fresh theme from upcoming occasions,
today's Google Trends in Romania and the post history, so themes don't repeat. Cost at Higgsfield's real rates:
about **$1.15 per carousel** (≈ $35/month for the daily carousel) and about $2.20–3.30 per weekly reel. Every paid call is
logged with its real price in `state/costs.jsonl` (`run.py costs` shows the month), and `budget.monthly_usd` in
`config/page.yaml` ($60) stops new posts once a month's spend reaches it. Instagram's API and GitHub Actions are free.

## Documentation

- **[docs/SETUP.md](docs/SETUP.md)**: set everything up from zero (Instagram page, Meta app and token, Claude and
  Higgsfield keys, install, deploy) and the inventory of what exists today.
- **[docs/OPERATIONS.md](docs/OPERATIONS.md)**: where the secrets live and how to update them, changing content or
  schedule, reviewing posts, costs, troubleshooting, moving to a new computer.
- **[docs/CLOUDFLARE_R2.md](docs/CLOUDFLARE_R2.md)**: the planned (not yet active) move of media hosting from
  jsDelivr to Cloudflare R2: why, Cloudflare setup and switch-over steps.

## Everyday commands (PowerShell, in the project folder)

| Command | What it does |
|---|---|
| `.\.venv\Scripts\python.exe run.py check` | checks every key, the Instagram account, media hosting, FFmpeg and fonts |
| `.\.venv\Scripts\python.exe run.py create --format carousel` | makes a post in `output/` without publishing (`--format reel` for a reel) |
| `.\.venv\Scripts\python.exe run.py publish output\<folder>` | publishes a post made earlier (then push `state/`, see OPERATIONS) |
| `.\.venv\Scripts\python.exe run.py render output\<folder>` | re-renders slides or the reel after you edit its `copy.json` |
| `.\.venv\Scripts\python.exe run.py remake output\<folder>` | makes an unpublished post's pictures or clips again, same text (for a reel that failed the quality check) |
| `.\.venv\Scripts\python.exe run.py costs` | spend this month (by model and by post) against the monthly budget |
| `.\.venv\Scripts\python.exe tests\smoke_test.py` | offline end-to-end test: no keys, no internet, no cost |
| `powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1` | prepares a computer (Python environment, packages, `.env`) |
| `powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1` | first deployment to GitHub (safe to re-run) |
| `powershell -ExecutionPolicy Bypass -File scripts\update-secrets.ps1` | sends changed keys or a new Instagram token to GitHub |

## Project layout

```
run.py                       command line
config/page.yaml             the page's brief: audience, voice, pillars, occasions, palettes, models
agent/research.py            1. topic research (occasions, Google Trends, history) with Claude
agent/copywriter.py          2. sticker concepts, slide text, reel hook, caption, hashtags
agent/visuals.py             3. image and video prompts -> Higgsfield API (agent/higgsfield.py)
agent/quality.py             3. Claude checks every reel sticker (or edit and clip) before it is used
agent/design.py              4. brand templates: carousel slides, reel overlays, covers
agent/video.py               4. reel editing (FFmpeg): rewind opener, sped-up clips, overlays, loop
agent/animate.py             4. reel with the "placed" engine: cuts the stickers out, places and animates them
agent/hosting.py             5. public media URLs (the repo's `media` branch, served by jsDelivr)
agent/instagram.py, tokens.py           5. publishing and Instagram token renewal
agent/costs.py               cost log (state/costs.jsonl) and the monthly budget
state/                       post history, cost log and the encrypted Instagram token (committed by the schedule)
assets/                      brand fonts (OFL), profile picture, slap sounds (for the "placed" reel engine)
.github/workflows/autopost.yml          the schedule
scripts/                     setup, deploy and secret-update scripts
tests/smoke_test.py          offline end-to-end test
```
