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
| `docs/carriers.md` | Every `ha-*` repo in the org: manifest, version, icon |
| `docs/automations.md` | `ha-parcel-aggregator/examples/**` |
| `docs/assets/icons/*.png` | Each carrier's `custom_components/<domain>/brand/icon.png` |

All three are gitignored. A committed copy is worse than none, because the suite
gains carriers faster than anyone remembers to update a table.

The one hand-maintained input is [`data/carriers.yml`](data/carriers.yml) —
coverage, how you authenticate, one-line blurb. Nothing else belongs there.

**If the org has a carrier repo that `data/carriers.yml` does not list, the build
fails.** That is the tripwire that keeps this site honest; do not soften it.

## Local preview

```sh
python -m venv .venv && .venv/bin/pip install -r requirements.txt
GITHUB_TOKEN=$(gh auth token) .venv/bin/python scripts/generate.py
.venv/bin/mkdocs serve
```

`GITHUB_TOKEN` is optional but the unauthenticated rate limit (60/h) does not
cover a full run.

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
