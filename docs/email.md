---
hide:
  - navigation
description: >-
  Let Home Assistant read the shipping confirmations in your mailbox over IMAP
  and start tracking each parcel automatically — no tracking number typed by
  hand.
---

# Tracking numbers straight from your e-mail

Every shop mails you the tracking number the moment your order ships, and typing
it over is the last manual step left in this suite. Home Assistant's built-in
**IMAP** integration can do it for you.

> Shipping mail arrives :material-arrow-right: `imap_content` fires
> :material-arrow-right: your automation lifts the number out
> :material-arrow-right: `carrier.track_parcel`.

!!! info "Only for tracking-number carriers"
    PostNL, DHL, DPD and Vinted Go log into your account and pull in every parcel
    by themselves. This page is for the carriers whose **Connect with** column on
    the [carriers page](carriers.md) says a tracking number.

## 1. Set up IMAP

**Settings → Devices & Services → Add Integration → IMAP** — it ships with Home
Assistant, nothing to install. Gmail, iCloud and Outlook need an **app
password**, not your normal one.

| Setting | Use |
|---|---|
| Folder | A folder that holds only shipping mail, filled by a rule in your mail provider. `INBOX` works, but see [Privacy](#privacy) first |
| Search | `UnSeen UnDeleted` |
| Include message text | **On** while you work out your pattern, off afterwards — step 2 reads the body either way |
| Enable IMAP push | **On** where supported: tracked seconds after the mail lands instead of at the next poll |

!!! tip "Look at a real mail before writing any pattern"
    Listen to `imap_content` under **Developer tools → Events** and send yourself
    a shipping confirmation. What comes back is the `sender`, `subject` and body
    you have to match — which beats guessing.

## 2. Pull the number out

Do it in the entry's **Custom event data template** option rather than in your
automation: there, `text` is the *complete* body — the copy that rides along on
the event is cut off after 2 kB — and the result arrives as
`trigger.event.data.custom`.

=== "From the tracking link"

    The reliable one: the code sits in the URL, and the hostname proves which
    carrier it is. Swap in the host and parameter your own mail uses.

    ```jinja
    {{ text
       | regex_findall('tracking\\.example-carrier\\.com/\\?code=([A-Z0-9]{6,30})')
       | first | default('', true) }}
    ```

=== "From a labelled line"

    When the number is printed rather than linked. Anchor on the label beside it.

    ```jinja
    {{ text
       | regex_findall('(?i)track\\s*(?:&|and)?\\s*trace[^A-Z0-9]{0,20}([A-Z0-9]{6,30})')
       | first | default('', true) }}
    ```

=== "From the number's shape"

    Last resort — only for formats strict enough to match nothing else, such as
    the international UPU S10. A bare `\d{12,}` eventually matches an order or
    invoice number.

    ```jinja
    {{ text | regex_findall('\\b[A-Z]{2}\\d{9}[A-Z]{2}\\b')
       | first | default('', true) }}
    ```

`regex_findall` returns a list; `first | default('', true)` turns "no match" into
an empty string, which the automation below checks for.

## 3. The automation

```yaml
alias: Track parcels from e-mail
triggers:
  - trigger: event
    event_type: imap_content
conditions:
  - condition: template
    value_template: >-
      {{ trigger.event.data.initial and trigger.event.data.custom }}  # (1)!
actions:
  - action: postnord.track_parcel  # (2)!
    data:
      tracking_code: "{{ trigger.event.data.custom }}"
  - action: imap.seen  # (3)!
    data:
      entry: "{{ trigger.event.data.entry_id }}"
      uid: "{{ trigger.event.data.uid }}"
mode: queued
```

1.  `initial` is true only the first time a message is seen; the second half
    drops mails the template found nothing in.
2.  Your carrier's own domain — `postnord`, `gls`, `swiss_post`, … The
    aggregator has no `track_parcel`: it reads what carriers publish, it never
    writes to them. **GLS**, **Trunkrs** and **Dynalogic** also want a
    `postal_code`, but only if you run several hubs — otherwise the hub you
    configured supplies its own.
3.  Marks the mail read so the `UnSeen` search stops returning it. Use
    `imap.move` if you would rather file it away.

`mode: queued` matters: mails arriving as a batch fire the trigger several times
in a row, and the default `single` would drop all but the first.

### Several carriers, or several parcels

Let the sender pick the carrier, and loop when a split order brings more than one
number (have the template end in `| unique | list` for that):

```yaml
actions:
  - choose:
      - conditions:
          - "{{ 'postnord' in trigger.event.data.sender }}"
        sequence:
          - repeat:
              for_each: "{{ trigger.event.data.custom }}"
              sequence:
                - action: postnord.track_parcel
                  data:
                    tracking_code: "{{ repeat.item }}"
```

One IMAP entry per carrier, each with its own folder and template, is more setup
but keeps the patterns independent — worth it once one template sprouts
branches.

### Untrack what has arrived

Parcels stay tracked until you remove them; the *Delivered parcels* option only
controls what the sensor still shows. A mailbox-fed setup therefore grows
forever unless you clean up:

```yaml
triggers:
  - trigger: event
    event_type: postnord_parcel_delivered
actions:
  - delay: {days: 3}  # (1)!
  - action: postnord.untrack_parcel
    data:
      tracking_code: "{{ trigger.event.data.barcode }}"
mode: parallel
```

1.  Untracking also drops the parcel from the delivered sensor, so a few days'
    grace keeps "what arrived this week" intact. A `delay` this long does not
    survive a restart — walk the delivered sensor nightly if that bothers you.

## Privacy

It all runs on your own machine, and the only thing a carrier receives is a
number it issued itself. That is not the same as nobody seeing it: an IMAP login
hands Home Assistant your mailbox, and a mailbox is where password resets and
bank mail live.

| Place | What lands there |
|---|---|
| The event bus | Sender, subject and body of every matching message, live in **Developer tools → Events** |
| Automation traces | The full trigger payload of your last few runs, on disk and in the automation editor |
| Recorder and backups | Bus events can be recorded, and `.storage` holds the IMAP password either way |
| Your template | The complete, untruncated body of every matching message — including the ones that have nothing to do with parcels |

Three ways to give it less, best first:

1. **A separate mailbox**, used for nothing else, filled by a forwarding rule for
    carriers and webshops. Better still, order with an alias
    (`you+parcels@gmail.com`, or `shop@yourdomain` on a catch-all) so it arrives
    there directly. A leaked app password then costs you an afternoon.
2. **A narrower search.** The **Search** field takes raw IMAP criteria — what
    does not match is never fetched:
    `UnSeen UnDeleted FROM "no-reply@gls-group.eu"`.
3. **Message text off** once your pattern works. The template still gets the full
    body; traces and database then hold a tracking number instead of a letter.

## Share what worked

Worked out a pattern that reliably matches a carrier's mails?
[Post it in the discussions](https://github.com/ha-parcel-integrations/.github/discussions)
— with the number scrubbed — and the next person is done in a minute.
