---
description: >-
  Build a Home Assistant parcel integration for a carrier that is not in the
  suite yet, starting from the carrier template, and get it into the family.
---

# Build your own carrier

Missing a carrier and comfortable with Python? You can build it yourself. Every
carrier here starts from the same
[carrier template](https://github.com/ha-parcel-integrations/ha-carrier-template),
so you only write the part that is about your carrier. Config flow, sensors,
events, polling, diagnostics, translations, tests and CI come with it.

The template is a working, fully tested integration for a made-up carrier. A
script stamps out a new repo from it with your carrier's name and leaves a
handful of places marked `TODO(carrier)` for you to fill in.

!!! tip "Say you are on it first"
    Before you write any code, open a
    [carrier request](https://github.com/ha-parcel-integrations/.github/discussions/new?category=carrier-requests)
    (or reply to the one already there) and say you are building it. That way two
    people don't build the same carrier, and we can tell you early if the carrier
    already has a known problem.

## 1. Generate the repo

You need Python 3.13 or newer and a clone of the template:

```sh
git clone https://github.com/ha-parcel-integrations/ha-carrier-template
cd ha-carrier-template
python scripts/bootstrap.py \
  --name "Example Post" \
  --domain example_post \
  --slug ha-example-post \
  --auth none \
  --out ../ha-example-post
```

Pick `--auth` by how people track their parcels with this carrier:

| `--auth` | When |
|---|---|
| `none` | The user enters a tracking code. No account needed. |
| `credentials` | The carrier has a customer account that lists your parcels. The integration logs in and finds them automatically. |
| `byo-key` | The only reliable route is the carrier's official API, and any consumer can sign up for their own key. |

The [template README](https://github.com/ha-parcel-integrations/ha-carrier-template#readme)
explains every flag.

## 2. Fill in the carrier

`grep -rn "TODO(carrier)"` in the new repo lists what is still placeholder. These
are the important ones:

| File | What goes in |
|---|---|
| `api.py` | The request to the carrier and the shape of its response |
| `parcels.py` | The status map and how a carrier record becomes a [parcel](contract.md) |
| `const.py` | Endpoints, and which optional parcel fields this carrier fills in |
| `config_flow.py` | The login or API-key fields (`credentials` and `byo-key` only) |
| `diagnostics.py` | The carrier's field names that hold personal data, for redaction |
| `tests/payloads.py` | Real responses from real parcels, with personal data removed |

Replace the placeholder `brand/icon.png` too, and write the carrier section in
the README.

## 3. Test it

```sh
cd ../ha-example-post
pip install -r requirements-dev.txt
python -m pytest tests/ --cov=custom_components.example_post
```

Keep coverage above 95%. Then copy or symlink
`custom_components/example_post` into your Home Assistant's `custom_components`
folder, restart, and track a parcel you actually have on the way.

## What makes a carrier good enough

- **It speaks the [parcel contract](contract.md).** Every carrier status maps to
  one of the eight `ParcelStatus` values. A status you have not seen yet becomes
  `unknown`, and the integration logs a warning with a link to report it.
- **The status map comes from real parcels.** Guessing from a website's wording
  is a starting point, not a mapping. Follow at least one parcel from start to
  delivery, and save the responses (with personal data removed) as test payloads.
- **It uses the carrier's own tracking data.** That is usually the JSON behind
  its tracking page or app. Scraping HTML pages is only accepted as an
  exception. A key you can only get as a registered business is not something
  users can bring.
- **It follows the
  [engineering principles](https://github.com/ha-parcel-integrations/.github/blob/main/CONVENTIONS.md#engineering-principles-integrations).**
  They are the mistakes Home Assistant and HACS reviews keep finding. The rest
  of that file shows how the other carriers handle commits, releases and tests.

## Getting it into the family

A carrier joins the suite by moving its repo into the
[ha-parcel-integrations](https://github.com/ha-parcel-integrations) org. That is
what puts it on this site, lets the
[Parcel Aggregator](https://github.com/ha-parcel-integrations/ha-parcel-aggregator)
recognise it, and gives it the same CI and release automation as every other
carrier.

1. **Publish it in a public repo on your own account.** The tests should pass.
   The generated README and issue links already point at the org, so they start
   working after the move.
2. **Confirm it on a real parcel.** At least one parcel tracked end to end, with
   its responses (personal data removed) in `tests/payloads.py`.
3. **Tell us in your carrier request.** Link the repo and say which country you
   tested in, which statuses you saw on real parcels, and what is still unknown.
4. **Review.** We check it against the contract and the conventions. Expect a
   round of changes; almost every carrier gets one.
5. **Move the repo.** Once it is ready, we arrange moving the repo into the org
   with you. After that it works like every other carrier here: changes go in
   through pull requests, which we review and merge, and you are credited in
   the release notes.

After the move we do the rest: the first release, the listing on the
[carriers page](carriers.md), recognition in the aggregator, and submitting it
to the HACS default list.
