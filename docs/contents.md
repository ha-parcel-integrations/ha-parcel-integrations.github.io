---
description: >-
  Give your parcels a note with update_contents: a dashboard button and an
  automation that fills it from an order confirmation.
---

# Label your parcels

A tracking code says little about what is in the box. The
[`contents`](contract.md#parcel-contents) field holds a short note you write
yourself, and it shows up in every sensor attribute and event. The action is
described on the [Actions](actions.md#update_contents) page.

## A button that sets the contents

Two helpers and a script, like the add-parcel card on the
[dashboard page](dashboards.md). Put the helpers in `configuration.yaml` (or
Settings → Devices & services → Helpers), the script in `scripts.yaml`, and the
card on a dashboard.

```yaml
input_text:
  parcel_code:
    name: Tracking code
  parcel_contents:
    name: What is in it
    max: 120

script:
  parcel_set_contents:
    alias: Parcel, set contents
    sequence:
      - action: postnl.update_contents  # (1)!
        data:
          tracking_code: "{{ states('input_text.parcel_code') }}"
          contents: "{{ states('input_text.parcel_contents') }}"
```

1.  Use your own carrier's domain. An empty `parcel_contents` clears the text.

```yaml
type: entities
entities:
  - input_text.parcel_code
  - input_text.parcel_contents
  - type: button
    name: Save contents
    tap_action:
      action: call-service
      service: script.parcel_set_contents
```

## Set contents after an order confirmation

When a shop's confirmation mail names the order, you can label the parcel before
it ships. This automation reacts to an event your own mail setup fires (see
[Track from e-mail](email.md)) and stores the text for the code, which does not
have to be tracked yet.

```yaml
alias: Parcel, label new order
triggers:
  - trigger: event
    event_type: order_confirmed  # (1)!
actions:
  - action: postnl.update_contents
    data:
      tracking_code: "{{ trigger.event.data.tracking_code }}"
      contents: "{{ trigger.event.data.items | join('; ') }}"  # (2)!
mode: queued
```

1.  An event of your own, for instance fired from an IMAP template. Invented
    here: the data is `{"tracking_code": "ABC123456789", "items": ["Desk lamp", "Bulbs"]}`.
2.  Joined as `A; B`, the same way carriers join several items. Keep the
    result within 120 characters.

With several accounts of one carrier the text lands in every account that holds
the code; add `config_entry_id` to pick one.
