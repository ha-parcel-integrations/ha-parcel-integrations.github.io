---
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
| `at_pickup_point` | Arrived at a pickup point (ServicePoint / Point / ParcelShop / locker), ready to collect — also when a failed home delivery was taken there |
| `delivered` | Handed over — to you, your mailbox, a neighbour, or collected by you |
| `returning` | Delivery failed; on its way back to the sender, or already back there |
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
| `barcode` | string | Tracking code |
| `sender` | string \| null | Sender name, often the webshop |
| `receiver` | string \| null | Recipient name |
| `status` | `ParcelStatus` | Canonical status — see above |
| `raw_status` | string \| null | The carrier's own status string |
| `delivered` | bool | Whether the journey is over: delivered, or a parcel sent back to its sender that is back there. A return you send yourself counts as delivered once it reaches the shop |
| `delivered_at` | ISO 8601 \| null | When, if known. For a pickup-point parcel: when you collected it |
| `planned_from` | ISO 8601 \| null | Start of the expected arrival window — at your address, or at the pickup point |
| `planned_to` | ISO 8601 \| null | End of that window |
| `pickup` | bool | The parcel goes to a pickup point rather than your address. Stays `true` after you collected it |
| `pickup_point` | string \| null | The pickup point's name, when `pickup` is true |
| `url` | string \| null | Deep link to the carrier's tracking page |
| `weight` | float \| null | Kilograms, when the carrier exposes it |
| `dimensions` | dict \| null | `{length, width, height, text}` in centimetres; `text` is a ready-made `"L x W x H cm"` |
| `history` | list \| null | Status timeline, oldest → newest, each `{timestamp, status, raw_status}` |
| `raw` | dict | The carrier's own record, untouched — carrier events and sensors only |

A few notes that save debugging time:

- **`null` is normal.** Carriers expose wildly different amounts of detail.
  Guard your templates (`{{ parcel.weight or '—' }}`) rather than assuming a
  field is populated. Select a carrier on the [carriers page](carriers.md) to
  see exactly which fields it populates.
- **`history` is opt-in.** It stays `null` unless you enable *Parcel history* in
  that carrier's options — it is off by default because it grows the attribute
  payload considerably. With the option on, a parcel without events has `[]`.
- **`raw` is dropped by the aggregator.** The carrier's untouched payload is
  available on its own events and sensors; the aggregator strips it to keep the
  unified events small.
- **`planned_from`/`planned_to` are as precise as the carrier is.** A real
  window keeps its hours. A carrier that gives only a date becomes
  `00:00`–`23:59:59` that day, and one that gives a single time runs from that
  time to `23:59:59`. Build "today / tomorrow" logic on them rather than exact
  hours.
- **The delivery window empties when it no longer applies**: once the parcel
  is at the pickup point, returning, or delivered, both fields are `null`.

## Events

Each carrier fires four events, prefixed with its own domain. If you also run the
optional aggregator, it subscribes to all of them and re-emits them under
`parcel_aggregator_`.

| Event | Fires when | Extra payload |
|---|---|---|
| `…_parcel_registered` | A new parcel appears | — |
| `…_parcel_status_changed` | `status` changes — *except* the final hop to delivered | `old_status`, `new_status` |
| `…_parcel_delivered` | The parcel is delivered (not when a return reaches the sender) | — |
| `…_parcel_delivery_time_changed` | The expected delivery window moves to a new time (not when it empties) | `old_planned_from`, `new_planned_from`, `old_planned_to`, `new_planned_to` |

Carriers that support outgoing parcels also fire
`…_outgoing_parcel_status_changed` and `…_outgoing_parcel_delivered`.

Every payload is the full parcel dict from the section above, plus the extra keys
in the table, plus the account's `device_id`.

!!! warning "Delivery fires once, on one event"
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

Which parcel is in which sensor:

| Sensor | Holds |
|---|---|
| Incoming parcels | Every parcel on its way to you that is not delivered yet, whatever its status |
| Delivered parcels | Delivered parcels, and returns back at the sender, trimmed by the retention option |
| Awaiting pickup | Parcels with status `at_pickup_point` |
| En route to pickup point | Parcels going to a pickup point that have not arrived there yet, and are not returning |
| Next delivery | The earliest `planned_from` among parcels whose window has not ended yet |
| Deliveries calendar | One event per parcel with a delivery window; a whole-day window shows as an all-day event |

Incoming parcels always holds everything in awaiting pickup and en route to
pickup point. Those two never overlap, and a delivered parcel is in neither.
A carrier that can deliver to pickup points or lockers offers both pickup sensors
from the start; they read 0 until a parcel shows the status or pickup flag.

## Stability

These names are a contract, not an implementation detail. Status values, parcel
keys and event names change only in a major release, and a change is applied to
every carrier and to the aggregator in the same wave — never to one integration
on its own.
