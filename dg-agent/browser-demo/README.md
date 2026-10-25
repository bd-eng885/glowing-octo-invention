# Browser demo

A single-page version that runs in any browser with no server: UN verification, identification,
segregation (IMDG / IATA / warehouse) and spill response, using the demonstration data only.

* `engine.js` is a JavaScript port of `backend/app/engines` (dg, segregation, compat, spill).
* `ui.html` is the page; `build.sh` inlines the seed data and engine into one file.
* `run.js` + `cases.json` produce engine outputs for comparison with the Python engines.
  On the 24 cases the decisions are identical; wording differs only in how lists are printed in two messages.

Not included (needs the full application): login, saved reports, approvals, audit trail, SDS upload/OCR,
ERP, inspection, risk reports and PDF/Word export. When the Python engines change, update `engine.js` too.
