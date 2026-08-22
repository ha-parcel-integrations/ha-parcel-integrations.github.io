#!/usr/bin/env python3
"""Generate the pages that must never be hand-written.

Four pages on this site describe things that already have a source of truth
somewhere else in the org:

* ``docs/carriers.md``      — every carrier repo, its version and its icon
* ``docs/capabilities.md``  — which optional contract fields each carrier's
  own ``const.py`` declares it populates
* ``docs/automations.md``   — the aggregator's ``examples/automations/`` folder
* ``docs/dashboards.md``    — the aggregator's ``examples/dashboards/`` folder

All of them are rebuilt from the GitHub API on every deploy. Nothing here is
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
import unicodedata
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

import yaml

ORG = "ha-parcel-integrations"
API = "https://api.github.com"

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
BUILD = ROOT / "build"
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

# English names for every ISO 3166-1 alpha-2 code that appears in
# data/carriers.yml's `countries` lists — used to label the carriers-page
# country filter. Only the codes actually in use need to be here; render_carriers
# fails the build if a carrier uses a code this map does not, so the filter
# never silently mislabels or drops a country.
COUNTRY_NAMES = {
    "AR": "Argentina",
    "AT": "Austria",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "BR": "Brazil",
    "CH": "Switzerland",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "HR": "Croatia",
    "HU": "Hungary",
    "ID": "Indonesia",
    "IE": "Ireland",
    "IN": "India",
    "IT": "Italy",
    "LI": "Liechtenstein",
    "LT": "Lithuania",
    "LU": "Luxembourg",
    "LV": "Latvia",
    "MD": "Moldova",
    "MY": "Malaysia",
    "NL": "Netherlands",
    "NO": "Norway",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "TH": "Thailand",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
}

# The optional parcel-contract fields a carrier may or may not populate. Order
# here is display order on docs/capabilities.md. Keep the keys in sync with
# ha-carrier-template's KNOWN_CAPABILITIES — that is the copy every carrier
# repo's own CAPABILITIES constant is validated against, this is only used to
# label and order them on the page.
CAPABILITY_LABELS = {
    "delivery_window": ("Delivery window", "`planned_from` / `planned_to`"),
    "pickup_point": ("Pickup point name", "`pickup_point`"),
    "weight": ("Weight", "`weight`"),
    "dimensions": ("Dimensions", "`dimensions`"),
    "url": ("Tracking link", "`url`"),
    "history": ("Status history", "opt-in `history`"),
}

# ``^`` anchors to the start of a line (with MULTILINE) so this does not also
# match inside ``KNOWN_CAPABILITIES = frozenset({...})``, which contains
# "CAPABILITIES = frozenset(" as a literal substring.
CAPABILITIES_RE = re.compile(
    r"^CAPABILITIES\s*=\s*frozenset\(\s*\{(.*?)\}\s*\)", re.DOTALL | re.MULTILINE
)

# Finished Lovelace cards, built by other people, that read this suite's
# sensors on their own. Every carrier README links these two under "Community
# Lovelace cards"; the site says the same thing in one place so the credit is
# not buried in 23 READMEs. Keep this list in step with the READMEs and with
# ha-carrier-template/scaffold/README.md.
COMMUNITY_CARDS = [
    (
        "HKI Parcels Card",
        "jonisnet/hki-parcels-card",
        "jonisnet",
        (
            "Every carrier you run in one card, with tabs for in transit, "
            "delivered, sent and PostNL letterbox scans, a per-parcel delivery "
            "tracker, and a **+ Add parcel** control for the account-less "
            "carriers. Visual editor, no YAML."
        ),
    ),
    (
        "Package Tracker Card",
        "klaptafel/ha-package-tracker-card",
        "klaptafel",
        (
            "Drop it on a dashboard with no configuration at all and it finds "
            "every parcel sensor you have, deduplicated when the same parcel "
            "arrives through two sources, with an expandable event timeline "
            "per package and filters per carrier, status or direction."
        ),
    ),
]

# Lovelace plugins our example dashboards lean on — helpers inside a card,
# not cards in their own right. Keyed by the string as it appears after
# ``custom:`` in YAML, because that is what _custom_cards matches against.
CUSTOM_CARDS = {
    "auto-entities": (
        "thomasloven/lovelace-auto-entities",
        "Thomas Lovén",
        (
            "Fills a card's entity list from a filter instead of a hand-written "
            "list, so parcels that only exist tomorrow still show up"
        ),
    ),
    "template-entity-row": (
        "thomasloven/lovelace-template-entity-row",
        "Thomas Lovén",
        (
            "Renders a template as an entities-card row — how you get a value "
            "that lives on an attribute onto its own line"
        ),
    ),
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
    capabilities: frozenset[str] | None

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
        # data/carriers.yml stores `input` in mid-sentence form ("tracking
        # number"); this column starts a line, so it gets a capital here.
        if not self.input:
            return label
        detail = self.input[0].upper() + self.input[1:]
        # The sub-line only earns its space when it says more than the label.
        if detail == label:
            return label
        return f"{label}<br><small>{detail}</small>"


def _alpha_key(carrier: Carrier) -> tuple[str, str]:
    """Sort key that files accented names where a reader looks for them.

    Plain code-point order puts "Österreichische Post" after Z, because ö is
    U+00F6. Stripping the combining marks (NFKD, then drop non-ASCII) files it
    under O instead. The original name is the tiebreaker, so two carriers that
    fold to the same ASCII still get a stable order.
    """
    folded = unicodedata.normalize("NFKD", carrier.name)
    ascii_only = folded.encode("ascii", "ignore").decode()
    return (ascii_only.lower(), carrier.name.lower())


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


def _capabilities_of(repo: str, domain: str) -> frozenset[str] | None:
    """Parse ``CAPABILITIES`` out of the carrier's const.py.

    Returns ``None`` — not an empty set — when the constant is absent, so the
    page can say "not yet documented" instead of lying that the carrier
    supports nothing. Not every carrier repo has migrated to declaring this
    yet; that is not a build failure the way a missing manifest.json is.
    """
    raw = gh_file(repo, f"custom_components/{domain}/const.py")
    if raw is None:
        return None
    match = CAPABILITIES_RE.search(raw.decode("utf-8"))
    if not match:
        return None
    return frozenset(re.findall(r'"([^"]+)"', match.group(1)))


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

        shared = dict(
            repo=repo,
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
            icon=icon_name,
            capabilities=_capabilities_of(repo, domain),
        )

        carriers.append(Carrier(name=manifest.get("name", repo), blurb=meta["blurb"], **shared))

        # A repo answering to a second brand name (e.g. a carrier's own
        # locker network) gets its own row everywhere carriers are listed —
        # same repo link/version/icon, its own name and blurb.
        for alias in meta.get("aliases") or []:
            carriers.append(Carrier(name=alias["name"], blurb=alias["blurb"], **shared))

    carriers.sort(key=_alpha_key)
    return carriers


# --------------------------------------------------------------------------
# Page: carriers
# --------------------------------------------------------------------------

CARRIERS_INTRO = """\
---
hide:
  - navigation
description: >-
  Every carrier you can track packages with in Home Assistant — PostNL, DHL,
  DPD, GLS, PostNord, Hermes, Packeta, Correos, Swiss Post and more.
---

# Carriers

Every integration below speaks the same [parcel contract](contract.md): the same
`ParcelStatus` values, the same parcel fields, the same events. Install only the
ones that deliver to you — each works on its own, and none of them depends on
another.

Not every carrier's API exposes every optional field the contract allows —
`null` for those is normal, not a bug. See the
[capability comparison](capabilities.md) for which carrier gives you what.

Install instructions live on [Getting started](install.md); each carrier's own
README covers its options in full.
"""

CARRIERS_FOOTER = """
## Parcel Aggregator (optional)

Running more than one carrier? The [Parcel Aggregator]({aggregator_url}) saves you
from writing the same automation once per carrier. It talks to no carrier API of
its own — it reads the sensors and events the carriers already publish and
re-emits them as one merged set:

- summed count sensors with a `by_carrier` breakdown
- a single `parcel_aggregator_parcel_*` event stream
- one `next_delivery` timestamp and one combined deliveries calendar

It is genuinely optional: no carrier integration needs it, and skipping it costs
you nothing but the merging. Carriers you have not installed are skipped
silently, and a carrier you add later is picked up automatically — no reload, no
update here.

## Missing your carrier?

[Request it]({request_url}) — the code is rarely the blocker, real tracking data
is. A request from someone who actually receives those parcels is worth a great
deal, because the status vocabulary can only be confirmed against live shipments.

That is also what the **Early release** badge above means: the integration works,
but its status mapping was inferred rather than observed. If one of your parcels
reports `unknown`, the integration logs a warning with a one-click report link —
please use it.
"""


def _country_filter_options(carriers: list[Carrier]) -> str:
    """<option> tags for every country any carrier lists, sorted by name.

    Raises the same GenerateError style as ``_reconcile`` when a carrier uses
    a code COUNTRY_NAMES does not know — the filter must never silently
    mislabel a country or, worse, drop it from the dropdown.
    """
    codes = {code for c in carriers for code in c.countries}
    unknown = sorted(codes - set(COUNTRY_NAMES))
    if unknown:
        raise GenerateError(
            "data/carriers.yml uses country code(s) not in generate.py's "
            f"COUNTRY_NAMES: {', '.join(unknown)}. Add them there."
        )
    ordered = sorted(codes, key=lambda code: COUNTRY_NAMES[code])
    return "\n".join(
        f'<option value="{code}">{_flag(code)} {COUNTRY_NAMES[code]}</option>'
        for code in ordered
    )


def render_carriers(carriers: list[Carrier]) -> str:
    out = [CARRIERS_INTRO, ""]
    out.append(f'<div id="carriers-block" markdown="1">\n')
    out.append(
        '<div class="carriers-filter">\n'
        '<label for="carrier-country-filter">Filter by country</label>\n'
        '<select id="carrier-country-filter">\n'
        '<option value="">All countries</option>\n'
        f"{_country_filter_options(carriers)}\n"
        "</select>\n"
        '<span id="carrier-country-count" role="status"></span>\n'
        "</div>\n"
    )
    out.append(f"**{len(carriers)} carriers** and counting.\n")
    out.append("| | Carrier | Coverage | Connect with | Tracks | Version |")
    out.append("|---|---|---|---|---|---|")

    for c in carriers:
        # Root-relative, not "assets/...": Material serves this page at
        # /carriers/, and MkDocs does not rewrite src attributes inside raw
        # HTML, so a relative path resolves to /carriers/assets/... and 404s.
        icon = (
            f'<img src="/assets/icons/{c.icon}" width="32" alt="{c.name}">'
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
        if c.early:
            badge += (
                "<br>![](https://img.shields.io/badge/-BETA-orange?style=flat-square)"
            )
        out.append(f"| {icon} | {name} | {coverage} | {c.connect} | {tracks} | {badge} |")

    # Row order here must match the <tr> order above exactly — carriers-filter.js
    # zips this against the table's tbody rows by index, not by carrier name.
    out.append(
        '\n<script type="application/json" id="carriers-country-data">'
        + json.dumps([c.countries for c in carriers])
        + "</script>\n"
        "</div>\n"
    )

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
# Page: capabilities
# --------------------------------------------------------------------------

CAPABILITIES_INTRO = """\
---
hide:
  - navigation
description: >-
  Which optional parcel contract fields each carrier actually populates —
  weight, dimensions, delivery window, pickup point, tracking link and status
  history — so a null value reads as "this carrier doesn't have it" rather
  than "something is broken".
---

# Capability comparison

Every carrier publishes the same [parcel shape](contract.md#the-parcel-shape),
but the fields marked optional there are only as complete as the carrier's own
API. A `null` on one of these is not a bug — it means the carrier itself never
told us. This page is generated from each carrier's own source, so it changes
the moment a carrier starts (or stops) exposing something new.
"""

CAPABILITIES_FOOTER = """
**{count} of {total} carriers** have declared their capabilities so far — the
rest show "?" until their own repo migrates. This is an ongoing rollout, not a
claim that the undeclared ones support nothing.

## Reading this table

- 🟢 — the carrier's own tests prove this field comes back non-null for at
  least some parcels.
- 🔴 — the carrier's API does not expose this, so the field is always `null`.
  Nothing to configure or work around.
- ? — this carrier has not declared its capabilities yet.

See the [parcel contract](contract.md#the-parcel-shape) for what each column
actually means on the wire.
"""


SUPPORTED = "🟢"
UNSUPPORTED = "🔴"
UNDECLARED = "?"


def render_capabilities(carriers: list[Carrier]) -> str:
    keys = list(CAPABILITY_LABELS)
    out = [CAPABILITIES_INTRO, ""]
    out.append("| Carrier | " + " | ".join(CAPABILITY_LABELS[k][0] for k in keys) + " |")
    out.append("|---|" + "---|" * len(keys))

    declared = 0
    for c in carriers:
        if c.capabilities is None:
            cells = " | ".join(UNDECLARED for _ in keys)
        else:
            declared += 1
            cells = " | ".join(
                SUPPORTED if k in c.capabilities else UNSUPPORTED for k in keys
            )
        out.append(f"| [{c.name}]({c.url}) | {cells} |")

    out.append(CAPABILITIES_FOOTER.format(count=declared, total=len(carriers)))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Pages: automation cookbook & dashboard cards
#
# Both are the same machinery over a different examples/ subfolder, so they
# share everything below except their own intro.
# --------------------------------------------------------------------------

AUTOMATIONS_INTRO = """\
---
hide:
  - navigation
description: >-
  Copy-paste Home Assistant automations for package tracking — delivery
  notifications, daily summaries and calendar entries, for any carrier.
---

# Automation cookbook

Every automation on this page is pulled straight from the [Parcel Aggregator's
`examples/automations/` folder]({examples_url}/automations) when this site is
built, so it always matches the version that is actually shipped. Looking for
[dashboard cards](dashboards.md)? They have their own page.

They are carrier-agnostic on purpose: they trigger on canonical
[`ParcelStatus`](contract.md#parcelstatus) values and the unified
`parcel_aggregator_*` events, so the same automation covers a carrier you install
next year without a single edit.

!!! note "Not running the aggregator?"
    These work per carrier too. Swap `parcel_aggregator_` for the carrier's own
    domain (`postnl_parcel_status_changed`) and the aggregator's sensors for that
    carrier's own. The parcel data inside is identical — see the
    [contract](contract.md).

!!! tip "Where these go"
    **Settings → Automations & scenes → Create automation → Create new
    automation**, then **⋮ → Edit in YAML** and paste over what is there.
"""

DASHBOARDS_INTRO = """\
---
hide:
  - navigation
description: >-
  Copy-paste Home Assistant dashboard cards for package tracking — a parcel
  table, a per-carrier breakdown and a next-delivery card, for any carrier.
---

# Dashboard cards

Cards that put your parcels on a dashboard: what is on its way, from whom, and
when it lands. Each one is pulled straight from the [Parcel Aggregator's
`examples/dashboards/` folder]({examples_url}/dashboards) when this site is
built, so it always matches the version that is actually shipped. For
notifications and other logic, see the [automation cookbook](automations.md).

Like the automations, they are carrier-agnostic: they read the aggregator's
merged sensors and the canonical parcel fields, so a card keeps working when you
add a carrier — no new rows to write.

Would rather not write YAML at all? Two community projects package all of this
into a finished card that finds your sensors by itself — see [ready-made parcel
cards](#ready-made-parcel-cards) below.

!!! note "Not running the aggregator?"
    These work per carrier too. Swap the aggregator's sensors for the carrier's
    own (`sensor.postnl_incoming_parcels`, …). The `parcels` attribute holds the
    same fields either way — see the [contract](contract.md#the-parcel-shape).
    Several carriers also ship dashboard examples of their own, in that repo's
    `examples/dashboards/` folder.

!!! tip "Where these go"
    Open your dashboard, **✏️ → + Add card → Manual**, and paste over the
    contents. On a card that already exists: **⋮ → Edit → Show code editor**.
"""

COMMUNITY_CARDS_SECTION = """\
## Ready-made parcel cards

The snippets above are deliberately plain — they use cards Home Assistant already
ships, so nothing extra has to be installed. If you would rather have a finished
parcel card, two community projects build one on top of these same sensors and
detect your carriers automatically:

{cards}

Install either through **HACS → Custom repositories**, category **Dashboard**.

Both are independent projects, built and maintained by their authors and not by
this org. The credit for them is theirs — and so are the bug reports and feature
requests, which belong in their own trackers rather than in a carrier repo here.

## Plugins the snippets use

A snippet that needs more than a built-in card reaches for one of these two
Lovelace plugins instead. They are helpers *inside* a card rather than cards of
their own, also installed through HACS:

| Plugin | By | What it adds |
|---|---|---|
{rows}

Neither is required. Every snippet that uses one says in its comments what to
fall back to, and the parcel data sits on the sensor's attributes either way.
"""

CUSTOM_RE = re.compile(r"custom:([a-z0-9_-]+)")

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


def _render_snippets(
    snippets: list[tuple[str, str, str, str]], folder: str, examples_url: str
) -> list[str]:
    out: list[str] = []
    for title, description, source, filename in snippets:
        out.append(f'??? example "{title}"')
        if description:
            out.append(f"    {description}\n")
        out.append("    ```yaml")
        out.extend(f"    {line}" if line.strip() else "" for line in source.splitlines())
        out.append("    ```\n")
        out.append(f"    [View on GitHub]({examples_url}/{folder}/{filename})\n")
    return out


def _custom_cards(sources: list[str]) -> list[str]:
    """Every ``custom:`` card the snippets reference, credited.

    An unknown one fails the build on purpose: a card that needs a HACS plugin
    nobody named is a snippet that silently does not render for the reader.
    """
    used = sorted({m for source in sources for m in CUSTOM_RE.findall(source)})
    unknown = [name for name in used if name not in CUSTOM_CARDS]
    if unknown:
        raise GenerateError(
            "These custom Lovelace cards appear in the aggregator's examples "
            "but are not in CUSTOM_CARDS — add them (repo, author, what it "
            "adds) so the docs can credit and link them:\n    "
            + "\n    ".join(unknown)
        )
    return used


def render_automations() -> str:
    examples_url = f"https://github.com/{ORG}/{AGGREGATOR}/tree/main/examples"
    out = [AUTOMATIONS_INTRO.format(examples_url=examples_url), ""]
    out.append("## Automations\n")
    out.extend(_render_snippets(_snippets("automations"), "automations", examples_url))

    out.append("## Carrier-specific events\n")
    out.append(
        "Every carrier fires its own events, whether or not the aggregator is "
        "installed: `<domain>_parcel_registered`, "
        "`<domain>_parcel_status_changed`, `<domain>_parcel_delivered`, "
        "`<domain>_parcel_delivery_time_changed`. Use these when you run a "
        "single carrier, when you want one carrier to behave differently from "
        "the rest, or when you need the raw carrier payload the aggregator "
        "strips. See the [parcel contract](contract.md#events) for the "
        "payload.\n"
    )
    return "\n".join(out) + "\n"


def render_dashboards() -> str:
    examples_url = f"https://github.com/{ORG}/{AGGREGATOR}/tree/main/examples"
    snippets = _snippets("dashboards")
    out = [DASHBOARDS_INTRO.format(examples_url=examples_url), ""]
    out.append("## Cards\n")
    out.extend(_render_snippets(snippets, "dashboards", examples_url))

    # Credit the plugins the snippets above actually reach for. Carrier repos
    # use the same two in their own examples, so both stay listed even when
    # only one turns up in the aggregator's — see CUSTOM_CARDS.
    _custom_cards([source for _, _, source, _ in snippets])
    rows = [
        f"| [`custom:{name}`](https://github.com/{repo}) "
        f"| [{author}](https://github.com/{repo.split('/')[0]}) | {does} |"
        for name, (repo, author, does) in sorted(CUSTOM_CARDS.items())
    ]
    # A card list wants room for a sentence about each one; the plugins below
    # fit a table because there is only one thing to say about them.
    cards = "\n\n".join(
        f"-   **[{name}](https://github.com/{repo})** — by "
        f"[{author}](https://github.com/{author})\n\n    {does}"
        for name, repo, author, does in COMMUNITY_CARDS
    )
    out.append(COMMUNITY_CARDS_SECTION.format(cards=cards, rows="\n".join(rows)))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
# Page: the org profile README
#
# github.com/ha-parcel-integrations shows .github/profile/README.md. It carries
# the same carrier list as this site, so it is generated from the same data and
# pushed by scripts/push_profile.py — a second hand-maintained table is exactly
# the drift this repo exists to prevent.
# --------------------------------------------------------------------------

PROFILE_HEADER = """\
<!-- Generated by ha-parcel-integrations.github.io/scripts/generate.py — do not edit by hand. -->

# Home Assistant parcel integrations

A suite of [Home Assistant](https://www.home-assistant.io/) custom integrations that track your parcels across carriers and countries — every one speaking the same canonical parcel contract, so your automations and dashboards work the same no matter who delivers.

📖 **[Read the docs]({site_url})** — carrier list, the parcel contract, and copy-paste automations and dashboard cards.

## Integrations
"""

PROFILE_FOOTER = """
📦 **Missing your carrier, or want one of these in another country?**
[Request it]({request_url}) —
the code is rarely the blocker, real tracking data is, so a request from
someone who receives those parcels helps most.

## How they fit together

Each carrier integration is standalone and normalises its data to a shared `ParcelStatus` enum and a common parcel shape, firing canonical events (`<carrier>_parcel_registered` / `_status_changed` / `_delivered` / `_delivery_time_changed`). Install just the carriers that deliver to you — nothing else is required.

Running several? The optional **Parcel Aggregator** subscribes to all of them and re-emits a unified stream, so you write one automation like *"when any parcel is out for delivery"* instead of one per carrier.

The full contract is documented at **[{site_host}]({site_url}contract/)**.

## Installation

All integrations are distributed via [HACS](https://hacs.xyz/). See
**[Getting started]({site_url}install/)** for the walkthrough, or each
repository's README for its own options.

## Support this project

Every integration here is free and MIT-licensed, and stays that way. Sponsoring
buys no features and no priority — it just says the work is worth continuing. See
**[the ways to help]({site_url}sponsor/)**, including ones that cost nothing.

[![Sponsor on GitHub](https://img.shields.io/badge/-Sponsor-EA4AAA?style=flat-square&logo=github-sponsors&logoColor=white)](https://github.com/sponsors/peternijssen)
[![Buy me a coffee](https://img.shields.io/badge/-Buy%20me%20a%20coffee-FFDD00?style=flat-square&logo=buymeacoffee&logoColor=black)](https://www.buymeacoffee.com/peternijssen)

## Community

💬 Questions or feedback? Join the discussion on the [Home Assistant community]({community_url}).

🐛 Found a bug, or does a parcel report an `unknown` status? That belongs in
the issue tracker of the integration itself.
"""

SITE_URL = f"https://{ORG}.github.io/"
COMMUNITY_URL = (
    "https://community.home-assistant.io/t/"
    "packages-postnl-dhl-nl-dpd-and-gls-parcel-integration/112433/"
)
REQUEST_URL = f"https://github.com/{ORG}/.github/discussions/new?category=carrier-requests"


def _profile_row(c: Carrier, icon_url: str, tracks: str) -> str:
    icon = f'<img src="{icon_url}" width="32" alt="{c.name}">'
    badge = (
        f"![](https://img.shields.io/github/v/release/{ORG}/{c.repo}"
        "?style=flat-square&label=&color=41BDF5)"
    )
    return f"| {icon} | [{c.repo}]({c.url}) | {badge} | {tracks} |"


def _tracks(c: Carrier) -> str:
    """The prose cell in the profile README's table.

    Regions keep their capitals (they are proper nouns) and are dropped when
    the blurb already names the country — "Spain's national postal operator
    (Spain)" helps nobody.
    """
    sentence = c.blurb
    if c.region and c.region.split()[0].lower() not in c.blurb.lower():
        sentence += f" ({c.region})"

    if c.auth == "account":
        access = "account-based"
    elif c.input:
        access = f"account-less, {c.input} only" if "+" not in c.input else f"account-less, {c.input}"
    else:
        access = "account-less"
    if c.directions == "incoming+outgoing":
        access += ", incoming & outgoing parcels"

    tracks = f"{sentence}; {access}."
    if c.early:
        tracks += (
            " **Early release:** the status mapping is still being confirmed "
            "against real parcels, "
            f"[help wanted]({c.url}/issues/new?template=unrecognised_status.yml)"
        )
    return tracks


def render_profile(carriers: list[Carrier]) -> str:
    out = [PROFILE_HEADER.format(site_url=SITE_URL)]
    out.append("| | Integration | Latest | Tracks |")
    out.append("|---|---|---|---|")

    for c in carriers:
        # Raw GitHub URLs, because the profile README renders on github.com and
        # cannot reach this site's asset paths.
        icon_url = (
            f"https://raw.githubusercontent.com/{ORG}/{c.repo}/main/"
            f"custom_components/{c.domain}/brand/icon.png"
        )
        out.append(_profile_row(c, icon_url, _tracks(c)))

    aggregator = _aggregator_carrier()
    if aggregator:
        icon_url = (
            f"https://raw.githubusercontent.com/{ORG}/{AGGREGATOR}/main/"
            f"custom_components/{aggregator.domain}/brand/icon.png"
        )
        out.append(
            _profile_row(
                aggregator,
                icon_url,
                "Rolls every carrier above into one unified set of sensors, a "
                "combined deliveries calendar, and a single event stream",
            )
        )

    out.append(
        PROFILE_FOOTER.format(
            site_url=SITE_URL,
            site_host=f"{ORG}.github.io",
            request_url=REQUEST_URL,
            community_url=COMMUNITY_URL,
        )
    )
    return "\n".join(out) + "\n"


def _aggregator_carrier() -> Carrier | None:
    """Minimal Carrier for the aggregator — it has no data/carriers.yml entry."""
    domain = _domain_of(AGGREGATOR)
    tag = latest_release(AGGREGATOR)
    if not domain or tag is None:
        return None
    return Carrier(
        repo=AGGREGATOR,
        name="Parcel Aggregator",
        domain=domain,
        version=tag.lstrip("v"),
        url=f"https://github.com/{ORG}/{AGGREGATOR}",
        region="",
        countries=[],
        auth="none",
        input=None,
        directions="incoming+outgoing",
        blurb="",
        icon=None,
        capabilities=None,
    )


# --------------------------------------------------------------------------


def main() -> int:
    try:
        carriers = collect_carriers()
        (DOCS / "carriers.md").write_text(render_carriers(carriers), encoding="utf-8")
        (DOCS / "capabilities.md").write_text(render_capabilities(carriers), encoding="utf-8")
        (DOCS / "automations.md").write_text(render_automations(), encoding="utf-8")
        (DOCS / "dashboards.md").write_text(render_dashboards(), encoding="utf-8")
        BUILD.mkdir(parents=True, exist_ok=True)
        (BUILD / "profile-README.md").write_text(render_profile(carriers), encoding="utf-8")
        # Consumed by scripts/sync_org.py to point each repo's About box here.
        # dict.fromkeys dedupes repos that carry more than one alias row above,
        # preserving first-seen order.
        (BUILD / "repos.json").write_text(
            json.dumps(list(dict.fromkeys(c.repo for c in carriers)) + [AGGREGATOR], indent=2),
            encoding="utf-8",
        )
    except GenerateError as err:
        print(f"\n❌ generate.py: {err}\n", file=sys.stderr)
        return 1

    print(f"✓ docs/carriers.md          ({len(carriers)} carriers)")
    print("✓ docs/capabilities.md")
    print("✓ docs/automations.md")
    print("✓ docs/dashboards.md")
    print("✓ build/profile-README.md   (pushed by scripts/sync_org.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
