#!/usr/bin/env python3
"""Generate the pages that must never be hand-written.

Three pages on this site describe things that already have a source of truth
somewhere else in the org:

* ``docs/carriers.md``      — every carrier repo, its version and its icon,
  plus the capabilities its own ``const.py`` declares, shown per carrier
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
import html
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
ALIAS_ICONS = ROOT / "data" / "icons"

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
    "trackingnr": "Tracking code",
    "apikey": "Official API key",
}

# The same three mechanisms as a one-word badge on the carrier tile, where
# there is no room for the sentence AUTH_LABEL spells out. Both maps are
# keyed by the auth kinds data/carriers.yml declares, so a kind can never
# have a badge and no label (or the reverse).
AUTH_PILL = {
    "account": "Account",
    "trackingnr": "Tracking",
    "apikey": "API",
}

# English names for every ISO 3166-1 alpha-2 code that appears in
# data/carriers.yml's `countries` lists — used to label the carriers-page
# country filter. Only the codes actually in use need to be here; render_carriers
# fails the build if a carrier uses a code this map does not, so the filter
# never silently mislabels or drops a country.
COUNTRY_NAMES = {
    "AR": "Argentina",
    "AT": "Austria",
    "AU": "Australia",
    "BE": "Belgium",
    "BG": "Bulgaria",
    "BR": "Brazil",
    "CA": "Canada",
    "CH": "Switzerland",
    "CY": "Cyprus",
    "CZ": "Czechia",
    "DE": "Germany",
    "DK": "Denmark",
    "EE": "Estonia",
    "ES": "Spain",
    "FI": "Finland",
    "FR": "France",
    "GB": "United Kingdom",
    "GR": "Greece",
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
    "NZ": "New Zealand",
    "PH": "Philippines",
    "PL": "Poland",
    "PT": "Portugal",
    "RO": "Romania",
    "RS": "Serbia",
    "SE": "Sweden",
    "SI": "Slovenia",
    "SK": "Slovakia",
    "TH": "Thailand",
    "UA": "Ukraine",
    "US": "United States",
    "VN": "Vietnam",
}

# The optional parcel-contract fields a carrier may or may not populate. Order
# here is the column order in each carrier's capability table. Keep the keys in sync with
# ha-carrier-template's KNOWN_CAPABILITIES — that is the copy every carrier
# repo's own CAPABILITIES constant is validated against, this is only used to
# label and order them on the page.
CAPABILITY_LABELS = {
    "delivery_window": ("Delivery window", "`planned_from` / `planned_to`"),
    "pickup_point": ("Pickup point", "`pickup_point`"),
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

# A carrier with more than one backend (a country-specific transport, not
# just a config option) declares CAPABILITIES_BY_VARIANT instead of the flat
# CAPABILITIES above — one frozenset per backend/country, so a field only
# some backends populate doesn't get silently intersected away (or
# overclaimed) for the carrier as a whole. See ha-dpd's or ha-gls's
# const.py. Matched as its own statement (anchored, non-greedy up to the
# closing brace of the outer dict) rather than reusing CAPABILITIES_RE,
# because the nested ``frozenset({...})`` calls would confuse a single
# regex written to stop at the first ``}``.
CAPABILITIES_BY_VARIANT_RE = re.compile(
    r"^CAPABILITIES_BY_VARIANT\s*=\s*\{(.*?)\n\}", re.DOTALL | re.MULTILINE
)
CAPABILITIES_VARIANT_ENTRY_RE = re.compile(
    r'"([^"]+)"\s*:\s*frozenset\(\s*\{(.*?)\}\s*\)', re.DOTALL
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


@dataclass(frozen=True)
class Connection:
    """One way to connect a carrier: an auth kind and what the user types.

    ``variant`` is None for the single-source carriers (almost all of them)
    and the backend's label for a carrier whose sources authenticate
    differently — USPS signs in to Informed Delivery but wants a developer
    key for API Tracking, and one "Connect with" answer would be a lie.
    """

    auth: str
    input: str | None
    variant: str | None = None


@dataclass
class Carrier:
    repo: str
    name: str
    domain: str
    version: str
    url: str
    region: str
    countries: list[str]
    connections: tuple[Connection, ...]
    directions: str
    blurb: str
    icon: str | None
    # A single frozenset for a single-backend carrier, a dict of
    # {variant_label: frozenset} for a multi-backend one (declared as
    # CAPABILITIES_BY_VARIANT in that carrier's own const.py — see
    # _capabilities_of), or None when undeclared.
    capabilities: frozenset[str] | dict[str, frozenset[str]] | None
    # The primary brand this row is an alias of, when it is one. Seven rows
    # are a second brand on somebody else's repo. Each carries its own logo
    # from data/icons where the two brands look different; the two that share
    # a visual identity with their parent (Zásilkovna with Packeta, Intelcom
    # with Dragonfly) deliberately inherit the parent's, because a separate
    # file would be the same artwork twice. The tile names the parent out loud
    # either way.
    parent: str | None = None

    @property
    def early(self) -> bool:
        """Below 1.0.0 means unconfirmed data — say so, loudly."""
        return self.version.split(".")[0] == "0"

    @property
    def flags(self) -> str:
        return " ".join(_flag(c) for c in self.countries)

    @property
    def connect(self) -> str:
        return "<br>".join(self._connect_line(c) for c in self.connections)

    @staticmethod
    def _connect_line(conn: Connection) -> str:
        label = AUTH_LABEL[conn.auth]
        # A carrier whose backends authenticate differently names each one,
        # so the row says which answer belongs to which source.
        if conn.variant:
            label = f"**{conn.variant}** — {label}"
        # data/carriers.yml stores `input` in mid-sentence form ("tracking
        # code"); this column starts a line, so it gets a capital here.
        if not conn.input:
            return label
        detail = conn.input[0].upper() + conn.input[1:]
        # The sub-line only earns its space when it says more than the label.
        if detail == AUTH_LABEL[conn.auth]:
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


def _capabilities_of(
    repo: str, domain: str
) -> frozenset[str] | dict[str, frozenset[str]] | None:
    """Parse ``CAPABILITIES`` (or ``CAPABILITIES_BY_VARIANT``) out of const.py.

    Returns ``None`` — not an empty set — when neither constant is present,
    so the page can say "not yet documented" instead of lying that the
    carrier supports nothing. Not every carrier repo has migrated to
    declaring this yet; that is not a build failure the way a missing
    manifest.json is.

    A carrier that declares the multi-backend form gets a ``dict`` back,
    keyed by variant label in declaration order (a plain dict, so that order
    survives — see _payload). Tried first: a carrier is expected
    to declare exactly one of the two forms, never both.
    """
    raw = gh_file(repo, f"custom_components/{domain}/const.py")
    if raw is None:
        return None
    text = raw.decode("utf-8")

    variant_match = CAPABILITIES_BY_VARIANT_RE.search(text)
    if variant_match:
        variants = {
            label: frozenset(re.findall(r'"([^"]+)"', fields))
            for label, fields in CAPABILITIES_VARIANT_ENTRY_RE.findall(
                variant_match.group(1)
            )
        }
        if variants:
            return variants

    match = CAPABILITIES_RE.search(text)
    if not match:
        return None
    return frozenset(re.findall(r'"([^"]+)"', match.group(1)))


def _connections_of(
    repo: str,
    meta: dict,
    capabilities: frozenset[str] | dict[str, frozenset[str]] | None,
) -> tuple[Connection, ...]:
    """Read `auth`/`input` out of one carriers.yml entry.

    Scalar `auth` is the common form. A mapping is the variant-keyed form,
    keyed by the same backend labels the carrier declares in its own
    CAPABILITIES_BY_VARIANT, so a carrier's connection detail and its
    capability table name the sources identically — a mismatch fails the
    build rather than quietly listing a backend under two different names.
    """
    auth = meta["auth"]

    if isinstance(auth, str):
        return (Connection(auth=_checked_auth(repo, auth), input=meta.get("input")),)

    if not isinstance(auth, dict) or not auth:
        raise GenerateError(
            f"{repo}: `auth` must be an auth kind or a non-empty mapping of "
            "backend label -> {kind, input}"
        )
    if meta.get("input") is not None:
        raise GenerateError(
            f"{repo}: `input` belongs inside each backend when `auth` is "
            "variant-keyed, not next to it"
        )
    if isinstance(capabilities, dict):
        unknown = sorted(set(auth) - set(capabilities))
        if unknown:
            raise GenerateError(
                f"{repo}: `auth` names backend(s) {', '.join(unknown)}, which "
                "CAPABILITIES_BY_VARIANT in the carrier's const.py does not "
                f"declare (it has {', '.join(capabilities)})"
            )

    connections = []
    for label, spec in auth.items():
        if not isinstance(spec, dict) or "kind" not in spec:
            raise GenerateError(
                f"{repo}: backend {label} needs a mapping with a `kind` "
                "(and optionally an `input`)"
            )
        connections.append(
            Connection(
                auth=_checked_auth(repo, spec["kind"]),
                input=spec.get("input"),
                variant=label,
            )
        )
    return tuple(connections)


def _checked_auth(repo: str, auth: str) -> str:
    if auth not in AUTH_LABEL:
        raise GenerateError(
            f"{repo}: unknown auth kind {auth!r} — expected one of "
            f"{', '.join(AUTH_LABEL)}"
        )
    return auth


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
        capabilities = _capabilities_of(repo, domain)

        # The repo's own brand icon is the default. A repo that ships as one
        # integration but lists here under two brand names (Posten Bring)
        # overrides it, so the primary row carries one brand's mark and the
        # alias row the other. HA and HACS keep reading the repo's icon —
        # this override is the site listing only, exactly like `name`.
        icon_name = None
        if primary_icon := meta.get("icon"):
            src = ALIAS_ICONS / primary_icon
            if not src.is_file():
                raise GenerateError(f"{repo}: icon {src} is missing")
            (ICONS / primary_icon).write_bytes(src.read_bytes())
            icon_name = primary_icon
        elif icon_bytes := gh_file(repo, f"custom_components/{domain}/brand/icon.png"):
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
            directions=meta.get("directions", "incoming"),
            icon=icon_name,
            capabilities=capabilities,
            connections=_connections_of(repo, meta, capabilities),
        )

        name = meta.get("name") or manifest.get("name", repo)
        carriers.append(Carrier(name=name, blurb=meta["blurb"], **shared))

        # A repo answering to a second brand name (e.g. a carrier's own
        # locker network) gets its own row everywhere carriers are listed —
        # same repo link/version, its own name and blurb (and optionally its own
        # icon, read from data/icons — the repo only ships the primary brand's). region/countries
        # default to the primary entry's but may be narrowed when the two
        # brands don't cover the same territory (e.g. one brand per country).
        for alias in meta.get("aliases") or []:
            alias_shared = shared | {"parent": name} | {
                k: alias[k] for k in ("region", "countries") if k in alias
            }
            if alias_icon := alias.get("icon"):
                src = ALIAS_ICONS / alias_icon
                if not src.is_file():
                    raise GenerateError(f"{repo}: alias {alias['name']} icon {src} is missing")
                (ICONS / alias_icon).write_bytes(src.read_bytes())
                alias_shared["icon"] = alias_icon
            carriers.append(Carrier(name=alias["name"], blurb=alias["blurb"], **alias_shared))

    carriers.sort(key=_alpha_key)
    return carriers


# --------------------------------------------------------------------------
# Page: carriers
# --------------------------------------------------------------------------

CARRIERS_INTRO = """\
---
description: >-
  Every carrier you can track packages with in Home Assistant — PostNL, DHL,
  DPD, GLS, PostNord, Hermes, Packeta, Correos, Swiss Post and more.
---

# Carriers

Every integration below speaks the same [parcel contract](contract.md): the same
`ParcelStatus` values, the same parcel fields, the same events. Install only the
ones that deliver to you — each works on its own, and none of them depends on
another.

Pick a country to narrow the list, or a connection type to see which carriers
work without an account. **Select a carrier** for its capabilities: which
optional contract fields it actually populates, what it needs from you, and
where it delivers.

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


def _slug(carrier: Carrier) -> str:
    """Stable id for one row — what ``/carriers/#gls`` opens.

    Built from the display name, not the repo, because aliases share a repo
    and each one is its own card. Accents fold the same way they do in
    _alpha_key, so the fragment stays typeable.
    """
    folded = unicodedata.normalize("NFKD", carrier.name)
    ascii_only = folded.encode("ascii", "ignore").decode().lower()
    return re.sub(r"-+", "-", re.sub(r"[^a-z0-9]+", "-", ascii_only)).strip("-")


def _payload(carriers: list[Carrier]) -> str:
    """Everything the detail dialog needs, as one JSON blob.

    The card markup carries what the page shows at rest (name, version,
    badges, flags); this carries the rest — capabilities, coverage prose,
    per-backend connection detail — so a page with 50+ carriers is not 50+
    hidden dialogs in the DOM.
    """
    rows = []
    for c in carriers:
        if isinstance(c.capabilities, dict):
            # One row per backend, in the order the carrier declared them.
            caps = [
                {"variant": label, "fields": sorted(fields)}
                for label, fields in c.capabilities.items()
            ]
        elif c.capabilities is None:
            caps = None
        else:
            caps = [{"variant": "", "fields": sorted(c.capabilities)}]
        rows.append(
            {
                "slug": _slug(c),
                "name": c.name,
                "repo": c.repo,
                "url": c.url,
                "icon": c.icon,
                "version": c.version,
                "early": c.early,
                "blurb": c.blurb,
                "region": c.region,
                "countries": c.countries,
                "directions": c.directions,
                "connections": [
                    {
                        "kind": conn.auth,
                        "label": AUTH_LABEL[conn.auth],
                        "variant": conn.variant or "",
                        # Same rule as _connect_line: the sub-line only earns
                        # its space when it says more than the pill above it,
                        # and "Tracking code" under a "Tracking code" pill
                        # says nothing twice.
                        "input": (
                            ""
                            if (conn.input or "").casefold()
                            == AUTH_LABEL[conn.auth].casefold()
                            else conn.input or ""
                        ),
                    }
                    for conn in c.connections
                ],
                "capabilities": caps,
            }
        )
    return json.dumps(
        {
            "carriers": rows,
            "countries": COUNTRY_NAMES,
            # The contract field travels with the label so the table header
            # can name it — a reader comparing carriers is usually about to
            # write a template against that exact key.
            "capabilityLabels": [
                [key, label, field.replace("`", "")]
                for key, (label, field) in CAPABILITY_LABELS.items()
            ],
        }
    )


def _searchable(carrier: Carrier) -> str:
    """Lower-cased haystack for the name box on the carriers page.

    Accents fold the same way _slug folds them, so typing "cesk" finds
    Ceska posta on a keyboard that has no way to produce the diacritic.
    """
    text = f"{carrier.name} {carrier.blurb}".lower()
    folded = unicodedata.normalize("NFKD", text)
    stripped = "".join(ch for ch in folded if not unicodedata.combining(ch))
    # Only the accented names need the second copy; most carriers have none.
    return text if stripped == text else f"{text} {stripped}"


def _card(carrier: Carrier) -> str:
    """One carrier card: logo first, then how you connect and where it runs.

    A <button>, not a link — it opens the detail dialog rather than
    navigating, and the element carries that for keyboard and screen-reader
    users without any ARIA of our own. The link out to the repo lives in the
    dialog, which is also where the carrier-click analytics event fires.
    """
    # Root-relative, not "assets/...": Material serves this page at
    # /carriers/, and MkDocs does not rewrite src attributes inside raw
    # HTML, so a relative path resolves to /carriers/assets/... and 404s.
    logo = (
        f'<img src="/assets/icons/{carrier.icon}" alt="" loading="lazy">'
        if carrier.icon
        else f'<span class="carrier-initial">{carrier.name[0]}</span>'
    )
    beta = '<span class="carrier-beta">Beta</span>' if carrier.early else ""
    parent = (
        f'<span class="carrier-parent">via {carrier.parent}</span>'
        if carrier.parent
        else ""
    )

    kinds = dict.fromkeys(conn.auth for conn in carrier.connections)
    pills = "".join(
        f'<span class="carrier-pill carrier-pill--{kind}">{AUTH_PILL[kind]}</span>'
        for kind in kinds
    )

    if not carrier.countries:
        where = '<span class="carrier-flags">🌍</span> Worldwide'
    elif len(carrier.countries) == 1:
        code = carrier.countries[0]
        where = f'<span class="carrier-flags">{_flag(code)}</span> {COUNTRY_NAMES[code]}'
    elif len(carrier.countries) <= FLAGS_SHOWN:
        flags = " ".join(_flag(code) for code in carrier.countries)
        where = f'<span class="carrier-flags">{flags}</span>'
    else:
        flags = " ".join(_flag(code) for code in carrier.countries[:FLAGS_SHOWN])
        rest = len(carrier.countries) - FLAGS_SHOWN
        where = (
            f'<span class="carrier-flags">{flags}</span> '
            f'<span class="carrier-more">+{rest} more</span>'
        )

    return (
        f'<button type="button" class="carrier-card" data-slug="{_slug(carrier)}" '
        f'data-kinds="{" ".join(kinds)}" '
        # Name and blurb both, so "bol.com" still finds Ampere the way site
        # search does. Folded here rather than in the browser so the filter
        # never has to touch the DOM to read a card's text.
        f'data-search="{html.escape(_searchable(carrier), quote=True)}" '
        f'data-countries="{" ".join(carrier.countries)}">'
        f'<span class="carrier-plate">{logo}{beta}</span>'
        f'<span class="carrier-name">{carrier.name}'
        f'<span class="carrier-version">{carrier.version}</span></span>'
        f"{parent}"
        f'<span class="carrier-kinds">{pills}</span>'
        f'<span class="carrier-where">{where}</span>'
        # Not decoration and not dead weight: this is the sentence site search
        # matches on ("bol.com" has to find Ampère), and the screen reader
        # reads it as part of the button's own label.
        f'<span class="carrier-blurb">{carrier.blurb}</span>'
        "</button>"
    )


# How many flags a card shows before it switches to "+N more". Four fits the
# narrowest card without wrapping onto a second line.
FLAGS_SHOWN = 4


def render_carriers(carriers: list[Carrier]) -> str:
    out = [CARRIERS_INTRO, ""]
    out.append('<div id="carriers-block">')
    out.append(
        '<div class="carriers-filter">'
        # Country first: it is the question almost every visitor arrives with.
        '<label class="carriers-filter__country" for="carrier-country-filter">'
        '<span class="carriers-filter__label">Delivering to</span>'
        '<select id="carrier-country-filter">'
        '<option value="">🌍 All countries</option>'
        f"{_country_filter_options(carriers)}"
        "</select>"
        "</label>"
        # Second, because it only helps a reader who already has a name in
        # mind — but with 60+ tiles that reader should not have to scan.
        '<label class="carriers-filter__search" for="carrier-search">'
        '<span class="carriers-filter__label">Carrier</span>'
        '<input type="search" id="carrier-search" autocomplete="off" '
        'placeholder="Search by name">'
        "</label>"
        # The pills carried their purpose in an aria-label only, so a sighted
        # reader met three unexplained words.
        '<div class="carriers-filter__kinds" role="group" '
        'aria-labelledby="carrier-kinds-label">'
        '<span class="carriers-filter__label" id="carrier-kinds-label">'
        "Connect with</span>"
        '<div class="carriers-filter__pills">'
        + "".join(
            f'<button type="button" class="carrier-chip carrier-chip--{kind}" '
            f'data-kind="{kind}" aria-pressed="false">{label}</button>'
            for kind, label in AUTH_PILL.items()
        )
        + "</div>"
        "</div>"
        "</div>"
    )
    out.append(
        f'<p class="carriers-count" id="carrier-count" role="status">'
        f"<strong>{len(carriers)} carriers</strong> and counting.</p>"
    )
    out.append(
        '<div class="carriers-grid" id="carriers-grid">'
        + "".join(_card(c) for c in carriers)
        + "</div>"
    )
    out.append(
        '<p class="carriers-empty" id="carriers-empty" hidden>'
        "No carrier matches that combination yet — "
        "clear the search or the connection filter, or "
        f'<a href="https://github.com/{ORG}/.github/discussions/new'
        '?category=carrier-requests">request the carrier</a>.</p>'
    )
    out.append(
        '<dl class="carriers-legend">'
        '<div><dt class="carrier-pill carrier-pill--account">Account</dt>'
        "<dd>You sign in with your own carrier account.</dd></div>"
        '<div><dt class="carrier-pill carrier-pill--trackingnr">Tracking</dt>'
        "<dd>A tracking code is enough — no account.</dd></div>"
        '<div><dt class="carrier-pill carrier-pill--apikey">API</dt>'
        "<dd>You bring your own official API credentials.</dd></div>"
        # The badge on a third of the tiles was the one mark on this page
        # with no key; CARRIERS_FOOTER explains it 60 tiles further down.
        '<div><dt class="carrier-beta">Beta</dt>'
        "<dd>Early release — its status mapping was inferred, not observed.</dd></div>"
        "</dl>"
    )
    # A <div>, not <script>: navigation.instant strips <script> tags from the
    # content it swaps in on SPA navigation, which silently dropped this data
    # (and broke the filter) on every navigation into the page that wasn't a
    # full reload.
    out.append(
        '<div id="carriers-data" hidden>' + _payload(carriers) + "</div>"
    )
    out.append("</div>")

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
# Pages: automation cookbook & dashboard cards
#
# Both are the same machinery over a different examples/ subfolder, so they
# share everything below except their own intro.
# --------------------------------------------------------------------------

AUTOMATIONS_INTRO = """\
---
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
    Open your dashboard, **:material-pencil: → + Add card → Manual**, and paste over the
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


@dataclass(frozen=True)
class Snippet:
    title: str
    # Every paragraph of the leading comment block, as prose.
    description: tuple[str, ...]
    # The YAML with that block removed — what the code block shows.
    body: str
    # The file exactly as it ships, which is what custom: cards are counted
    # from: a snippet may name its fallback plugin in a comment.
    source: str
    filename: str


def _describe(source: str) -> tuple[str, tuple[str, ...], str]:
    """Split the leading ``#`` block off as prose, and hand back the rest.

    That block and the description rendered above it said the same thing
    twice, so the reader met nine grey comment lines before the first line of
    YAML — ``alias:`` started below the fold of the code block. All of the
    block becomes prose now, not just its first paragraph, so nothing is lost
    by cutting it out of the snippet.
    """
    lines = source.strip().splitlines()
    paragraphs: list[list[str]] = [[]]
    cut = 0
    for line in lines:
        if line.startswith("#"):
            text = line.lstrip("#").strip()
            if text:
                paragraphs[-1].append(text)
            elif paragraphs[-1]:
                # A bare "#" is a paragraph break.
                paragraphs.append([])
        elif line.strip():
            break
        cut += 1
    match = TITLE_RE.search(source)
    title = match.group(1).strip().strip("\"'") if match else ""
    description = tuple(" ".join(p) for p in paragraphs if p)
    return title, description, "\n".join(lines[cut:]).strip()


def _snippets(folder: str) -> list[Snippet]:
    items = []
    for entry in sorted(gh_dir(AGGREGATOR, f"examples/{folder}"), key=lambda e: e["name"]):
        if not entry["name"].endswith((".yaml", ".yml")):
            continue
        raw = gh_file(AGGREGATOR, entry["path"])
        if raw is None:
            continue
        source = raw.decode("utf-8")
        title, description, body = _describe(source)
        fallback = entry["name"].rsplit(".", 1)[0].replace("_", " ").capitalize()
        items.append(
            Snippet(
                title=title or fallback,
                description=description,
                body=body,
                source=source.strip(),
                filename=entry["name"],
            )
        )
    return items


def _render_snippets(
    snippets: list[Snippet], folder: str, examples_url: str
) -> list[str]:
    """A heading, the prose, then the YAML behind a disclosure.

    The title used to live only in a ``???`` summary, which is not a heading —
    so the two longest pages on the site carried a table of contents with two
    entries between them, and no way to jump to a recipe. An ``h3`` per recipe
    gives the reader the index the page was missing, and the snippet itself
    stays folded because ten of them open at once is not a page anyone reads.
    """
    out: list[str] = []
    for snippet in snippets:
        out.append(f"### {snippet.title}\n")
        for paragraph in snippet.description:
            out.append(f"{paragraph}\n")
        out.append('??? example "Show the YAML"')
        out.append("    ```yaml")
        out.extend(
            f"    {line}" if line.strip() else "" for line in snippet.body.splitlines()
        )
        out.append("    ```\n")
        out.append(
            f"    [View on GitHub]({examples_url}/{folder}/{snippet.filename})\n"
        )
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
    _custom_cards([snippet.source for snippet in snippets])
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
# github.com/ha-parcel-integrations shows .github/profile/README.md.
# Keep the profile generic and direct visitors to the website for carrier
# coverage and documentation. scripts/sync_org.py publishes the rendered file.
# --------------------------------------------------------------------------

PROFILE = """\
<!-- Generated by ha-parcel-integrations.github.io/scripts/generate.py — do not edit by hand. -->

# Home Assistant parcel integrations

Track your parcels in [Home Assistant](https://www.home-assistant.io/), across carriers and countries. Bring delivery updates into your dashboards and automations, with a consistent way to follow every package.

📦 **[Find your carriers]({site_url}carriers/)** · **[Get started]({site_url}install/)** · **[Visit the website]({site_url})**

## How it works

Install the integrations for the carriers you use through HACS. Each works independently and provides parcel sensors and delivery events for your Home Assistant setup.

If you use several carriers, the optional **Parcel Aggregator** brings them together into combined sensors, a deliveries calendar, and shared events. Write an automation once and use it across your deliveries.

## Explore the documentation

The website is the central place for supported carriers, country coverage, and setup guidance:

- **[Carriers and coverage]({site_url}carriers/)** — find integrations available for your country.
- **[Getting started]({site_url}install/)** — install and configure your integrations.
- **[Automations]({site_url}automations/)** — get notified when a parcel is on its way or delivered.
- **[Dashboards]({site_url}dashboards/)** — bring your deliveries together in Home Assistant.
- **[Parcel contract]({site_url}contract/)** — explore the shared data and events for your own setup.

Missing a carrier or country? **[Request support]({site_url}carriers/#missing-your-carrier)**.

## Community

Questions or feedback? Join the [Home Assistant community discussion]({community_url}).
For bugs, find the integration through the **[carrier directory]({site_url}carriers/)** and open an issue in its repository.

## Support this project

These integrations are free and MIT-licensed. If you would like to help keep the project going, **[visit the support page]({site_url}sponsor/)** for sponsorship and other ways to contribute.
"""

SITE_URL = f"https://{ORG}.github.io/"
COMMUNITY_URL = (
    "https://community.home-assistant.io/t/"
    "packages-postnl-dhl-nl-dpd-and-gls-parcel-integration/112433/"
)


def render_profile() -> str:
    """Render the org introduction without a duplicate carrier directory."""
    return PROFILE.format(site_url=SITE_URL, community_url=COMMUNITY_URL)


# --------------------------------------------------------------------------


def main() -> int:
    try:
        carriers = collect_carriers()
        (DOCS / "carriers.md").write_text(render_carriers(carriers), encoding="utf-8")
        (DOCS / "automations.md").write_text(render_automations(), encoding="utf-8")
        (DOCS / "dashboards.md").write_text(render_dashboards(), encoding="utf-8")
        BUILD.mkdir(parents=True, exist_ok=True)
        (BUILD / "profile-README.md").write_text(render_profile(), encoding="utf-8")
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
    print("✓ docs/automations.md")
    print("✓ docs/dashboards.md")
    print("✓ build/profile-README.md   (pushed by scripts/sync_org.py)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
