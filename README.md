# Content Creation Agent: automated Instagram sticker page

Posts polished sticker content to a new Instagram page on autopilot and sends buyers to **@stickerul.tau**.

```
Topic research ─► Copy ─► Visuals ─► Design & edit ─► Publish ─► (repeats on schedule)
Claude + trends   Claude   Higgsfield  brand templates   Instagram API
                                       + voice + captions
```

| What | When (Romania time) | Made of |
|---|---|---|
| Carousel: a themed pack of 5 sticker designs | every day, 19:00 | cover, 5 numbered stickers, laptop mockup, "pick your favorite" slide |
| Reel: 3 stickers peeled and stuck on objects | Tue, Thu, Sat, 13:00 | AI video clips, Romanian voiceover, animated captions, end card |

It runs on **GitHub Actions** (free), so your PC can be off. Each run picks a fresh theme (it knows upcoming
occasions such as Halloween, 1 Decembrie and Mărțișor, plus today's Google Trends, and never repeats past themes).

**Running cost:** about **$8–15/month**: Claude ≈ $0.10 per post, Higgsfield ≈ $0.20 per carousel and ≈ $0.40–0.60
per reel. Instagram's API, GitHub Actions and the voiceover are free.

---

## 1. Create the Instagram page (in the Instagram app)

1. Create a new account. Free username ideas (check availability): `stickerul.zilei`, `pachetul.de.stickere`,
   `stickere.zilnice`.
2. **Settings → Account type and tools → Switch to professional account → Creator** (category: *Artist* or *Shopping & retail*).
   The API only works with Creator or Business accounts, and the account must be public.
3. Profile:
   - **Name** (searchable): `Stickerul Zilei | Stickere noi zilnic`
   - **Bio**:
     ```
     Un pachet nou de stickere în fiecare zi ✨
     Le vrei pe laptop? Comandă pe @stickerul.tau 👇
     Design-uri create cu AI 🤖
     ```
   - **Profile picture**: `assets/brand/profile_picture.jpg`
   - **Link**: your shop link.
4. Update `handle` in `config/page.yaml` if your username differs from `stickerul.zilei`.

> Warm-up tip: post 2–3 times by hand during the first days and reply to comments yourself. New accounts that start
> posting at full speed on day one are more likely to be rate-limited.

## 2. Instagram token (free, about 10 minutes)

1. Go to <https://developers.facebook.com>, log in with Facebook, and register as a developer if asked.
2. **My Apps → Create App** → use case **Other** → app type **Business** → give it a name (e.g. *Sticker Agent*).
3. In the app dashboard, find **Instagram** and click **Set up**. This opens **API setup with Instagram login**.
4. Under **Generate access tokens**, click **Add account** and log in with the **new page**. If Instagram shows a
   tester invite, accept it: Instagram → Settings → *Website permissions* → *Apps and websites* → *Tester invites*.
5. Click **Generate token** next to the account, approve the permissions, and copy the token (it starts with `IGAA`).

The app stays in *Development mode*: that is all you need to post to your own account (no App Review or Facebook Page).
The token lasts 60 days, and the agent renews it automatically every week.

## 3. Claude API key

<https://console.anthropic.com> → **API keys → Create key**. Add $5 of credit under **Billing**, which lasts about 1–2 months.

## 4. Higgsfield API key

<https://open.higgsfield.ai> → **Create API key** (you get a *key ID* and a *secret*, shown once). Top up $10–20.
The API is pay-as-you-go and separate from your Higgsfield Plus plan; plan credits don't apply to it.

## 5. Fill in `.env` and test locally

```powershell
copy .env.example .env      # then paste the keys from steps 2-4 into .env
.\.venv\Scripts\python.exe run.py check
```

`check` must show `[ok]` for Claude, Higgsfield, Instagram, FFmpeg and Fonts (*Media hosting* is set up in step 6).

Make a test post **without publishing** and review it in `output/`:

```powershell
.\.venv\Scripts\python.exe run.py create --format carousel
.\.venv\Scripts\python.exe run.py create --format reel
```

## 6. Put it on autopilot

```powershell
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1
```

This creates the public repository `stickerultau/sticker-content-agent`, stores your keys as encrypted GitHub secrets,
and starts a test run that creates a carousel without publishing it. Instagram downloads each post's media from
this public repository; your keys are never in it. From then on it posts on the schedule above.

To publish the first post right away: **GitHub → Actions → Content Creation Agent → Run workflow** (format *carousel*,
*Publish* ticked).

---

## Day-to-day

| I want to… | Do this |
|---|---|
| See what was posted | GitHub → Actions → a run → summary (preview + link); files under *Artifacts* |
| Pause posting | GitHub → Actions → Content Creation Agent → **⋯ → Disable workflow** |
| Change times or frequency | edit the `cron` lines in `.github/workflows/autopost.yml` (UTC; Romania = UTC+2 in winter, +3 in summer) |
| Change tone, topics, rules, colors | edit `config/page.yaml` (the agent re-reads it on every run) |
| Review before posting | run `python run.py create …` locally, check `output/`, then `python run.py publish output/<folder>` |
| Fix a typo and re-render | edit `output/<folder>/copy.json`, then `python run.py render output/<folder>` |
| Add background music to reels | put royalty-free `.mp3` files in `assets/music/` (e.g. from the YouTube Audio Library) |
| Make every post a collab with the shop | set `collaborators: ["stickerul.tau"]` in `config/page.yaml` (accept each invite in the app) |
| Switch reel style if hands look odd | set `motion: "float"` in `config/page.yaml` |

Every post is labeled as AI-generated through the API (`is_ai_generated`), as Instagram's rules require for AI imagery.

## Troubleshooting

- **`check` says the Instagram account is PERSONAL**: switch it to Creator (step 1.2).
- **"Instagram's publishing limit is used up"**: the API allows 100 posts per 24 hours; this only happens if you run it in a loop.
- **A Higgsfield model is "unavailable"**: the agent automatically tries the next model in `config/page.yaml → models`.
  The API's model IDs are listed at `GET https://api.higgsfield.ai/models` (with your key) or <https://open.higgsfield.ai/explore>.
  Not every model in the Higgsfield app is on the API (Seedream isn't, for example).
- **Token errors after a long pause**: generate a new token (step 2.5), put it in `.env`, then run `scripts\deploy.ps1` again.

## Project layout

```
run.py                     command line (check, create, post, publish, render, refresh-token, seal-token)
config/page.yaml           the page's brief: audience, voice, pillars, occasions, palettes, models
agent/research.py          1. topic research (occasions, Google Trends, history) with Claude
agent/copywriter.py        2. sticker concepts, slide text, voiceover lines, caption, hashtags
agent/visuals.py           3. image and video prompts → Higgsfield API (agent/higgsfield.py)
agent/design.py            4. brand templates (carousel slides, reel overlays, covers)
agent/video.py, voice.py, captions.py   4. reel editing with FFmpeg, voiceover and word-by-word captions
agent/hosting.py, instagram.py, tokens.py  5. public media URLs, publishing and token renewal
.github/workflows/autopost.yml          the schedule
```
