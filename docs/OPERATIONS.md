# Operations

How the automation runs, where its secrets live, and how to change, update, fix or move it.

## How a scheduled run works

GitHub Actions starts `.github/workflows/autopost.yml` on schedule (carousel daily 17:00 UTC; reel every Friday
18:00 UTC; Romania is UTC+2 in winter and UTC+3 in summer). Each run:

1. installs FFmpeg and the Python packages;
2. runs `python run.py post --format carousel|reel`:
   **topic research → copy → visuals (Higgsfield) → design & edit → publish** (media goes to the repo's `media`
   branch, then the Instagram API publishes it, labeled as AI content). For reels, Claude checks every edit and clip
   and has a failed one made again; a reel that still fails is not published;
3. commits `state/` (post history, the cost log and, when renewed, the encrypted Instagram token);
4. keeps the post's files as a downloadable artifact for 14 days.

Watch it under **GitHub → Actions**: each run's summary shows a preview, the caption and the Instagram link.
GitHub emails you when a scheduled run fails.

## Secrets

### Where they live

| Name | On your PC | On GitHub | Used for |
|---|---|---|---|
| `ANTHROPIC_API_KEY` | `.env` | Actions secret | Claude |
| `HF_API_KEY_ID`, `HF_API_KEY_SECRET` | `.env` | Actions secrets | Higgsfield |
| `IG_ACCESS_TOKEN` | `.env` (the token you generated) | not a secret: stored **encrypted** in `state/ig_token.enc` in the repo, renewed weekly by the agent | Instagram |
| `TOKEN_KEY` | `.env` | Actions secret | decrypts `state/ig_token.enc` |
| `MEDIA_REPO` | `.env` | not needed (the workflow knows its own repo) | where local runs host media |
| GitHub token | your `gh` login | automatic `GITHUB_TOKEN` | commits state, updates the `media` branch |

GitHub secrets page: <https://github.com/stickerultau/sticker-content-agent/settings/secrets/actions>.
Secrets there can be **replaced but never viewed**, so keep the `.env` values in a password manager.
`.env` is gitignored and never uploaded.

### Change a key (Claude or Higgsfield)

1. Create the new key at the provider, then revoke the old one.
2. Put it in `.env`.
3. Run `powershell -ExecutionPolicy Bypass -File scripts\update-secrets.ps1`.

Without the script: GitHub → Settings → Secrets and variables → Actions → click the secret → **Update secret**, or
`gh secret set ANTHROPIC_API_KEY --repo stickerultau/sticker-content-agent` (it asks for the value).

### Replace the Instagram token

Needed if you remove the app's access on Instagram, Instagram asks you to log in again, or the token expired. It
expires if nothing is published for 60 days (for example, while the workflow is paused), since renewal happens on
each post.

1. Generate a new token ([SETUP.md, step 2.6](SETUP.md#2-meta-developer-app-and-instagram-token)).
2. Put it in `.env` as `IG_ACCESS_TOKEN`.
3. Run `scripts\update-secrets.ps1`: it gets the latest state, re-encrypts the token, pushes it and refreshes the
   secrets.

### If `TOKEN_KEY` is lost or leaked

Delete the `TOKEN_KEY` line from `.env`, put a fresh `IG_ACCESS_TOKEN` in `.env`, run
`.\.venv\Scripts\python.exe run.py seal-token` (creates a new key), then `scripts\update-secrets.ps1`.

## Changing what gets posted

| To change | Edit, then commit and push |
|---|---|
| Tone, topics, rules, occasions, hashtags, colors, stickers per post | `config/page.yaml` |
| What the shop offers: surfaces mentioned in captions and closing slides, and the materials stickers are shown in (glossy and matte vinyl, holographic, transparent, epoxy 3D, electrostatic) | `page.shop_offer` in `config/page.yaml`; each material has a Romanian name (shown on the slide), an English description (for the image model) and an optional hint telling Claude when to use it |
| Fallback shop line (used only if a post has none) | `page.cta_line` |
| Posting times or days | the `cron` lines in `.github/workflows/autopost.yml`; the "Decide what to post" step maps each time to a format |
| How reel stickers land | `formats.reel.engine`: `"ai_clips"` (chosen: each landing filmed by Kling O3 with its own sound, stickers never overlap, ≈ $2.20–3.30 a reel) or `"placed"` (each sticker made alone on a green screen, cut out, placed and animated by code: always-correct layering, ≈ $1.15 a reel, a more designed look) |
| Hook, escalation and payoff rules | the reel prompt in `agent/copywriter.py` (`write_reel`): the hook opens a question only the last sticker answers, the designs get funnier up to a punchline, every sticker has a different material |
| Stickers per reel | `formats.reel.stickers` (4; every one gets a different material) |
| How reels look and move | `"placed"`: the `CUTOUT` prompt in `agent/visuals.py`; timing, sizes, spots and shine at the top of `agent/animate.py`; slap sounds in `assets/sfx/`. `"ai_clips"`: the `SCENE`, `ADD_STICKER`, `LAND` prompts and `agent/video.py` |
| Pause or resume reels | put or remove `#` before the reel `cron` line in `.github/workflows/autopost.yml` |
| Image or video models | `models` in `config/page.yaml` (see [Models](#models)) |
| Make every post a collab with the shop | `page.collaborators: ["stickerul.tau"]` (the shop accepts each invite in the app) |

**Pause**: GitHub → Actions → Content Creation Agent → **⋯ → Disable workflow** (re-enable the same way).
Pausing longer than 60 days lets the Instagram token expire. To pause one format only, put `#` before its `cron`
line in the workflow.

## Review before posting and posting by hand

- **Review first**: `run.py create --format carousel` → check `output\<folder>\slides` (or `reel.mp4`) →
  `run.py publish output\<folder>`.
- **Fix a typo**: edit `output\<folder>\copy.json` → `run.py render output\<folder>` → publish.
- **A reel that failed the quality check** is not published. Watch `output\<folder>\reel.mp4` (Claude's notes are in
  `media.json`); if it looks fine, `run.py publish output\<folder> --force`. Otherwise `run.py remake output\<folder>`
  makes its pictures and clips again with the same theme and text (about $2), then check and publish it.
- **After publishing from your PC**, push `state/`. Otherwise the cloud doesn't know about the post and may repeat
  the theme:
  ```powershell
  git add state; git commit -m "chore: update agent state"; git pull --rebase; git push
  ```
- **From GitHub instead**: Actions → Content Creation Agent → **Run workflow** (pick the format; untick Publish to
  only create it and download it from the run's artifacts). The cloud saves `state/` by itself.

## Models

All images and videos come from the Higgsfield API. The list of what the API offers (it differs from the Higgsfield
app; Seedream, for example, is app-only):

```powershell
.\.venv\Scripts\python.exe -c "import requests; from agent.higgsfield import API, Higgsfield; [print(m['slug']) for m in requests.get(API + '/models', headers=Higgsfield().headers).json()['items']]"
```

A free way to check a model name: send it a request **without** a prompt. HTTP 400/422 means it exists, 404 means
it doesn't. Nothing is generated.

Current choices (verified 28 Oct 2026 with a side-by-side test of the same sticker on 6 models):

| Role | Model (tried in order) | Price |
|---|---|---|
| Sticker images (asked in 2:3, cropped into the 4:5 slide) | `marketing-studio/image` (best looking), `ideogram/v4.0`, `xai/grok-imagine-image-2.0` | $0.197 / $0.06 / $0.06 |
| Laptop mockup | `alibaba/qwen-image-3/edit` (accepts at most 3 reference images) | $0.04 |
| Reel surface | `marketing-studio/image` at 9:16, `ideogram/v4.0` | $0.21 / $0.06 |
| Reel stickers, `placed` engine (one green-screen picture each) | `marketing-studio/image` at 1:1, `resolution: 1k`; `ideogram/v4.0` | $0.188 / $0.06 |
| Reel stickers, `ai_clips` engine (one edit each) | `alibaba/qwen-image-3/edit`, `resolution: 2k` + `aspect_ratio: 9:16` (at 2k it returns squares without it) | $0.075 |
| Reel clips, `ai_clips` engine (one per sticker) | `kling-video/o3/first-last-frame`, 3 s with sound | $0.357 |

Prices are what Higgsfield's estimate endpoint (`POST https://api.higgsfield.ai/estimate/<model>`, free) returned
on 28 Oct 2026. The agent asks it for every generation and logs the answer. Marketing Studio's price depends on the
image shape: 2:3 (the carousel since 28 Oct 2026, 1360×2048 px) $0.197, 3:4 $0.277, 9:16 $0.21; `resolution: "1k"`
costs about half.

## The `media` branch

Instagram's API doesn't take file uploads: it downloads each image or video from a public link. Right before
posting, the agent replaces the `media` branch with a single commit holding only that post's files and hands
Instagram their jsDelivr links. The branch never shares history with `main`, never grows, and must never be merged.
GitHub may suggest "Compare & pull request" for it: ignore that. Deleting it is harmless; the next post recreates it.

## Costs and balances

Every paid call is logged in `state/costs.jsonl`: Higgsfield generations with the real price from the estimate
endpoint, Claude calls from their token counts. See the month, by model and by post:

```powershell
.\.venv\Scripts\python.exe run.py costs
```

Each run's log and GitHub summary show the post's cost and the month so far. `budget.monthly_usd` in
`config/page.yaml` (default $60) stops new posts once the month's logged spend reaches it; raise it to continue.
Typical costs: carousel ≈ $1.15 (5 images × $0.197, mockup $0.04, Claude ≈ $0.12); reel ≈ $2.20 with `ai_clips`
(surface $0.21, 4 edits × $0.075, 4 clips × $0.357, checks and Claude ≈ $0.26), plus $0.08–0.38 for each edit or clip
made again, so ≈ $2.20–3.30; ≈ $1.15 with `placed`. A month of daily carousels and a weekly reel ≈ $44–49.

Post shape: slides are 1080×1350 (4:5), the tallest shape Instagram's API accepts for feed images (its documented
range is 4:5 to 1.91:1; the app's newer 3:4 uploads aren't in that range). The shape asked from the image model
(`aspect_ratio` in `agent/visuals.py`) only decides how much is cropped and what Higgsfield charges, not what
Instagram shows.

Balances: Claude at <https://console.anthropic.com> (Billing), Higgsfield API at <https://open.higgsfield.ai>
(separate from Higgsfield app plans). A run fails with a clear message when a balance is empty; set low-balance
alerts where offered.

## Troubleshooting

| Message in the run log | What to do |
|---|---|
| `Higgsfield API balance is empty` | top up at open.higgsfield.ai |
| `Higgsfield rejected the API key` / Claude `AuthenticationError` | new key → `.env` → `scripts\update-secrets.ps1` |
| Instagram `Error validating access token` / `Session has expired` | [replace the Instagram token](#replace-the-instagram-token) |
| `No model could generate this` | a model was renamed or removed: check the list ([Models](#models)) and update `config/page.yaml` |
| `Instagram's 24-hour publishing limit is used up` | the API allows 100 posts per 24 h; wait |
| `FFmpeg failed` | look at the lines after it; run `tests\smoke_test.py` locally |
| `This reel failed the automatic quality check` | see [Review before posting](#review-before-posting-and-posting-by-hand): watch it, then publish with `--force` or make a new one |
| Scheduled runs stopped | GitHub turns off schedules after 60 days without repository activity; each post commits `state/`, so this only happens if posting stopped. Re-enable in Actions. |
| The "Save post history" step failed on `git push` | rare overlap with your own push; the next run catches up, or re-run the job |

## Moving to a new computer (or recovering from a lost one)

The cloud keeps posting without your PC. To work on it from another computer:

1. Install the tools: `winget install Python.Python.3.12 Gyan.FFmpeg Git.Git GitHub.cli`.
2. `gh auth login`, then `gh repo clone stickerultau/sticker-content-agent` **in a short folder** (for example
   `C:\`, giving `C:\sticker-content-agent`; Windows' 260-character path limit breaks installs in deep folders),
   then `cd sticker-content-agent`.
3. `powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1`.
4. Recreate `.env` from your password manager (`ANTHROPIC_API_KEY`, `HF_API_KEY_ID`, `HF_API_KEY_SECRET`,
   `IG_ACCESS_TOKEN`, `TOKEN_KEY`, `MEDIA_REPO=stickerultau/sticker-content-agent`). If `TOKEN_KEY` is lost, see
   [above](#if-token_key-is-lost-or-leaked).
5. `.\.venv\Scripts\python.exe run.py check` and `.\.venv\Scripts\python.exe tests\smoke_test.py`.

Everything else (code, brand fonts and images, page brief, post history, encrypted token) is in the repository.
