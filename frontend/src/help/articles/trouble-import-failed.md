---
id: trouble-import-failed
title: An import failed — what the message means
category: Troubleshooting
keywords: import failed, error, does not look like, wrong file, upload failed, cannot import, invalid file, rejected
---

Most import failures are the wrong file rather than a broken one.

- *File does not look like an aSc Timetables export* — see
  [Importing from aSc](#import-asc).
- *Workbook does not look like a CSP planning spreadsheet* — see
  [EP-NB CSP](#import-ep-nb-csp).
- *Please upload a Word .docx file* — the [CSP import](#import-csp) needs
  `.docx`, not `.doc` or PDF.
- *Sheet 'X': lecturer 'Y' not found in session* — see
  [Lecturer preferences](#import-lecturer-preferences).
- *Workbook has no 'Overall' sheet* / *Workbook has no course sheets* — the
  visual-grid importers need their specific sheets.
- *No week exists in session* — import the [term calendar](#import-calendar)
  first.

Each import accepts particular file types, and the file picker filters to them —
if your file is greyed out in the picker, it is the wrong kind for that import.
