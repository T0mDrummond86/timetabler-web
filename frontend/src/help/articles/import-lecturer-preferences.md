---
id: import-lecturer-preferences
title: Import lecturer preferences
category: Importing data
keywords: lecturer preferences, availability import, preferences spreadsheet, competency import, staff availability upload, template, delivery hours, requested hours, additional notes, 21 hours
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

## What each sheet asks for

1. **Class preferences** — two firsts, two seconds, two thirds, each picked
   from the Qualification and Class dropdowns.
2. **Non-teaching day** — one weekday.
3. **Delivery hours requested** — how many hours a week the lecturer is asking
   to deliver. It arrives pre-filled with **21**, a full load for one FTE, so
   only lecturers wanting something different need to change it.
4. **Additional notes** — a free-text box for anything the fixed sections
   cannot say: job-share arrangements, travel between campuses, study leave.
5. **Blocked times** — write **X** in every half-hour the lecturer cannot
   teach.

**Delivery hours and notes are read by you, not by the importer.** They come
back in the workbook for you to read when you build the timetable; importing a
completed sheet brings in the preferences, the non-teaching day and the blocked
times, and leaves those two sections where they are. Keep the returned
workbooks if you want them later.
