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

[Browse the carriers :material-arrow-right:](carriers.md){ .md-button .md-button--primary }
[Get started](install.md){ .md-button }

---

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

## Missing your carrier?

That is the most useful thing you can tell us.
[Open a carrier request](https://github.com/ha-parcel-integrations/.github/discussions/new?category=carrier-requests)
— writing the code is rarely the blocker, getting real tracking data to confirm
the status vocabulary is. A request from someone who actually receives those
parcels is worth a great deal.

## Support the project

Every integration here is free and MIT-licensed, and stays that way. Sponsoring
covers what keeping the suite running actually costs — and if that is not for
you, [the ways to help that cost nothing](sponsor.md) are worth as much.

[:simple-githubsponsors: Sponsor on GitHub](https://github.com/sponsors/peternijssen){ .md-button .md-button--primary }
[:simple-buymeacoffee: Buy me a coffee](https://www.buymeacoffee.com/peternijssen){ .md-button }

!!! info "Independent project"
    Community-built, MIT-licensed, with no affiliation with or endorsement by
    any parcel carrier. See the [disclaimer](disclaimer.md).
