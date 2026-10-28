# Cloudflare R2: planned media hosting (not active yet)

**Status (28 Oct 2026):** the page still publishes through the old method: each post's files go to the
repository's `media` branch and Instagram downloads them through jsDelivr links
([OPERATIONS.md → The `media` branch](OPERATIONS.md#the-media-branch)). A replacement that uses Cloudflare R2 is
ready on the branch `claude/inspiring-colden-7856f7` (commit `c05aa84`) and is **not merged**. This page explains
why it exists, how to set up Cloudflare, and how to switch.

## Why switch

Instagram's API doesn't take uploaded files: when you post, it downloads each picture and video from a public link.
GitHub can't provide good links on its own (Actions artifacts are zip files behind a login, and GitHub's direct
file links label videos as a generic file instead of a video), so the old method puts jsDelivr in the middle.

jsDelivr's [Terms of Use](https://github.com/jsdelivr/jsdelivr/blob/master/Terms%20of%20Use.md) (section 6) forbid
using it "as a general-purpose file or media hosting service", naming hosting videos as an example, and section 10
lets them restrict or withdraw access. It works today, but if they block it, publishing fails without warning.

Cloudflare R2 is online storage whose terms allow hosting content. The agent would put a post's files in a private
R2 bucket for a few minutes, give Instagram signed links that expire after 2 hours, and delete the files once
publishing ends (also when it fails). Cost: $0. R2's free tier is 10 GB stored, 1 million uploads and 10 million
downloads a month with no traffic fees; the page uses about 250 uploads and 250 downloads a month.

Alternatives looked at: Meta's own video upload needs Facebook Login for Business (this page uses Instagram Login)
and doesn't take pictures; GitHub's direct links serve videos as `application/octet-stream`.

## 1. Set up Cloudflare (about 15 minutes, once)

1. Sign up at <https://dash.cloudflare.com/sign-up> with the page's Gmail and confirm the email. If it asks you to
   add a website, skip that: no domain is needed.
2. In the left menu, open **Storage & databases → R2 → Overview** and complete the checkout. Cloudflare asks for a
   card or PayPal because it bills only for usage above the free tier. At this page's size that's $0. Cloudflare
   doesn't cap usage, so keep the R2 keys as secret as the others.
3. **Create bucket** → name `stickerul-zilei-media` → leave the location (Automatic) and storage class (Standard) as
   they are → create it. Leave public access off: the agent's links are signed.
4. Optional safety net: in the bucket, **Settings → Object Lifecycle Rules → Add rule** → all objects, delete 1 day
   after upload → **Save changes**. It only cleans up after a run that was cut off while publishing.
5. Back on **R2 → Overview**, next to **API Tokens** click **Manage → Create Account API token**:
   name `stickerul-zilei-agent`, permission **Object Read & Write**, **Apply to specific buckets only** →
   `stickerul-zilei-media` → create.
6. The next page shows the keys **only once**. Save them in your password manager (never in a chat or in the
   repository): **Access Key ID**, **Secret Access Key** and the S3 endpoint
   `https://<account id>.r2.cloudflarestorage.com`.
7. Add them to `.env` (open it with Notepad in the project folder):
   ```
   R2_ENDPOINT=https://<account id>.r2.cloudflarestorage.com
   R2_ACCESS_KEY_ID=...
   R2_SECRET_ACCESS_KEY=...
   R2_BUCKET=stickerul-zilei-media
   ```

## 2. Switch over (in this order)

1. Merge `claude/inspiring-colden-7856f7` into your local `main` (no push yet), then install the new package:
   `.\.venv\Scripts\python.exe -m pip install -r requirements.txt` (adds `boto3`).
2. `.\.venv\Scripts\python.exe run.py check`. The **Media hosting** line uploads a test picture to R2, has Instagram
   download it into a draft that is never published, and deletes it. It must show `[ok]`; if it doesn't, stop here
   (nothing live has changed).
3. `powershell -ExecutionPolicy Bypass -File scripts\update-secrets.ps1` (the merged version also saves the four
   `R2_` values as GitHub secrets).
4. Push `main`. From the next run on, posts go through R2. If the secrets are missing, `run.py post` stops before
   spending anything.
5. Afterwards: delete the old `media` branch on GitHub (published posts don't depend on it). The repository no longer
   has to be public, which you may want, since anyone signed in to GitHub can download a public repository's run
   artifacts.

The merged branch also updates SETUP.md, OPERATIONS.md, the workflow and the scripts for R2, so this page can be
deleted after the switch.

**Going back:** revert the merge commit and push; the `media` branch method works again as before.
