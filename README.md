# ha-parcel-integrations.github.io

The org site: <https://ha-parcel-integrations.github.io/>

It documents what no single carrier repo can — the shared parcel contract, the
automation cookbook, and the coverage matrix across every carrier. Per-carrier
installation and options stay in each repo's own README; this site links there
rather than copying it.

## The rule

**The carrier list is generated, never written.**

`scripts/generate.py` reads the GitHub API on every deploy and produces:

| Generated file | Built from |
|---|---|
| `docs/carriers.md` | Every `ha-*` repo in the org: manifest, release, icon |
| `docs/automations.md` | `ha-parcel-aggregator/examples/automations/**` |
| `docs/dashboards.md` | `ha-parcel-aggregator/examples/dashboards/**` |
| `docs/assets/icons/*.png` | Each carrier's `custom_components/<domain>/brand/icon.png` |
| `build/profile-README.md` | A general project introduction with links to the website |

All of them are gitignored. A committed copy is worse than none, because the
suite gains carriers faster than anyone remembers to update a table.

Repos are included when they are **public and have a published release**.
Private repos and repos that have never shipped are skipped automatically — you
can develop a new carrier in the open without touching this repo.

## What this repo writes elsewhere

`scripts/sync_org.py` runs after a successful build and pushes two things out:

| Target | What |
|---|---|
| `.github` → `profile/README.md` | A general project introduction directing visitors to the website |
| Every carrier repo's `homepage` | Set to the docs site, so the About box links here |

Both need a PAT in the `PROFILE_TOKEN` secret (`contents:write` on `.github`,
`administration:write` on the org). Without it the step prints a notice and the
site still deploys — it never blocks a release.

The one hand-maintained input is [`data/carriers.yml`](data/carriers.yml) —
coverage, how you authenticate, one-line blurb. Nothing else belongs there.

**If the org has a carrier repo that `data/carriers.yml` does not list, the build
fails.** That is the tripwire that keeps this site honest; do not soften it.

The same applies to community Lovelace cards: an example dashboard that uses a
`custom:` card missing from `CUSTOM_CARDS` in `scripts/generate.py` fails the
build, so no snippet can quietly depend on a HACS plugin the page never names
or credits.

## Local preview

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) .venv/bin/python scripts/generate.py
.venv/bin/mkdocs serve
```

`GITHUB_TOKEN` is optional but the unauthenticated rate limit (60/h) does not
cover a full run.

## Carrier click analytics

Umami records clicks on carrier names and release badges in the carrier table,
and on carrier links in the capability comparison. Each click sends one custom
event named `carrier-click:<repo>`, for example `carrier-click:ha-postnl`.
Aliases pointing to the same integration share a counter. In Umami, select the
website and date range, then view Events to compare the counts per integration.
These are clicks, not completed installations, and collection starts after deploy.

This uses standard custom events supported by the free Hobby plan, without
extra event properties. Clicks count towards the plan's quota along with
pageviews; blocked analytics will not be counted. See the
[Umami Cloud usage FAQ](https://docs.umami.is/docs/cloud/faq).

## Deploys

- every push to `main`
- nightly at 04:00 UTC, so a release published by hand shows up
- `repository_dispatch` with type `carrier-released`, for immediate publication:

  ```sh
  gh api repos/ha-parcel-integrations/ha-parcel-integrations.github.io/dispatches \
    -f event_type=carrier-released
  ```

## Adding a carrier

1. Add the repo to [`data/carriers.yml`](data/carriers.yml)
2. Push

The table row, the icon, the version badge and the early-release flag all follow
from the repo itself.
