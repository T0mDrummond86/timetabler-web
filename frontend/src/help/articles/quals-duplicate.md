---
id: quals-duplicate
title: Duplicate a qualification
category: Classes, groups and qualifications
keywords: duplicate qualification, copy qualification, second intake, run it again, clone, new intake, same qualification twice, shared classes, duplicate all stages
---

**Duplicate** makes a second copy of a qualification — a new intake, a night
version, the same programme at another campus — **without recreating its
classes**. Select a qualification on the **Qualifications** tab and press
**Duplicate**, next to *Add* and *Delete*.

You are asked for a name. *"<name> (copy)"* is offered; anything not already
taken will do.

## The whole qualification, not one stage

A stage is its own record, so a qualification that runs over two stages is two
records. **Duplicate copies all of them**, and the confirmation names the stages
it found before anything is created — read that line. Naming the copy
*Cert IV Cyber 2027* gives you *Cert IV Cyber 2027 Stg1* and
*Cert IV Cyber 2027 Stg2*, each with its own groups and its own classes.

Stages are recognised two ways. One [split](#quals-stage-split) inside the app
is linked, so there is no guesswork. One that arrived from a course study plan
is not — its stages are only recognisable by being named the same apart from the
trailing *Stg1* / *Stage 2*, and that is what the app matches on. Names that
differ by more than the suffix are separate qualifications: *…STG1 -GRP1* and
*…STG1 -GRP2* are two groups of one stage, not two stages, and are left alone.

## Classes are shared, not copied

This is the whole point. The copy links the **same class records** as the
original. Change a class's duration or unit codes and both qualifications see
the change, because it is one class.

Building the second qualification by hand instead would create a *second*
"ICTNWK540", and the pair would then have to be folded back together with
[Consolidate](#classes-consolidate). Duplicating avoids that work entirely.

## What the copy gets of its own

- **Groups.** Cohorts belong to one qualification, so each stage of the copy
  gets a fresh set named after it, with the shared classes already sitting in
  each group's holding area ready to place. A stage keeps its own group count:
  copying a qualification whose Stg1 has one group and Stg2 has two gives you
  one and two.
- **Day/night, delivery mode and block settings**, taken from the original.
- **Online student counts** per lecturer, copied so they can be corrected rather
  than rebuilt.

## What the copy does not get

**Bookings.** The duplicate starts with an empty timetable. Its groups are new,
nobody has agreed to teach them yet, and copying placecards would put lecturers
and rooms into a second booking they never agreed to.

The original is untouched — same name, same groups, same classes, same
timetable.

The copy is a family of its own, never joined to the one it came from. Its
stages are properly linked to each other, so the Qualifications list shows the
copy as the single qualification it is — even when the original's stages arrived
as separate rows.
