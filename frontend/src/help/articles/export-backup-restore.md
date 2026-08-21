---
id: export-backup-restore
title: Back up a session and restore it
category: Exporting and printing
keywords: backup, restore, recover, undo everything, revert session, snapshot, json backup, safety copy, roll back
---

There are two backup routes.

**Excel round trip.** **Export ▾ → Timetable** gives you an `.xlsm` workbook.
Bringing it back with **Import ▾ → Session backup** restores the session from
it.

**JSON backup.** **Export ▾ → JSON backup** is a machine-readable snapshot of
the session — smaller and exact, and the better choice for a pure safety copy.

Before anything risky, the quickest safety net of all is
[duplicating the session](#sessions-create-rename-delete): you keep a working
copy in the app, with nothing to download or re-import.

If a restore reports *No Week row in this session; can't restore bookings*, the
target session has no calendar weeks yet — import the
[term calendar](#import-calendar) first.
