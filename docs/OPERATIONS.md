# Operations

How the automation runs, where its secrets live, and how to change, update, fix or move it.

## How a scheduled run works

GitHub Actions starts `.github/workflows/autopost.yml` on schedule (carousel daily 17:00 UTC, reel Tue/Thu/Sat
11:00 UTC; Romania is UTC+2 in winter and UTC+3 in summer). Each run:

1. installs FFmpeg and the Python packages;
2. runs `python run.py post --format carousel|reel`:
   **topic research → copy → visuals (Higgsfield) → design & edit → publish** (media goes to the repo's `media`
   branch, then the Instagram API publishes it, labeled as AI content);
3. commits `state/` (post history and, when renewed, the encrypted Instagram token);
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
| Tone, topics, rules, occasions, hashtags, CTA line, colors, stickers per post | `config/page.yaml` |
| Posting times or days | the `cron` lines in `.github/workflows/autopost.yml`; the "Decide what to post" step maps each time to a format |
| Reel motion (hands that peel vs. no hands) | `formats.reel.motion`: `"peel"` or `"float"` |
| Voice | `formats.reel.voice` (`ro-RO-AlinaNeural` or `ro-RO-EmilNeural`) |
| Background music | add royalty-free `.mp3` files to `assets/music/` |
| Image or video models | `models` in `config/page.yaml` (see [Models](#models)) |
| Make every post a collab with the shop | `page.collaborators: ["stickerul.tau"]` (the shop accepts each invite in the app) |

**Pause**: GitHub → Actions → Content Creation Agent → **⋯ → Disable workflow** (re-enable the same way).
Pausing longer than 60 days lets the Instagram token expire.

## Review before posting and posting by hand

- **Review first**: `run.py create --format carousel` → check `output\<folder>\slides` (or `reel.mp4`) →
  `run.py publish output\<folder>`.
- **Fix a typo**: edit `output\<folder>\copy.json` → `run.py render output\<folder>` → publish.
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
| Sticker images | `marketing-studio/image` (best looking), `ideogram/v4.0`, `xai/grok-imagine-image-2.0` | ≈ $0.011 / $0.03 / $0.04 |
| Laptop mockup | `alibaba/qwen-image-3/edit` (accepts at most 3 reference images) | ≈ $0.04 |
| Reel clips | `kling-video/v2.5-turbo/pro/image-to-video`, `kling-video/v2.6/pro/image-to-video`, `minimax/hailuo-2.3/standard/image-to-video` | ≈ $0.02–0.04 per second |

## The `media` branch

Instagram's API doesn't take file uploads: it downloads each image or video from a public link. Right before
posting, the agent replaces the `media` branch with a single commit holding only that post's files and hands
Instagram their jsDelivr links. The branch never shares history with `main`, never grows, and must never be merged.
GitHub may suggest "Compare & pull request" for it: ignore that. Deleting it is harmless; the next post recreates it.

## Costs and balances

Each run log ends with "Estimated cost of this post". Balances: Claude at <https://console.anthropic.com> (Billing),
Higgsfield at <https://open.higgsfield.ai>. A run fails with a clear message when a balance is empty; set low-balance
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
