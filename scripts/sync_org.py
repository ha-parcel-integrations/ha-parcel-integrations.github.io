#!/usr/bin/env python3
"""Push what this site owns back out to the rest of the org.

Two jobs, both writing to *other* repositories:

1. **The org profile README.** ``scripts/generate.py`` renders
   ``build/profile-README.md`` from the same data as the site's carrier page;
   this commits it to ``ha-parcel-integrations/.github`` at
   ``profile/README.md``, which is what github.com/ha-parcel-integrations
   displays.
2. **Each repo's homepage field.** The "About" box on every carrier repo points
   at the docs site, so a visitor landing on one carrier finds the suite.

Both are deliberately a no-op when:

* ``PROFILE_TOKEN`` is not set — the workflow's built-in GITHUB_TOKEN cannot
  write to another repository, so a maintainer has to add a PAT. Until then
  the site still deploys; only these two syncs stay manual.
* nothing would change — no empty commits, no needless PATCHes, on the nightly.

Usage:
    PROFILE_TOKEN=ghp_... python scripts/sync_org.py
"""

from __future__ import annotations

import base64
import json
import os
import sys
import urllib.error
import urllib.request
from pathlib import Path

ORG = "ha-parcel-integrations"
REPO = ".github"
TARGET = "profile/README.md"
BUILD = Path(__file__).resolve().parent.parent / "build"
SOURCE = BUILD / "profile-README.md"
REPO_LIST = BUILD / "repos.json"
SITE_URL = f"https://{ORG}.github.io/"
API = "https://api.github.com"


def _call(method: str, path: str, token: str, body: dict | None = None) -> dict:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{API}{path}", data=data, method=method)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("Authorization", f"Bearer {token}")
    req.add_header("User-Agent", f"{ORG}-site-generator")
    if data:
        req.add_header("Content-Type", "application/json")
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read() or b"{}")


def sync_homepages(token: str) -> None:
    """Point every carrier repo's About box at the docs site."""
    if not REPO_LIST.exists():
        print(f"· {REPO_LIST} is missing — skipping homepage sync.")
        return

    for repo in json.loads(REPO_LIST.read_text(encoding="utf-8")):
        current = _call("GET", f"/repos/{ORG}/{repo}", token)
        if (current.get("homepage") or "").rstrip("/") == SITE_URL.rstrip("/"):
            continue
        _call("PATCH", f"/repos/{ORG}/{repo}", token, {"homepage": SITE_URL})
        print(f"✓ {repo}: homepage → {SITE_URL}")


def push_profile(token: str) -> int:
    if not SOURCE.exists():
        print(f"❌ {SOURCE} is missing — run scripts/generate.py first.", file=sys.stderr)
        return 1

    content = SOURCE.read_bytes()

    sha = None
    try:
        current = _call("GET", f"/repos/{ORG}/{REPO}/contents/{TARGET}", token)
        sha = current.get("sha")
        if base64.b64decode(current.get("content", "")) == content:
            print("· Org profile README already up to date.")
            return 0
    except urllib.error.HTTPError as err:
        if err.code != 404:  # 404 just means we are creating it
            raise

    payload = {
        "message": "Regenerate carrier list from the org site",
        "content": base64.b64encode(content).decode(),
        "committer": {
            "name": "ha-parcel-integrations bot",
            "email": "noreply@github.com",
        },
    }
    if sha:
        payload["sha"] = sha

    _call("PUT", f"/repos/{ORG}/{REPO}/contents/{TARGET}", token, payload)
    print(f"✓ Pushed {TARGET} to {ORG}/{REPO}")
    return 0


def main() -> int:
    token = os.environ.get("PROFILE_TOKEN")
    if not token:
        print(
            "· PROFILE_TOKEN not set — skipping the org profile README and the\n"
            "  repo homepage sync. Add a PAT with contents:write on the .github\n"
            "  repo and administration:write on the org as the PROFILE_TOKEN\n"
            "  secret to enable both."
        )
        return 0

    sync_homepages(token)
    return push_profile(token)


if __name__ == "__main__":
    raise SystemExit(main())
