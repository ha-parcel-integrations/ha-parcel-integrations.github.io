---
description: >-
  What to do when a parcel shows unknown, nothing appears at all, or an
  integration is marked Early release — plus how often each carrier polls.
---

# Troubleshooting

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

## Polling and rate limits

Each carrier integration polls automatically — there is no fixed interval to
tune. How often it checks adjusts to what your parcels are actually doing:

- No polling between 00:00–06:00 local time, aside from one catch-up check
  right at each end of that window, so an overnight update is never missed.
- Checks every 15 minutes while a tracked parcel is out for delivery today,
  starting an hour before its delivery window opens.
- Checks every 30–60 minutes otherwise — for a carrier you log into with an
  account, this is also the minimum cadence, since it's the only way to
  discover a new shipment that appeared on your account without you doing
  anything.
- For carriers you add by tracking code, polling stops entirely once every
  tracked parcel has been delivered (or none are tracked) — adding a parcel
  back starts it again immediately.

Delivery-day precision comes from the carrier's own data, not from how often
you ask, and the cadence above is chosen to be polite to the carrier's own
API — asking more often than that would just get you rate-limited, not
faster updates.
