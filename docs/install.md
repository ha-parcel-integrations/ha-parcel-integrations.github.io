---
description: >-
  Install package tracking in Home Assistant via HACS — add the carriers that
  deliver to you, then optionally merge them with the Parcel Aggregator.
---

# Getting started

## What you need

- Home Assistant **2025.12** or newer
- [HACS](https://hacs.xyz/) installed

Every integration in this suite installs through HACS. Many are already in the
HACS default list; the rest are added once as a custom repository.

## 1. Add the carriers you use

Start by finding the carriers that deliver to you:

[Find your carriers :material-arrow-right:](carriers.md){ .md-button .md-button--primary }

Then repeat this for each one:

1. **Get it into HACS.** Select the carrier on the [carriers page](carriers.md):
    - With an **Open in HACS** button, it is in the HACS default list — click
      it, or just search for the carrier's name in HACS.
    - Without one, open **HACS → ⋮ → Custom repositories**, paste the
      repository URL from its **View on GitHub** button (for example
      `https://github.com/ha-parcel-integrations/ha-postnl`) and pick type
      **Integration**. After that it shows up in the HACS search too.
2. **Download** it from HACS
3. **Restart** Home Assistant
4. Go to **Settings → Devices & Services → Add Integration** and search for the
   carrier

What step 4 asks you for depends on the carrier: a tracking code, a tracking
code plus postal code, or an account login. Every tile on the [carriers
page](carriers.md) carries that as a badge — **Account**, **Tracking** or
**API** — and selecting a carrier spells out exactly what it asks for.

At this point you are done. Each carrier integration is fully standalone: it
gives you its own sensors, its own events and its own device page, and it needs
nothing else installed to work.

## 2. Optional: add the aggregator

Only worth it if you use **more than one carrier** and would rather write one
automation than one per carrier. It is not a dependency of anything — skip it
and every carrier keeps working exactly as it does now.

Do this once, after at least one carrier is set up.

1. It is in the HACS default list: search HACS for **Parcel Aggregator**, or
   [open it in HACS](https://my.home-assistant.io/redirect/hacs_repository/?owner=ha-parcel-integrations&repository=ha-parcel-aggregator&category=integration)
   directly
2. Download it, restart, then add it under **Settings → Devices & Services**
3. There is nothing to configure — no credentials, no options

It discovers your carrier sensors on its own, and keeps watching the entity
registry, so a carrier you install next month is picked up without a reload.

You get:

| Entity | What it holds |
|---|---|
| `sensor.parcel_aggregator_incoming_parcels` | Active incoming parcels across all carriers |
| `sensor.parcel_aggregator_outgoing_parcels` | Active outgoing parcels |
| `sensor.parcel_aggregator_delivered_parcels` | Recently delivered incoming parcels |
| `sensor.parcel_aggregator_outgoing_delivered_parcels` | Recently delivered outgoing parcels |
| `sensor.parcel_aggregator_en_route_to_pickup_point` | Parcels on their way to a pickup point |
| `sensor.parcel_aggregator_awaiting_pickup` | Parcels ready to collect at a pickup point |
| `sensor.parcel_aggregator_next_delivery` | Earliest expected delivery, with the parcel on `parcel` |

Each one carries the merged parcel list on its `parcels` attribute and a
per-carrier breakdown on `by_carrier`.

Plus a calendar, `calendar.parcel_aggregator_deliveries`, holding every expected
delivery from every carrier in one agenda. It is read-only, does no polling of
its own, and is enabled by default — drop it on a dashboard, or disable the
entity if you would rather not see it.

## 3. Build something

Head to the [automation cookbook](automations.md) for notifications and
summaries, or [dashboard cards](dashboards.md) to put your parcels on screen —
both are paste-as-is. Read the [parcel contract](contract.md) first if you would
rather write your own.

Those snippets use the aggregator's unified events and sensors. Without
it, the same recipes work per carrier — swap `parcel_aggregator_` for the
carrier's own domain (`postnl_`, `dhl_nl_`, …) and its own sensors. The parcel
data inside is identical either way, which is the point of the
[contract](contract.md).

## If something looks off

Statuses that come back as `unknown`, an integration marked "Early release", or
nothing showing up at all — [troubleshooting](troubleshooting.md) covers those,
along with how often each carrier polls.
