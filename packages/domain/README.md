# timetabler-domain

Python package ported from the [desktop timetabler](https://github.com/T0mDrummond86/timetabler) repo:

- `timetable/core` — models, validation, staff hours, block delivery, …
- `timetable/solver` — CP-SAT placement and auto-timetable
- `timetable/io` — backup JSON, Excel import/export (Qt/UI imports stripped)

Sync updates from desktop with:

```bash
./scripts/sync-domain-from-desktop.sh
```
