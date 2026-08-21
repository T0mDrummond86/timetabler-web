---
id: import-ep-nb-csp
title: Import an EP-NB CSP spreadsheet
category: Importing data
keywords: ep-nb, east perth, northbridge, csp xlsx, spreadsheet csp, course study plan excel, skill set
---

**Import ▾ → EP-NB CSP** reads the East Perth / Northbridge course study plan
spreadsheet (`.xlsx`).

The importer works from the workbook's own header row rather than assuming fixed
columns, so layouts vary a little without breaking it. It expects:

- The qualification **title on row 1** — anywhere on the row, not necessarily
  column A.
- A **header row** naming a TPN column.

Class names come from the **skill-set description** column. Where that is blank,
the class is still imported but with a **placeholder name**, and the import
result tells you which ones so you can rename them on the **Classes** tab.

If you see *Workbook does not look like a CSP planning spreadsheet (expected a
title on row 1 and a header row naming a TPN column)*, you are either importing
the wrong file or the title row has been deleted.
