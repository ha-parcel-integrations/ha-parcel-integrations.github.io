---
hide:
  - navigation
description: >-
  The shared contract behind every carrier: eight ParcelStatus values, one
  package shape, four events — so one automation covers every carrier.
---

# The parcel contract

Everything in this suite agrees on three things: **what a parcel looks like**,
**what statuses exist**, and **which events fire**. That agreement is the whole
point — it is what lets one automation cover every carrier you will ever install.

Write against this page rather than against any single carrier's raw data.

## ParcelStatus

Every parcel's `status` is one of exactly eight values. They are identical in
every integration, so `status: out_for_delivery` means the same thing whether it
came from PostNL or Sameday.

| Value | Meaning |
|---|---|
| `registered` | The carrier knows about the label, but the parcel is not moving yet |
| `in_transit` | Picked up; somewhere in the carrier's network |
| `out_for_delivery` | On the delivery vehicle today |
| `at_pickup_point` | Arrived at the chosen ServicePoint / Point / ParcelShop, ready to collect |
| `delivered` | Handed over — to you, your mailbox, a neighbour, or collected by you |
| `returning` | Delivery failed; on its way back to the sender |
| `problem` | The carrier reports an exception or needs intervention |
| `unknown` | The carrier sent something this integration has not mapped yet |

!!! warning "Trigger on `status`, not `raw_status`"
    The carrier's original string stays available on `raw_status` for when you
    need it, but it is carrier-specific, unstable, and often localised. Anything
    you build on it breaks the moment you add a second carrier.

### About `unknown`

`unknown` is not a bug you should work around — it is the integration telling you
it saw something new. When it happens the integration logs a **warning** with a
prefilled issue link. Please use it: a single report is usually enough to map the
status permanently, and it is the only way a pre-1.0 carrier reaches 1.0.

## The parcel shape

Every parcel — on a sensor's `parcels` attribute and inside every event payload —
has the same top-level keys.

| Key | Type | Meaning |
|---|---|---|
| `carrier` | string | Display name of the source carrier (`"PostNL"`, `"DHL"`, …) |
| `barcode` | string | Tracking number |
| `sender` | string \| null | Sender name, often the webshop |
| `receiver` | string \| null | Recipient name |
| `status` | `ParcelStatus` | Canonical status — see above |
| `raw_status` | string \| null | The carrier's own status string |
| `delivered` | bool | Whether it has been delivered |
| `delivered_at` | ISO 8601 \| null | When, if known |
| `planned_from` | ISO 8601 \| null | Start of the expected delivery window |
| `planned_to` | ISO 8601 \| null | End of the expected delivery window |
| `pickup` | bool | Headed for a pickup point rather than your address |
| `pickup_point` | string \| null | Which one, when `pickup` is true |
| `url` | string \| null | Deep link to the carrier's tracking page |
| `weight` | float \| null | Kilograms, when the carrier exposes it |
| `dimensions` | dict \| null | `{length, width, height, text}` in centimetres; `text` is a ready-made `"L x W x H cm"` |
| `history` | list \| null | Status timeline, oldest → newest, each `{timestamp, status, raw_status}` |

A few notes that save debugging time:

- **`null` is normal.** Carriers expose wildly different amounts of detail.
  Guard your templates (`{{ parcel.weight or '—' }}`) rather than assuming a
  field is populated.
- **`history` is opt-in.** It stays `null` unless you enable *Parcel history* in
  that carrier's options — it is off by default because it grows the attribute
  payload considerably.
- **`raw` exists on carrier events only.** The carrier's untouched payload is
  available on its own events; the aggregator strips it to keep the unified
  events small.
- **`planned_from`/`planned_to` are as precise as the carrier is.** Some give an
  all-day window until an hour before delivery, then narrow it. Build "today /
  tomorrow" logic on them rather than exact hours.

## Events

Each carrier fires four events, prefixed with its own domain. If you also run the
optional aggregator, it subscribes to all of them and re-emits them under
`parcel_aggregator_`.

| Event | Fires when | Extra payload |
|---|---|---|
| `…_parcel_registered` | A new parcel appears | — |
| `…_parcel_status_changed` | `status` changes — *except* the final hop to delivered | `old_status`, `new_status` |
| `…_parcel_delivered` | The parcel is delivered | — |
| `…_parcel_delivery_time_changed` | The expected delivery window moves | `old_planned_from`, `new_planned_from`, `old_planned_to`, `new_planned_to` |

Carriers that support outgoing parcels also fire
`…_outgoing_parcel_status_changed` and `…_outgoing_parcel_delivered`.

Every payload is the full parcel dict from the section above, plus the extra keys
in the table, plus the account's `device_id`.

!!! danger "Delivery fires once, on one event"
    The transition **into** `delivered` fires only `_parcel_delivered` — it does
    *not* also fire `_parcel_status_changed`. Listening to both and expecting two
    notifications gets you one; listening to both and expecting one gets you two
    for every *other* transition. Pick the event that matches the moment you care
    about.

### Which prefix to use

=== "One carrier"

    ```yaml
    triggers:
      - trigger: event
        event_type: postnl_parcel_delivered
    ```

    Always available — no aggregator needed. Use the carrier's HA domain
    (`postnl`, `dhl_nl`, `swiss_post`, …). This is also the only way to reach the
    `raw` carrier payload, and the right choice when one carrier should behave
    differently from the rest.

=== "Every carrier at once"

    ```yaml
    triggers:
      - trigger: event
        event_type: parcel_aggregator_parcel_delivered
    ```

    Needs the [aggregator](install.md#2-optional-add-the-aggregator). Covers every
    carrier you have installed, and every carrier you install later, with no edit.
    Worth it from your second carrier onward.

## Sensors

Each carrier exposes its own count sensors, and the aggregator sums them. In both
cases the parcel list lives on the `parcels` attribute in exactly the shape
described above — so a template that walks one carrier's sensor walks the
aggregator's just as well.

```jinja
{% set parcels = state_attr('sensor.parcel_aggregator_incoming_parcels', 'parcels') %}
{{ parcels | selectattr('status', 'eq', 'out_for_delivery') | list | count }}
```

## Stability

These names are a contract, not an implementation detail. Status values, parcel
keys and event names change only in a major release, and a change is applied to
every carrier and to the aggregator in the same wave — never to one integration
on its own.
