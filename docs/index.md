---
hide:
  - navigation
---

# Track every parcel in Home Assistant

A suite of [Home Assistant](https://www.home-assistant.io/) custom integrations
that follow your parcels across carriers and countries — every one of them
speaking the **same canonical parcel contract**, so your automations and
dashboards work the same no matter who delivers.

[Browse the carriers :material-arrow-right:](carriers.md){ .md-button .md-button--primary }
[Get started](install.md){ .md-button }

---

## Write the automation once

Without a shared contract, "tell me when a parcel is out for delivery" is one
automation per carrier, each keyed to that carrier's own status strings. Here it
is one automation, for all of them, forever:

```yaml
triggers:
  - trigger: event
    event_type: parcel_aggregator_parcel_status_changed
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

Install a new carrier next year and this keeps working — untouched.

## How the pieces fit

<div class="grid cards" markdown>

-   :material-truck-delivery: **Carrier integrations**

    ---

    One per carrier. Each talks to its own API and normalises the result into
    the shared parcel shape and the shared `ParcelStatus` values.

    [:octicons-arrow-right-24: See all carriers](carriers.md)

-   :material-set-merge: **Parcel Aggregator**

    ---

    Reads what the carriers publish and re-emits it merged: summed sensors, one
    `next_delivery`, one unified event stream. Talks to no API itself.

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

    [:octicons-arrow-right-24: Open the cookbook](automations.md)

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
