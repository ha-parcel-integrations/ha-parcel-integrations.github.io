---
hide:
  - navigation
description: >-
  Package tracking in Home Assistant for every carrier — PostNL, DHL, DPD, GLS,
  PostNord, Hermes, Packeta and more. Track parcels and packages with one set of
  sensors, events and automations.
---

# Package tracking in Home Assistant

A suite of [Home Assistant](https://www.home-assistant.io/) custom integrations
that track your packages across carriers and countries — every one of them
speaking the **same canonical parcel contract**, so your automations and
dashboards work the same no matter who delivers.

*Parcel* and *package* mean the same thing here; the integrations use "parcel"
throughout because that is what most European carriers call it.

[Browse the carriers :material-arrow-right:](carriers.md){ .md-button .md-button--primary }
[Get started](install.md){ .md-button }

---

## Pick one carrier, or all of them

Every integration stands on its own. Install the one carrier that delivers to
you, and you get its sensors, its events and its parcel data — nothing else
required.

```yaml
triggers:
  - trigger: event
    event_type: postnl_parcel_status_changed
    event_data:
      new_status: out_for_delivery
```

Use several carriers, and the shared contract starts paying off: the optional
**Parcel Aggregator** merges them into one event stream, so the same automation
covers every carrier at once — including the one you install next year.

```yaml
triggers:
  - trigger: event
    event_type: parcel_aggregator_parcel_status_changed  # (1)!
    event_data:
      new_status: out_for_delivery

actions:
  - action: notify.mobile_app
    data:
      title: "📦 On its way"
      message: >-
        {{ trigger.event.data.carrier }} is delivering
        {{ trigger.event.data.sender or 'your parcel' }} today.
```

1.  The only line that differs from the single-carrier version above. The event
    payload is identical either way.

## How the pieces fit

<div class="grid cards" markdown>

-   :material-truck-delivery: **Carrier integrations**

    ---

    One per carrier, each fully standalone. Talks to its own API and normalises
    the result into the shared parcel shape and `ParcelStatus` values.

    [:octicons-arrow-right-24: See all carriers](carriers.md)

-   :material-set-merge: **Parcel Aggregator** *(optional)*

    ---

    Only if you run several carriers. Reads what they already publish and
    re-emits it merged: summed sensors, one `next_delivery`, one event stream.

    [:octicons-arrow-right-24: On GitHub](https://github.com/ha-parcel-integrations/ha-parcel-aggregator)

-   :material-file-document-outline: **The contract**

    ---

    Eight status values, one parcel shape, four events. The thing that makes a
    carrier-agnostic automation possible at all.

    [:octicons-arrow-right-24: Read the contract](contract.md)

-   :material-lightbulb-on: **Cookbook**

    ---

    Ready-to-paste automations and dashboard cards, generated from the examples
    that ship with the aggregator.

    [:octicons-arrow-right-24: Automations](automations.md)
    · [:octicons-arrow-right-24: Dashboard cards](dashboards.md)

</div>

## No account, in most cases

Most carriers here need nothing but a tracking number — no login, no API key, no
developer portal. You add the number the way you would on the carrier's own
tracking page, and Home Assistant takes it from there. Where a carrier does offer
an account (PostNL, DHL, DPD, Vinted Go), logging in gets you every parcel
automatically, including the ones you send.

## Missing your carrier?

That is the most useful thing you can tell us.
[Open a carrier request](https://github.com/ha-parcel-integrations/.github/discussions/new?category=carrier-requests)
— writing the code is rarely the blocker, getting real tracking data to confirm
the status vocabulary is. A request from someone who actually receives those
parcels is worth a great deal.

!!! info "Independent project"
    Community-built, MIT-licensed, with no affiliation with or endorsement by
    any parcel carrier.
