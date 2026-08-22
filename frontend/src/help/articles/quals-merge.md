---
id: quals-merge
title: Merge two qualifications
category: Classes, groups and qualifications
keywords: merge, combine, join qualifications, two into one, merge quals, combined qualification
---

**Merge** creates a *new* qualification holding the classes of two existing
ones. Select a qualification on the **Qualifications** tab and press **Merge**.

Then pick the other qualification, check the summary, name the result and give
it a group count.

![The Merge dialog, showing both sources and what the merged qualification will hold](/help/quals-merge.png)

**Both original qualifications survive the merge, unchanged.** Their names,
groups, bookings and class links are all left exactly as they were — a merge
only ever adds a record. That is why it works on a fully timetabled session,
unlike [Stage split](#quals-stage-split).

Details worth knowing:

- A class belonging to both is linked once, and the dialog says how many
  overlapped.
- The new qualification gets its own groups, named after it.
- If the two disagree on day/night or regular/block, you choose which the new
  one uses. The dialog warns that its classes will then be held to that window
  **on top of** the window they already have from their original qualification.
- The result is a standalone qualification, never added to a stage family.

You cannot reuse either source's name — they are both still there.
