# Getting started

## What you need

- Home Assistant **2024.7** or newer
- [HACS](https://hacs.xyz/) installed

Every integration in this suite is distributed through HACS as a custom
repository.

## 1. Add the carriers you use

Repeat this for each carrier that delivers to you — [the full list is
here](carriers.md).

1. Open **HACS → Integrations → ⋮ → Custom repositories**
2. Paste the repository URL (for example
   `https://github.com/ha-parcel-integrations/ha-postnl`) and pick category
   **Integration**
3. Search for the carrier and install it
4. Restart Home Assistant
5. Go to **Settings → Devices & Services → Add Integration** and search for the
   carrier

What step 5 asks you for depends on the carrier: a tracking number, a tracking
number plus postal code, or an account login. The **Connect with** column on the
[carriers page](carriers.md) tells you which before you start.

## 2. Add the aggregator

Do this once, after at least one carrier is set up.

1. Add `https://github.com/ha-parcel-integrations/ha-parcel-aggregator` as a
   custom repository, category **Integration**
2. Install it, restart, then add it under **Settings → Devices & Services**
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
| `sensor.parcel_aggregator_awaiting_pickup` | Parcels headed for a pickup point |
| `sensor.parcel_aggregator_next_delivery` | Earliest expected delivery, with the parcel on `parcel` |

Each one carries the merged parcel list on its `parcels` attribute and a
per-carrier breakdown on `by_carrier`.

Plus a calendar, `calendar.parcel_aggregator_deliveries`, holding every expected
delivery from every carrier in one agenda. It is read-only, does no polling of
its own, and is enabled by default — drop it on a dashboard, or disable the
entity if you would rather not see it.

## 3. Build something

Head to the [cookbook](automations.md) for automations and dashboard cards you
can paste as-is, or read the [parcel contract](contract.md) first if you would
rather write your own.

## Polling and rate limits

Each carrier integration polls on an interval you can change in its **Configure**
dialog. The defaults are chosen to be polite to the carrier's API — turning them
way down mostly gets you rate-limited, not faster updates. Delivery-day
precision comes from the carrier's own data, not from how often you ask.

## When something looks wrong

- **A parcel shows `unknown`** — the carrier returned a status the integration
  has not mapped yet. It logs a warning containing a ready-made report link;
  opening that issue is what gets it mapped.
- **An integration is marked "Early release"** — it works, but its status
  vocabulary was inferred rather than confirmed against real shipments. Your
  reports are what move it to 1.0.
- **Nothing appears at all** — check **Settings → System → Logs**, then open an
  issue on that carrier's own repository with the diagnostics download from its
  device page.
