# Setup from scratch

Everything needed to rebuild this automation, accounts included, in about an hour. Steps follow the screens as
they looked in October 2026; Meta and Instagram rename buttons from time to time, but the order stays the same.
What exists today is listed at the end ([Inventory](#inventory-what-exists-today)).

## 0. What you need

| Account | Used for | Cost |
|---|---|---|
| Instagram (the page) | where posts are published | free |
| Facebook (your personal account) | only to log in to Meta for Developers and own the developer app; nothing is posted there | free |
| Anthropic Console | Claude writes themes, sticker concepts and captions | ≈ $0.10 per post |
| Higgsfield API (open.higgsfield.ai) | sticker images and reel videos | ≈ $0.05–0.60 per post |
| GitHub | runs the schedule and serves the media to Instagram | free |

On the computer (Windows): Python 3.12, FFmpeg, Git and GitHub CLI. `scripts\setup-local.ps1` tells you what is
missing (each installs with one `winget install` line).

Use a dedicated Gmail for the page (this setup uses the page's own Gmail address) and keep every key in a password
manager: GitHub stores them write-only, so you cannot read them back later.

## 1. Instagram page

1. Create the account in the Instagram app, using the dedicated Gmail.
2. **Switch to a Creator account** at <https://www.instagram.com/accounts/convert_to_professional_account/>:
   choose **Creator** → Next → Next → search the category **Graphic Designer** → tick **Show category on profile** →
   Done → **Continue** (it makes the account public, which the API requires).
   In the app: Settings → Account type and tools → Switch to professional account.
3. **Name**: Accounts Center → Profiles → the account → **Name** → `Stickerul Zilei | Stickere noi zilnic` → Done.
   Instagram allows only 2 name changes per 14 days, and the name is searchable, so keep the word "stickere".
4. **Bio**: <https://www.instagram.com/accounts/edit/> → Bio → Submit (141 of 150 characters):
   ```
   Le printăm pe orice 👉 @stickerul.tau
   Mașini, vitrine, laptopuri, HoReCa, canvas
   Lucios, mat, holografic, transparent, electrostatic, epoxy 3D
   ```
   Phones show only about 3 bio lines before "more", so the shop goes on line 1 and the first lines stay short
   enough not to wrap. The name above already says what the page is ("Stickere noi zilnic"), so the bio starts with
   the offer: any surface (line 2) and every material (line 3).
   AI is disclosed where it matters, on each post (the automatic "AI content" label), not in the bio.
   Leave **AI-generated profile** off in Edit profile: that label is only for accounts showing an AI-generated person.
5. **Profile picture**: Accounts Center → Profile picture → Upload new photo → `assets/brand/profile_picture.jpg`
   (or in the app). Browser automation cannot pick local files, so do this one by hand.
6. **Website link**: only editable in the mobile app (Edit profile → Links).
7. If the username is not `stickerul.zilei`, change `page.handle` in `config/page.yaml`.

## 2. Meta developer app and Instagram token

Meta for Developers only accepts a Facebook login. The Instagram account does **not** need to be linked to Facebook.
(No Facebook account at all? See [Appendix A](#appendix-a-without-a-facebook-account).)

1. Open <https://developers.facebook.com> → **Login** → **Continue with Facebook**. If you have never used it, finish
   the developer registration (accept the terms, verify your phone).
2. **My Apps → Create App**, then the wizard:
   - **App details**: App name `Stickerul Zilei Agent`; App contact email: the page's Gmail → Next.
   - **Use cases**: filter **Content management** → tick **Manage messaging & content on Instagram** → Next.
   - **Business**: **I don't want to connect a business portfolio yet.** → Next.
   - **Requirements**: "No requirements identified" → Next → **Overview** → **Create app**.
3. **Permissions**: in the app, Use cases → Customize (Instagram API) → **Permissions and features** → click **Add**
   on `instagram_business_basic` and on `instagram_business_content_publish`. Both must show "Ready for testing".
   Do not add the messaging or comment permissions: the agent does not need them.
4. **Tester role**: App roles → **Roles** → **Add People** → **Instagram Tester** → type the username → pick it from
   the list → **Add**. It shows as "Pending".
5. **Accept the invite** while logged in as the page: <https://www.instagram.com/accounts/manage_access/> →
   **Tester Invites** → **Accept**. (App: Settings → Website permissions → Apps and websites → Tester invites.)
6. **Token**: Use cases → Customize → **API setup with Instagram login** → expand **2. Generate access tokens** →
   **Generate token** next to the account → **Allow** → tick **I understand** → **Copy**. Paste it into `.env` as
   `IG_ACCESS_TOKEN=` (step 5 below). Never paste it into a chat or a file in the repository.

The token lasts 60 days; the agent renews it every week while it keeps posting. The app stays in **Development
mode**, which is all you need to post to your own account: no App Review, no business verification.

## 3. Claude API key

<https://console.anthropic.com> → **API keys → Create key** → `ANTHROPIC_API_KEY`. Under **Billing**, add $5 or more;
that covers 1–2 months.

## 4. Higgsfield API key

<https://open.higgsfield.ai> → **Create API key**. You get a **key ID** and a **secret**, shown once →
`HF_API_KEY_ID` and `HF_API_KEY_SECRET`. Top up $10–20: the API is pay-as-you-go and separate from Higgsfield app
plans (app credits do not work for the API). Model choices are explained in
[OPERATIONS.md → Models](OPERATIONS.md#models).

## 5. Install locally and test

```powershell
git clone https://github.com/stickerultau/sticker-content-agent.git   # or gh repo clone; skip on a brand-new setup
cd sticker-content-agent
powershell -ExecutionPolicy Bypass -File scripts\setup-local.ps1        # Python environment, packages, .env
```

Keep the project in a short folder such as `C:\sticker-agent` or `E:\AI projects\instagram automation`. Windows
limits paths to 260 characters and one package has very long file names, so installing inside a deep folder fails
(the script warns you and shows how to enable long paths instead).

Fill in `.env` (copied from `.env.example`): `ANTHROPIC_API_KEY`, `HF_API_KEY_ID`, `HF_API_KEY_SECRET`,
`IG_ACCESS_TOKEN`. Leave `MEDIA_REPO` and `TOKEN_KEY` empty on a brand-new setup (step 6 fills them).

```powershell
.\.venv\Scripts\python.exe run.py check                        # every line [ok]; Media hosting is set in step 6
.\.venv\Scripts\python.exe tests\smoke_test.py                 # offline test, no cost
.\.venv\Scripts\python.exe run.py create --format carousel     # a real post in output\, not published (~$0.20)
```

## 6. Deploy to GitHub (autopilot)

```powershell
gh auth login                                                  # once per computer
powershell -ExecutionPolicy Bypass -File scripts\deploy.ps1   # -RepoName other-name to change the repository name
```

The script:
1. gets the latest version from GitHub if the repository already exists (re-runs are safe);
2. writes `MEDIA_REPO=<you>/sticker-content-agent` into `.env`;
3. creates `TOKEN_KEY` if missing and encrypts the Instagram token into `state/ig_token.enc`;
4. creates the **public** repository and pushes the code (or pushes changes on a re-run);
5. saves `ANTHROPIC_API_KEY`, `HF_API_KEY_ID`, `HF_API_KEY_SECRET` and `TOKEN_KEY` as GitHub Actions secrets;
6. starts a test run that creates a carousel without publishing it (skip with `-SkipTestRun`).

The repository is public because Instagram downloads each post's media from a public link (the `media` branch,
served by jsDelivr). No key is ever stored in it: `.env` is gitignored and the token file is encrypted.

## 7. First post

Recommended: GitHub → **Actions** → **Content Creation Agent** → **Run workflow** → format `carousel`, **Publish**
ticked. Or publish a post you reviewed locally with `run.py publish` and push `state/` afterwards
([OPERATIONS.md](OPERATIONS.md#review-before-posting-and-posting-by-hand)). From then on the schedule runs by itself.

---

## Appendix A: without a Facebook account

Meta's developer portal needs a Facebook login. Alternatives:
- **A posting service with its own Meta-approved app**, such as Upload-Post or Zernio: you connect the page with
  your Instagram login and post through their API (Upload-Post: free for 10 posts/month, then $16–24/month).
  Not built in: it requires replacing `agent/instagram.py` and `agent/hosting.py` with the service's API.
- **Someone you trust** creates the Meta app with their Facebook, adds the page as an Instagram Tester, and the
  token is generated while logged in as the page.

Avoid a second "fake" Facebook account (against Meta's rules; the app can be shut down) and unofficial
password-based posting tools (high ban risk for new accounts).

## Inventory (what exists today)

| What | Details |
|---|---|
| Instagram page | [@stickerul.zilei](https://www.instagram.com/stickerul.zilei/): Creator account, category Graphic Designer, uses the page's Gmail |
| Meta app | **Stickerul Zilei Agent**, App ID `1103439452597014`, Development mode, no business portfolio, owned by your personal Facebook developer account. Its Instagram app is "Stickerul Zilei Agent-IG". Dashboard: <https://developers.facebook.com/apps/1103439452597014/> |
| Permissions | `instagram_business_basic`, `instagram_business_content_publish`; the page is an accepted Instagram Tester |
| GitHub repository | [stickerultau/sticker-content-agent](https://github.com/stickerultau/sticker-content-agent) (public); branches `main` (code and state) and `media` (current post's files) |
| Secrets | GitHub Actions: `ANTHROPIC_API_KEY`, `HF_API_KEY_ID`, `HF_API_KEY_SECRET`, `TOKEN_KEY`; Instagram token encrypted in `state/ig_token.enc` |
| Schedule | `.github/workflows/autopost.yml`: carousel daily 17:00 UTC, reel Tue/Thu/Sat 11:00 UTC |
| First post | <https://www.instagram.com/p/DfBBcQrDP-F/> (28 Oct 2026) |
