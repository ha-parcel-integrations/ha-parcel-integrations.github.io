#!/usr/bin/env python3
"""Generate the pages that must never be hand-written.

Two pages on this site describe things that already have a source of truth
somewhere else in the org:

* ``docs/carriers.md``    — every carrier repo, its version and its icon
* ``docs/automations.md`` — the aggregator's ``examples/`` folder

Both are rebuilt from the GitHub API on every deploy. Nothing here is
committed; a stale copy in git is worse than no copy at all, because the
suite gains carriers faster than anyone remembers to update a table.

The only hand-maintained input is ``data/carriers.yml``, which holds the
handful of facts no repo exposes machine-readably (coverage, how you
authenticate, one-line blurb). If the org and that file disagree, this
script exits non-zero and the deploy fails — see ``_reconcile``.

Usage:
    GITHUB_TOKEN=... python scripts/generate.py
"""

from __future__ import annotations

import base64
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

ORG = "ha-parcel-integrations"
API = "https://api.github.com"

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
ICONS = DOCS / "assets" / "icons"
CARRIER_DATA = ROOT / "data" / "carriers.yml"

# Repos in the org that are not carrier integrations. The aggregator is a
# real integration but gets its own section rather than a table row.
AGGREGATOR = "ha-parcel-aggregator"
NOT_A_CARRIER = {
    ".github",
    "ha-carrier-template",
    "ha-parcel-integrations.github.io",
    AGGREGATOR,
}

AUTH_LABEL = {
    "account": "Account login",
    "trackingnr": "Tracking number",
}


class GenerateError(RuntimeError):
    """Something is out of sync — fail the build rather than publish a lie."""


# --------------------------------------------------------------------------
# GitHub plumbing
# --------------------------------------------------------------------------


def _request(url: str) -> bytes:
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", f"{ORG}-site-generator")
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.read()
    except urllib.error.HTTPError as err:
        if err.code == 403 and "rate limit" in err.read().decode(errors="replace").lower():
            raise GenerateError(
                "GitHub rate limit hit. Set GITHUB_TOKEN (the workflow passes "
                "the built-in token automatically)."
            ) from err
        raise


def gh_json(path: str) -> object:
    return json.loads(_request(f"{API}{path}"))


def gh_file(repo: str, path: str) -> bytes | None:
    """Return a file's bytes from the default branch, or None if absent."""
    try:
        payload = gh_json(f"/repos/{ORG}/{repo}/contents/{path}")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise
    if not isinstance(payload, dict) or "content" not in payload:
        return None
    return base64.b64decode(payload["content"])


def gh_dir(repo: str, path: str) -> list[dict]:
    """Return a directory listing, or [] if the path does not exist."""
    try:
        payload = gh_json(f"/repos/{ORG}/{repo}/contents/{path}")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return []
        raise
    return payload if isinstance(payload, list) else []


def latest_release(repo: str) -> str | None:
    """Latest published release tag, or None when the repo has never shipped."""
    try:
        payload = gh_json(f"/repos/{ORG}/{repo}/releases/latest")
    except urllib.error.HTTPError as err:
        if err.code == 404:
            return None
        raise
    return payload.get("tag_name") if isinstance(payload, dict) else None


def org_repos() -> list[dict]:
    repos: list[dict] = []
    page = 1
    while True:
        batch = gh_json(f"/orgs/{ORG}/repos?per_page=100&page={page}")
        if not isinstance(batch, list) or not batch:
            break
        repos.extend(batch)
        page += 1
    return [r for r in repos if not r.get("archived")]


# --------------------------------------------------------------------------
# Carrier model
# --------------------------------------------------------------------------


@dataclass
class Carrier:
    repo: str
    name: str
    domain: str
    version: str
    url: str
    region: str
    countries: list[str]
    auth: str
    input: str | None
    directions: str
    blurb: str
    icon: str | None

    @property
    def early(self) -> bool:
        """Below 1.0.0 means unconfirmed data — say so, loudly."""
        return self.version.split(".")[0] == "0"

    @property
    def flags(self) -> str:
        return " ".join(_flag(c) for c in self.countries)

    @property
    def connect(self) -> str:
        label = AUTH_LABEL.get(self.auth, self.auth)
        # The sub-line only earns its space when it says more than the label,
        # e.g. "Tracking number + postal code" or "AWB number".
        if self.input and self.input != label:
            return f"{label}<br><small>{self.input}</small>"
        return label


def _flag(code: object) -> str:
    """ISO 3166-1 alpha-2 → regional-indicator flag emoji."""
    if not isinstance(code, str):
        # Unquoted NO in YAML 1.1 is the boolean false, not Norway.
        raise GenerateError(
            f"data/carriers.yml: country code {code!r} is not a string — quote "
            'it ("NO"). YAML reads bare NO/ON/OFF/Y/N as booleans.'
        )
    return "".join(chr(0x1F1E6 + ord(ch) - ord("A")) for ch in code.upper())


def _domain_of(repo: str) -> str | None:
    entries = gh_dir(repo, "custom_components")
    dirs = [e["name"] for e in entries if e.get("type") == "dir"]
    return dirs[0] if len(dirs) == 1 else None


def _reconcile(found: set[str], declared: set[str]) -> None:
    missing = sorted(found - declared)
    stale = sorted(declared - found)
    problems = []
    if missing:
        problems.append(
            "These carrier repos are public and released but are not in "
            "data/carriers.yml — add them:\n    " + "\n    ".join(missing)
            + "\n\n  (Private repos and repos without a release are skipped "
            "automatically; they never need an entry.)"
        )
    if stale:
        problems.append(
            "These entries in data/carriers.yml have no matching repo in the "
            f"org — remove them:\n    " + "\n    ".join(stale)
        )
    if problems:
        raise GenerateError("\n\n".join(problems))


def collect_carriers() -> list[Carrier]:
    declared = yaml.safe_load(CARRIER_DATA.read_text(encoding="utf-8")) or {}

    # Private repos are excluded explicitly rather than relying on the token's
    # scope: a maintainer previewing locally has a token that *can* see them,
    # and a preview that differs from production is worse than no preview.
    candidates = [
        r["name"]
        for r in org_repos()
        if r["name"].startswith("ha-")
        and r["name"] not in NOT_A_CARRIER
        and not r.get("private")
    ]

    domains: dict[str, str] = {}
    releases: dict[str, str] = {}
    unreleased: list[str] = []
    for repo in candidates:
        domain = _domain_of(repo)
        if not domain:  # no custom_components/<one dir> → not an integration repo
            continue
        tag = latest_release(repo)
        if tag is None:
            # Public but never shipped — still in development. It is not
            # installable, so it does not belong on the site yet.
            unreleased.append(repo)
            continue
        domains[repo] = domain
        releases[repo] = tag

    if unreleased:
        print(f"  skipped, no release yet: {', '.join(sorted(unreleased))}")

    _reconcile(set(domains), set(declared))

    ICONS.mkdir(parents=True, exist_ok=True)
    carriers: list[Carrier] = []
    for repo, domain in sorted(domains.items()):
        raw = gh_file(repo, f"custom_components/{domain}/manifest.json")
        if raw is None:
            raise GenerateError(f"{repo}: custom_components/{domain}/manifest.json is missing")
        manifest = json.loads(raw)
        meta = declared[repo]

        icon_bytes = gh_file(repo, f"custom_components/{domain}/brand/icon.png")
        icon_name = None
        if icon_bytes:
            icon_name = f"{domain}.png"
            (ICONS / icon_name).write_bytes(icon_bytes)

        carriers.append(
            Carrier(
                repo=repo,
                name=manifest.get("name", repo),
                domain=domain,
                # The released tag, not the manifest on main — main may carry
                # an unreleased bump, and what matters here is what a user can
                # actually install today. Tags carry no "v" prefix by
                # convention, but tolerate one.
                version=releases[repo].lstrip("v"),
                url=f"https://github.com/{ORG}/{repo}",
                region=meta["region"],
                countries=meta.get("countries") or [],
                auth=meta["auth"],
                input=meta.get("input"),
                directions=meta.get("directions", "incoming"),
                blurb=meta["blurb"],
                icon=icon_name,
            )
        )

    carriers.sort(key=lambda c: c.name.lower())
    return carriers


# --------------------------------------------------------------------------
# Page: carriers
# --------------------------------------------------------------------------

CARRIERS_INTRO = """\
# Carriers

Every integration below speaks the same [parcel contract](contract.md): the same
`ParcelStatus` values, the same parcel fields, the same events. Install the ones
that deliver to you, add the [Parcel Aggregator](#parcel-aggregator), and your
automations stop caring who is driving the van.

Install instructions live on [Getting started](install.md); each carrier's own
README covers its options in full.
"""

CARRIERS_FOOTER = """
## Parcel Aggregator

The [Parcel Aggregator]({aggregator_url}) is the piece that makes the suite more
than a pile of integrations. It talks to no carrier API of its own — it reads the
sensors and events the carriers already publish and re-emits them as one merged
set:

- summed count sensors with a `by_carrier` breakdown
- a single `parcel_aggregator_parcel_*` event stream
- one `next_delivery` timestamp across every carrier

Carriers you have not installed are skipped silently, and a carrier you add later
is picked up automatically — no reload, no update here.

## Missing your carrier?

[Request it]({request_url}) — the code is rarely the blocker, real tracking data
is. A request from someone who actually receives those parcels is worth a great
deal, because the status vocabulary can only be confirmed against live shipments.

That is also what the **Early release** badge above means: the integration works,
but its status mapping was inferred rather than observed. If one of your parcels
reports `unknown`, the integration logs a warning with a one-click report link —
please use it.
"""


def render_carriers(carriers: list[Carrier]) -> str:
    out = [CARRIERS_INTRO, ""]
    out.append(f"**{len(carriers)} carriers** and counting.\n")
    out.append("| | Carrier | Coverage | Connect with | Tracks | Version |")
    out.append("|---|---|---|---|---|---|")

    for c in carriers:
        icon = (
            f'<img src="assets/icons/{c.icon}" width="32" alt="{c.name}">'
            if c.icon
            else ""
        )
        name = f"**[{c.name}]({c.url})**<br><small>{c.blurb}</small>"
        if c.early:
            name += '<br>:material-flask: *Early release — status mapping unconfirmed*'
        coverage = f"{c.flags} {c.region}".strip()
        tracks = (
            "Incoming & outgoing"
            if c.directions == "incoming+outgoing"
            else "Incoming"
        )
        badge = (
            f"[![](https://img.shields.io/github/v/release/{ORG}/{c.repo}"
            f"?style=flat-square&label=&color=41BDF5)]({c.url}/releases)"
        )
        out.append(f"| {icon} | {name} | {coverage} | {c.connect} | {tracks} | {badge} |")

    out.append(
        CARRIERS_FOOTER.format(
            aggregator_url=f"https://github.com/{ORG}/{AGGREGATOR}",
            request_url=(
                f"https://github.com/{ORG}/.github/discussions/new"
                "?category=carrier-requests"
            ),
        )
    )
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Page: automation cookbook
# --------------------------------------------------------------------------

AUTOMATIONS_INTRO = """\
# Automation cookbook

Every snippet on this page is pulled straight from the [Parcel Aggregator's
`examples/` folder]({examples_url}) when this site is built, so it always matches
the version that is actually shipped.

They are carrier-agnostic on purpose: they trigger on canonical
[`ParcelStatus`](contract.md#parcelstatus) values and the unified
`parcel_aggregator_*` events, so the same automation covers a carrier you install
next year without a single edit.

!!! tip "Where these go"
    Automations paste into **Settings → Automations → ⋮ → Edit in YAML**.
    Dashboard cards paste into any card's **Show code editor**.
"""

TITLE_RE = re.compile(r"^(?:alias|title):\s*(.+?)\s*$", re.MULTILINE)


def _describe(source: str) -> tuple[str, str]:
    """Split a leading ``#`` comment block off as the human description."""
    comment: list[str] = []
    for line in source.splitlines():
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if not text:
                # A bare "#" is a paragraph break. Take only the first
                # paragraph as the summary — the rest stays in the listing
                # below, where its line breaks survive.
                break
            comment.append(text)
        elif comment or not line.strip():
            break
    match = TITLE_RE.search(source)
    title = match.group(1).strip().strip("\"'") if match else ""
    return title, " ".join(comment)


def _snippets(folder: str) -> list[tuple[str, str, str, str]]:
    items = []
    for entry in sorted(gh_dir(AGGREGATOR, f"examples/{folder}"), key=lambda e: e["name"]):
        if not entry["name"].endswith((".yaml", ".yml")):
            continue
        raw = gh_file(AGGREGATOR, entry["path"])
        if raw is None:
            continue
        source = raw.decode("utf-8")
        title, description = _describe(source)
        fallback = entry["name"].rsplit(".", 1)[0].replace("_", " ").capitalize()
        items.append((title or fallback, description, source.strip(), entry["name"]))
    return items


def render_automations() -> str:
    examples_url = f"https://github.com/{ORG}/{AGGREGATOR}/tree/main/examples"
    out = [AUTOMATIONS_INTRO.format(examples_url=examples_url), ""]

    sections = [
        ("automations", "Automations", "Paste into the automation YAML editor."),
        ("dashboards", "Dashboard cards", "Paste into a card's code editor."),
    ]
    for folder, heading, blurb in sections:
        snippets = _snippets(folder)
        if not snippets:
            continue
        out.append(f"## {heading}\n")
        out.append(f"{blurb}\n")
        for title, description, source, filename in snippets:
            out.append(f'??? example "{title}"')
            if description:
                out.append(f"    {description}\n")
            out.append("    ```yaml")
            out.extend(f"    {line}" if line.strip() else "" for line in source.splitlines())
            out.append("    ```\n")
            out.append(f"    [View on GitHub]({examples_url}/{folder}/{filename})\n")

    out.append("## Carrier-specific events\n")
    out.append(
        "Prefer the unified stream above. When you genuinely need one carrier — "
        "or the raw carrier payload the aggregator strips — subscribe to that "
        "carrier's own event instead: `<domain>_parcel_registered`, "
        "`<domain>_parcel_status_changed`, `<domain>_parcel_delivered`, "
        "`<domain>_parcel_delivery_time_changed`. See the "
        "[parcel contract](contract.md#events) for the payload.\n"
    )
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------


def main() -> int:
    try:
        carriers = collect_carriers()
        (DOCS / "carriers.md").write_text(render_carriers(carriers), encoding="utf-8")
        (DOCS / "automations.md").write_text(render_automations(), encoding="utf-8")
    except GenerateError as err:
        print(f"\n❌ generate.py: {err}\n", file=sys.stderr)
        return 1

    print(f"✓ docs/carriers.md      ({len(carriers)} carriers)")
    print("✓ docs/automations.md")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
