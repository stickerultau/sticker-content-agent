"""Content Creation Agent: command line.

  python run.py check                          verify keys, Instagram account, media hosting, FFmpeg
  python run.py post --format carousel         create AND publish a post (what the schedule runs)
  python run.py create --format reel           create a post without publishing (review it in output/)
  python run.py publish output/<post folder>   publish a post you created earlier
  python run.py render output/<post folder>    re-render slides/reel after editing its copy.json
  python run.py refresh-token                  refresh the Instagram token now
  python run.py seal-token                     encrypt the token for GitHub Actions (state/ig_token.enc)
"""
from __future__ import annotations

import argparse
import shutil
import sys
from pathlib import Path

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

from agent import log, pipeline, tokens  # noqa: E402
from agent.settings import FONTS, ROOT, env, load_config  # noqa: E402


def cmd_check(cfg: dict) -> int:
    ok = True

    def report(name: str, fn) -> None:
        nonlocal ok
        try:
            print(f"  [ok] {name}: {fn()}")
        except Exception as exc:  # noqa: BLE001 - show every problem at once
            ok = False
            print(f"  [!!] {name}: {exc}")

    print(f"Page: {cfg['page']['name']} (@{cfg['page']['handle']})  shop: @{cfg['page']['shop_handle']}")

    def claude():
        import anthropic
        model = anthropic.Anthropic().models.retrieve(cfg["models"]["claude"])
        return f"key works, model {model.id}"

    def higgsfield():
        import requests
        from agent.higgsfield import Higgsfield
        hf = Higgsfield()
        r = requests.get("https://api.higgsfield.ai/requests/00000000-0000-0000-0000-000000000000/status",
                         headers=hf.headers, timeout=30)
        if r.status_code in (401, 403):
            raise RuntimeError("key rejected")
        return "key accepted"

    def instagram():
        from agent.instagram import Instagram
        ig = Instagram()
        acc = ig.account
        if acc.get("account_type") not in ("BUSINESS", "MEDIA_CREATOR"):
            raise RuntimeError(f"@{acc.get('username')} is a {acc.get('account_type')} account; switch it to Creator or Business")
        left = ig.quota_left()
        return f"@{acc['username']} ({acc['account_type']}, {acc.get('followers_count', 0)} followers, {left} posts left today)"

    def media_host():
        from agent.hosting import GitHubMediaHost
        return f"{GitHubMediaHost().check()} (public)"

    report("Claude API", claude)
    report("Higgsfield API", higgsfield)
    report("Instagram", instagram)
    report("Media hosting", media_host)
    report("FFmpeg", lambda: shutil.which("ffmpeg") or (_ for _ in ()).throw(RuntimeError("not installed")))
    report("Fonts", lambda: f"{len(list(FONTS.glob('Brand*.ttf')))} brand fonts")
    print("\nAll good." if ok else "\nFix the [!!] items above (see README).")
    return 0 if ok else 1


def set_env_var(name: str, value: str) -> None:
    """Sets NAME=value in .env, replacing an existing line (and in this process)."""
    import os
    env_file = ROOT / ".env"
    lines = env_file.read_text(encoding="utf-8").splitlines() if env_file.exists() else []
    lines = [line for line in lines if not line.strip().startswith(f"{name}=")]
    lines.append(f"{name}={value}")
    env_file.write_text("\n".join(lines) + "\n", encoding="utf-8")
    os.environ[name] = value


def cmd_seal_token() -> int:
    key = env("TOKEN_KEY")
    if not key:
        key = tokens.new_key()
        set_env_var("TOKEN_KEY", key)
        print("Generated TOKEN_KEY and saved it in .env")
    data = tokens.load()
    if tokens.read_encrypted() == data:
        print("Instagram token unchanged (state/ig_token.enc is up to date)")
        return 0
    tokens.save(data)
    print(f"Encrypted the Instagram token into {tokens.ENCRYPTED.relative_to(ROOT)}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Content Creation Agent for Instagram")
    sub = parser.add_subparsers(dest="command", required=True)
    sub.add_parser("check")
    for name in ("post", "create"):
        p = sub.add_parser(name)
        p.add_argument("--format", choices=["carousel", "reel"], default="carousel")
    for name in ("publish", "render"):
        sub.add_parser(name).add_argument("post_dir", type=Path)
    sub.add_parser("refresh-token")
    sub.add_parser("seal-token")
    sub.add_parser("costs")
    setter = sub.add_parser("set-env")
    setter.add_argument("name")
    setter.add_argument("value")
    args = parser.parse_args()
    cfg = load_config()

    if args.command == "set-env":
        set_env_var(args.name, args.value)
        return 0
    if args.command == "costs":
        from agent import costs
        print(costs.report((cfg.get("budget") or {}).get("monthly_usd")))
        return 0
    if args.command == "check":
        return cmd_check(cfg)
    if args.command == "seal-token":
        return cmd_seal_token()
    if args.command == "refresh-token":
        from agent.instagram import Instagram
        Instagram().refresh_if_needed(force=True)
        return 0
    if args.command in ("post", "create"):
        post_dir = pipeline.create(cfg, args.format)
        if args.command == "post":
            with log.step(5, "Publish to Instagram"):
                pipeline.publish(cfg, post_dir)
        else:
            log.info("Not published (create mode). To publish: python run.py publish " + str(post_dir))
        return 0
    if args.command == "render":
        pipeline.render(cfg, args.post_dir.resolve())
        log.info(f"Rendered {args.post_dir}")
        return 0
    if args.command == "publish":
        with log.step(5, "Publish to Instagram"):
            pipeline.publish(cfg, args.post_dir.resolve())
        return 0
    return 1


if __name__ == "__main__":
    sys.exit(main())
