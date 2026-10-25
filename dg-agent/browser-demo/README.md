# Browser demo

A single-page version that runs in any browser with no server: UN verification, identification,
segregation (IMDG / IATA / warehouse) and spill response, using the demonstration data only.

* `engine.js` is a JavaScript port of `backend/app/engines` (dg, segregation, compat, spill).
* `ui.html` is the page; `build.sh` writes `data.js` from the seed files and `build.js` inlines data and engine and transpiles to ES2018 (older mobile browsers). The page shows an error message instead of a blank screen if the browser cannot run it.
* `run.js` + `cases.json` produce engine outputs for comparison with the Python engines.
  On the 24 cases the decisions are identical; wording differs only in how lists are printed in two messages.

Not included (needs the full application): login, saved reports, approvals, audit trail, SDS upload/OCR,
ERP, inspection, risk reports and PDF/Word export. When the Python engines change, update `engine.js` too.
