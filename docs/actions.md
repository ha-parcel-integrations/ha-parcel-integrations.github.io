---
description: >-
  The actions every carrier integration offers: track_parcel, untrack_parcel and
  update_contents, and how they behave with several accounts.
---

# Actions

Every carrier integration registers its actions under its own domain, so the
action is `<domain>.update_contents` (`postnl.update_contents`,
`gls.update_contents`, …). The aggregator has no actions: it reads what carriers
publish and never writes to them.

## `update_contents`

Sets the [`contents`](contract.md#parcel-contents) text of a parcel. Every carrier
integration has it, account-based carriers included, and it works for a code that
is not tracked yet.

| Field | Required | Meaning |
|---|---|---|
| `tracking_code` | yes | The parcel's tracking code |
| `contents` | no | The text, up to 120 characters. Empty or absent clears it |
| `config_entry_id` | no | Which account to store it in; see below |

```yaml
action: postnl.update_contents
data:
  tracking_code: "ABC123456789"
  contents: "Running shoes; socks"
```

### Several accounts

With more than one account of the same carrier, the text is stored in **every**
account that holds the code. If no account holds it, the action asks for
`config_entry_id` instead. Pass it to choose the account yourself.

### Where the text lives

The text is stored on your own Home Assistant, in one storage file per account
entry. Each keeps at most 200 codes; when it is full the oldest is dropped.
Diagnostics redact it. Changing the contents alone fires no event, so it never
triggers a status automation by accident.

## `track_parcel`

Carriers that track single codes (see the **Tracking** badge on the
[carriers page](carriers.md)) offer `<domain>.track_parcel`. It takes the same
optional `contents` field. Calling it again for a tracked code replaces the text,
and an empty text clears it.

```yaml
action: postnord.track_parcel
data:
  tracking_code: "ABC123456789"
  contents: "Birthday present"
```

`<domain>.untrack_parcel` stops tracking a code.

!!! note "No contents field in the add-parcel screen yet"
    The add-parcel screen in the Home Assistant UI has no contents field. Set the
    text with the actions above, a script or an automation; see
    [Label your parcels](contents.md).
