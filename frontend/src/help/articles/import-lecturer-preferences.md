---
id: import-lecturer-preferences
title: Import lecturer preferences
category: Importing data
keywords: lecturer preferences, availability import, preferences spreadsheet, competency import, staff availability upload, template
---

**Import ▾ → Lecturer preferences** loads a completed availability and
competency spreadsheet, setting each lecturer's
[availability](#staff-availability) and
[competencies](#staff-competency) in bulk.

Get the blank workbook first from **Export ▾ → Lecturer prefs template**, send
it out, and import the completed copies.

The template is **local to the session you export it from**: one tab per
lecturer in this session, and the Qualification and Class dropdowns offer only
this session's. Importing works the same way, so a sheet naming a lecturer or
class that belongs to another session is reported rather than matched.

Each sheet is one lecturer. Errors name the sheet, which makes them quick to
chase:

- *Sheet 'X': lecturer 'Y' not found in session* — the name on the sheet does
  not match any lecturer in this session. Add the lecturer on the **Staff** tab
  first, or correct the spelling.
- *Sheet 'X': non-teaching day 'Y' is not valid* — the non-teaching day must be
  a weekday name.

Availability comes in as windows: blocked slots become the times the lecturer
**cannot** teach.
