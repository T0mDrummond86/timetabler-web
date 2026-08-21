---
id: import-asc
title: Import from aSc Timetables
category: Importing data
keywords: asc, asc timetables, xml, import asc, migrate, existing timetable, bring in bookings, cards
---

**Import ▾ → aSc export** brings a whole timetable across from aSc Timetables:
staff, rooms, classes, qualifications **and bookings**.

Two formats are accepted:

- **`.xlsx`** — an aSc export with *Teachers*, *Classrooms*, *Classes* and
  *Lessons* sheets.
- **`.xml`** — an aSc 2012 XML export with teachers, lessons and cards.

Cohorts with identical subject sets are grouped into one multi-group
qualification, so an aSc timetable with four parallel cohorts arrives as one
qualification with four groups rather than four qualifications.

Errors to expect:

- *File does not look like an aSc Timetables export* — wrong file, or a format
  the importer does not recognise.
- *Lessons: unknown class 'X'* — a lesson references a class that is not in the
  Classes sheet.
- *Lessons: room 'X' … not found* — a lesson references a room that is not in
  the Classrooms sheet.
