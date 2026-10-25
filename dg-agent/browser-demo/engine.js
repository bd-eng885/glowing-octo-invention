// Browser port of the dg-agent rule engines (backend/app/engines/*.py). Deterministic; no network.
// Only demonstration data is embedded, so no result can be authoritative.
const E = (() => {
  const VERIFIED = "VERIFIED AGAINST SOURCE", MATCH_COND = "MATCH WITH CONDITIONS", DISCREPANCY = "DISCREPANCY FOUND",
    INSUFFICIENT = "INSUFFICIENT INFORMATION", NOT_VERIFIED = "NOT VERIFIED — HUMAN REVIEW REQUIRED";
  const HOLD = "HOLD — MANUAL VERIFICATION REQUIRED", CONFLICT = "CONFLICT IDENTIFIED — DO NOT LOAD/STOW AS PROPOSED";
  const MODE_LABEL = { IMDG: "IMDG Code (sea)", IATA: "IATA DGR (air)", UN_MODEL: "UN Model Regulations (reference)" };
  const GENERAL_LIMITATION = "A matching UN number alone is not proof of compliance. This check covers identification fields only; packaging, quantity limits, marking, labelling, documentation, stowage, segregation and operator/State acceptance must be verified separately by qualified personnel.";
  const SRC = DATA.sources.find((s) => s.code === "DEMO-UN-SEED");
  const ENTRIES = DATA.un.map((e, i) => ({ ...e, id: i + 1 }));

  // ---------------------------------------------------------------- text utilities
  const OCR = { O: "0", o: "0", I: "1", l: "1", S: "5" };
  function normalizeUN(value) {
    const notes = [];
    if (!value) return [null, notes];
    const raw = String(value).trim();
    const m = raw.match(/^(UN|ID)?\s*[-:]?\s*([0-9OIlS]{4})$/i);
    if (!m) return [null, [`'${raw}' is not a valid UN/ID number format (expected e.g. UN1203).`]];
    const prefix = (m[1] || "UN").toUpperCase();
    const digits = m[2];
    const fixed = [...digits].map((c) => OCR[c] ?? c).join("");
    if (fixed !== digits) notes.push(`Possible OCR/typing error corrected: '${digits}' read as '${fixed}'. Confirm against the document.`);
    if (!/^\d{4}$/.test(fixed)) return [null, [...notes, `'${raw}' contains non-numeric characters.`]];
    return [prefix + fixed, notes];
  }
  function findUNs(text) {
    const out = [], seen = new Set();
    for (const m of (text || "").matchAll(/\b(UN|ID)\s*[-:]?\s*([0-9OIlS]{4})\b/gi)) {
      const [un, notes] = normalizeUN(m[0]);
      if (un && !seen.has(un)) { seen.add(un); out.push([un, notes]); }
    }
    return out;
  }
  function casOK(cas) {
    const m = String(cas).trim().match(/^(\d{2,7})-(\d{2})-(\d)$/);
    if (!m) return false;
    const d = [...(m[1] + m[2])].reverse();
    return d.reduce((s, c, i) => s + (i + 1) * Number(c), 0) % 10 === Number(m[3]);
  }
  function findCAS(text) {
    const out = [], seen = new Set();
    for (const m of (text || "").matchAll(/\b(\d{2,7})-(\d{2})-(\d)\b/g)) {
      if (seen.has(m[0])) continue;
      seen.add(m[0]); out.push({ cas: m[0], checksum_valid: casOK(m[0]) });
    }
    return out;
  }
  const ROMAN = { I: "I", II: "II", III: "III", 1: "I", 2: "II", 3: "III" };
  function normPG(v) {
    if (v === null || v === undefined) return null;
    const s = String(v).trim().toUpperCase().replace("PG", "").replace("PACKING GROUP", "").trim();
    if (["", "-", "N/A", "NA", "NONE"].includes(s)) return null;
    return ROMAN[s] ?? null;
  }
  function normClass(v) {
    if (v === null || v === undefined) return null;
    const s = String(v).trim().toUpperCase().replace("CLASS", "").replace("DIVISION", "").trim().split("(")[0].trim();
    return s || null;
  }
  function normText(s) {
    s = (s || "").normalize("NFKC").toUpperCase();
    s = s.replace(/[^\p{L}\p{N}_%.,()\- ]+/gu, " ");
    s = s.replace(/\s*,\s*/g, ", ");
    return s.replace(/\s+/g, " ").replace(/^[ ,]+|[ ,]+$/g, "");
  }
  const VARIANTS = [["SULFUR", "SULPHUR"], ["ALUMINUM", "ALUMINIUM"], ["CESIUM", "CAESIUM"]];
  const canonical = (s) => VARIANTS.reduce((acc, [a, b]) => acc.split(a).join(b), normText(s));
  const isUpperWord = (w) => { const L = [...w].filter((c) => /\p{L}/u.test(c)); return L.length > 0 && L.every((c) => c !== c.toLowerCase()); };
  function psnAlternatives(psn) {
    const cores = [];
    for (const seg of psn.split(/\s+or\s+/)) {
      const core = [];
      for (const w of seg.split(/\s+/).filter(Boolean)) {
        if (isUpperWord(w) || (![...w].some((c) => /\p{L}/u.test(c)) && core.length)) core.push(w); else break;
      }
      if (core.length) cores.push(normText(core.join(" ")));
    }
    return cores.length ? cores : [normText(psn)];
  }
  function stripTech(d) { const m = d.trim().match(/^(.*?)\s*\(([^)]*)\)\s*$/); return m ? [m[1], m[2]] : [d, null]; }
  // difflib.SequenceMatcher(None, a, b).ratio() for short strings (no autojunk below 200 chars)
  function ratio(a, b) {
    function lm(alo, ahi, blo, bhi) {
      let besti = alo, bestj = blo, bestsize = 0, j2len = {};
      for (let i = alo; i < ahi; i++) {
        const n = {};
        for (let j = blo; j < bhi; j++) if (a[i] === b[j]) { const k = (j2len[j - 1] || 0) + 1; n[j] = k; if (k > bestsize) { besti = i - k + 1; bestj = j - k + 1; bestsize = k; } }
        j2len = n;
      }
      return [besti, bestj, bestsize];
    }
    let M = 0; const q = [[0, a.length, 0, b.length]];
    while (q.length) { const [alo, ahi, blo, bhi] = q.pop(); const [i, j, k] = lm(alo, ahi, blo, bhi);
      if (k) { M += k; if (alo < i && blo < j) q.push([alo, i, blo, j]); if (i + k < ahi && j + k < bhi) q.push([i + k, ahi, j + k, bhi]); } }
    return a.length + b.length ? (2 * M) / (a.length + b.length) : 1;
  }

  // ---------------------------------------------------------------- provenance
  const evidence = (e) => ({ source_code: SRC.code, publisher: SRC.publisher, title: SRC.title, edition: SRC.edition,
    effective_date: SRC.effective_date, section_ref: e.section_ref, rule_set: "UN_MODEL", source_verification_status: "demo_seed",
    entry_verification_status: "demo_seed", authoritative: false,
    limitations: [`Source '${SRC.code}' is DEMONSTRATION DATA, not an authoritative regulatory source.`,
      `Entry ${e.un_number} has not been verified against the source text (status: demo_seed).`] });
  function labelsFor(e, mode) {
    const labels = [`Class/Division ${e.hazard_class} hazard label`, ...e.subsidiary_hazards.map((s) => `Class/Division ${s} subsidiary hazard label`)];
    const marks = [`${e.un_number} and Proper Shipping Name`];
    if (mode === "IMDG") marks.push("Marine pollutant mark: STATUS NOT LOADED — determine from DGL / classification criteria");
    if (mode === "IATA") marks.push("Cargo Aircraft Only label: DEPENDS on packing instruction/quantity — IATA data not loaded");
    return { labels, marks, basis: "Derived from class and subsidiary hazards (rule-based). Exemptions (e.g. limited/excepted quantities) and special provisions can change requirements — confirm against applicable rules." };
  }

  // ---------------------------------------------------------------- verification
  const C = (field, result, declared, reference, message) => ({ field, result, declared, reference, message });
  function comparePSN(declared, e) {
    if (!declared) return C("proper_shipping_name", "insufficient", null, e.proper_shipping_name, "Proper Shipping Name not declared.");
    const [coreDecl, tech] = stripTech(declared);
    const d = normText(coreDecl), alts = psnAlternatives(e.proper_shipping_name), full = normText(e.proper_shipping_name);
    const nos = alts.some((a) => a.includes("N.O.S"));
    if (alts.includes(d) || d === full) {
      if (nos && !tech) return C("proper_shipping_name", "condition", declared, e.proper_shipping_name, "Generic / N.O.S. entry: a technical name in parentheses may be required. Classification criteria for generic entries must be confirmed.");
      if (nos) return C("proper_shipping_name", "condition", declared, e.proper_shipping_name, `Generic / N.O.S. entry with technical name '${tech}': confirm the technical name and that the generic entry is the most specific applicable entry.`);
      return C("proper_shipping_name", "match", declared, e.proper_shipping_name, "Declared name matches an authorised name in the entry.");
    }
    if (alts.map(canonical).includes(canonical(coreDecl)))
      return C("proper_shipping_name", "condition", declared, e.proper_shipping_name, "Matches apart from a spelling variant (e.g. sulfur/sulphur). Confirm the variant is acceptable under the applicable rules.");
    for (const a of alts) if (d.startsWith(a + " ") || d.startsWith(a + ", "))
      return C("proper_shipping_name", "condition", declared, e.proper_shipping_name, `Declared name begins with the authorised name '${a}' followed by additional text. Confirm the additional text is permitted (e.g. qualifying description).`);
    const best = Math.max(...alts.map((a) => ratio(d, a)));
    let msg = "Declared name does not match the Proper Shipping Name for this UN number.";
    if (best >= 0.8) msg += ` Very similar (similarity ${best.toFixed(2)}) — possible misspelling or OCR error.`;
    return C("proper_shipping_name", "discrepancy", declared, e.proper_shipping_name, msg);
  }
  function compareEntry(decl, e, mode) {
    const checks = [comparePSN(decl.proper_shipping_name, e)];
    const dc = normClass(decl.hazard_class);
    if (dc === null) checks.push(C("hazard_class", "insufficient", null, e.hazard_class, "Hazard class/division not declared."));
    else if (dc === e.hazard_class) checks.push(C("hazard_class", "match", dc, e.hazard_class, "Primary hazard class matches."));
    else if (e.subsidiary_hazards.includes(dc)) checks.push(C("hazard_class", "discrepancy", dc, e.hazard_class, `Declared class ${dc} is a SUBSIDIARY hazard of this entry; primary hazard is ${e.hazard_class}.`));
    else checks.push(C("hazard_class", "discrepancy", dc, e.hazard_class, "Primary hazard class does not match."));
    const ds = decl.subsidiary_hazards;
    if (ds === null || ds === undefined) {
      if (e.subsidiary_hazards.length) checks.push(C("subsidiary_hazards", "insufficient", null, e.subsidiary_hazards, "Subsidiary hazards not declared but the entry has subsidiary hazard(s)."));
      else checks.push(C("subsidiary_hazards", "match", null, [], "No subsidiary hazard in entry; none declared."));
    } else {
      const dset = [...new Set(ds.filter(Boolean).map(normClass))].sort(), eset = [...e.subsidiary_hazards].sort();
      if (JSON.stringify(dset) === JSON.stringify(eset)) checks.push(C("subsidiary_hazards", "match", dset, eset, "Subsidiary hazards match."));
      else {
        const missing = eset.filter((x) => !dset.includes(x)), extra = dset.filter((x) => !eset.includes(x));
        checks.push(C("subsidiary_hazards", "discrepancy", dset, eset, `Subsidiary hazards differ. Missing: ${missing.length ? missing.join(", ") : "none"}; not in entry: ${extra.length ? extra.join(", ") : "none"}.`));
      }
    }
    const raw = decl.packing_group, dpg = normPG(raw), pgs = e.packing_groups;
    if (raw && dpg === null && !["-", "N/A", "NA", "NONE"].includes(String(raw).trim().toUpperCase())) checks.push(C("packing_group", "discrepancy", raw, pgs, `'${raw}' is not a valid packing group.`));
    else if (!pgs.length) checks.push(dpg ? C("packing_group", "discrepancy", dpg, null, "A packing group is declared but this entry has no packing group assigned.") : C("packing_group", "match", null, null, "No packing group applicable to this entry; none declared."));
    else if (dpg === null) checks.push(C("packing_group", "insufficient", null, pgs, `Packing group required (entry permits ${pgs.join(", ")}) but not declared.`));
    else if (!pgs.includes(dpg)) checks.push(C("packing_group", "discrepancy", dpg, pgs, `Packing group ${dpg} is not available for this entry (permits ${pgs.join(", ")}).`));
    else if (pgs.length > 1) checks.push(C("packing_group", "condition", dpg, pgs, "Packing group is permitted, but the entry has several; the assignment depends on classification criteria (e.g. flash point / boiling point / toxicity data). Confirm from test data or SDS."));
    else checks.push(C("packing_group", "match", dpg, pgs, "Packing group matches."));
    checks.push(C("special_provisions", "condition", null, null, "Special provisions are NOT LOADED for this entry; they cannot be evaluated."));
    if (mode === "IMDG") checks.push(C("marine_pollutant", "condition", decl.marine_pollutant ?? null, null, "Marine pollutant status not loaded for this entry; determine from DGL and classification criteria."));
    return checks;
  }
  function statusOf(checks) {
    const r = new Set(checks.map((c) => c.result));
    return r.has("discrepancy") ? DISCREPANCY : r.has("insufficient") ? INSUFFICIENT : r.has("condition") ? MATCH_COND : VERIFIED;
  }
  function verify(declared, mode) {
    const [un, notes] = normalizeUN(declared.un_number);
    const res = { mode, mode_label: MODE_LABEL[mode], normalized_un: un, notes, general_limitation: GENERAL_LIMITATION,
      decision: "NOT APPROVED — assistance only; requires authorised review" };
    if (!un) return { ...res, status: INSUFFICIENT, provisional_status: INSUFFICIENT, checks: [], corrective_actions: ["Provide a valid UN/ID number (format UNnnnn) from the shipping documents."] };
    const cands = ENTRIES.filter((e) => e.un_number === un);
    if (!cands.length) return { ...res, status: NOT_VERIFIED, provisional_status: INSUFFICIENT, checks: [], matched_entry: null,
      corrective_actions: [`No ${MODE_LABEL[mode]} entry for ${un} is loaded. Verify manually against the applicable authoritative edition, or load the licensed dataset.`, "Do NOT treat the absence of data as evidence that the goods are not dangerous."] };
    const scored = cands.map((e) => { const ch = compareEntry(declared, e, mode); return [ch.filter((c) => c.result === "match").length - 2 * ch.filter((c) => c.result === "discrepancy").length, e, ch]; }).sort((x, y) => y[0] - x[0]);
    const [, e, checks] = scored[0];
    const basis = mode === "UN_MODEL" ? "mode" : "reference_only";
    const limitations = (basis === "reference_only" ? [`No ${MODE_LABEL[mode]} data loaded for ${un}. The comparison used UN Model Regulations reference data only; mode-specific provisions may differ.`] : []).concat(evidence(e).limitations);
    const corrective = [];
    for (const c of checks) {
      if (c.result === "discrepancy") corrective.push(`Correct or justify ${c.field.replace(/_/g, " ")}: declared '${c.declared}', reference '${c.reference}'. ${c.message}`);
      else if (c.result === "insufficient") corrective.push(`Provide ${c.field.replace(/_/g, " ")}. ${c.message}`);
    }
    corrective.push("Have a qualified DG professional verify this entry against the applicable authoritative edition.");
    return { ...res, status: NOT_VERIFIED, provisional_status: statusOf(checks), basis, matched_entry: { ...e, labelling: labelsFor(e, mode) },
      checks, data_limitations: limitations, corrective_actions: corrective, evidence: [evidence(e)] };
  }

  // ---------------------------------------------------------------- identification
  function identify({ name, un, cas, text, mode = "IMDG", context = {} }) {
    const hits = new Map(), notes = [];
    const hit = (e, reason, w) => { const h = hits.get(e.id) || { entry: e, reasons: [], score: 0 }; h.reasons.push(reason); h.score += w; hits.set(e.id, h); };
    const uns = [];
    if (un) { const [n, nn] = normalizeUN(un); notes.push(...nn); if (n) uns.push(n); else notes.push(`Supplied UN number '${un}' is invalid.`); }
    if (text) for (const [n, nn] of findUNs(text)) { uns.push(n); notes.push(...nn); }
    const casList = [];
    if (cas) casList.push({ cas: cas.trim(), checksum_valid: casOK(cas) });
    if (text) casList.push(...findCAS(text));
    for (const c of casList) if (!c.checksum_valid) notes.push(`CAS ${c.cas} fails the CAS check-digit test — likely a typing/OCR error. Not used.`);
    for (const e of ENTRIES) {
      if (uns.includes(e.un_number)) hit(e, `UN number ${e.un_number} supplied/extracted`, 5);
      for (const c of casList) if (c.checksum_valid && e.cas_numbers.includes(c.cas)) hit(e, `CAS ${c.cas} associated with this entry (concentration/form not confirmed)`, 3);
      if (name) {
        const q = normText(name), names = [...psnAlternatives(e.proper_shipping_name), ...e.synonyms.map(normText)];
        if (names.includes(q)) hit(e, `Name '${name}' matches entry name/synonym`, 4);
        else { const r = Math.max(0, ...names.map((n) => ratio(q, n))); if (r >= 0.82) hit(e, `Name '${name}' is similar to entry name (similarity ${r.toFixed(2)})`, 2); }
      }
    }
    const results = [...hits.values()].sort((a, b) => b.score - a.score).map((h) => {
      const strong = h.reasons.length >= 2 && h.score >= 7;
      return { category: "CANDIDATE", confidence: `${strong ? "high" : h.score >= 4 ? "medium" : "low"} (identity match) — data NOT authoritative`,
        match_reasons: h.reasons, entry: { ...h.entry, labelling: labelsFor(h.entry, mode) }, limitations: evidence(h.entry).limitations };
    });
    const matched = new Set([...hits.values()].filter((h) => h.reasons.some((r) => r.includes("UN number"))).map((h) => h.entry.un_number));
    const unmatched = [...new Set(uns)].filter((u) => !matched.has(u));
    for (const u of unmatched) notes.push(`${u} was supplied/extracted but no entry for it is loaded. Its classification cannot be checked; candidates below (if any) come from other identifiers and may not describe this product.`);
    if (casList.length && (casList.length > 1 || unmatched.length)) notes.push("CAS-based candidates describe the pure substance. A mixture or solution may be classified differently (e.g. under a generic or N.O.S. entry); concentration and test data decide.");
    let overall;
    if (unmatched.length) overall = { category: "UNKNOWN", message: `Declared/extracted UN number(s) ${unmatched.join(", ")} not found in loaded data. Candidates from CAS/name are shown for reference only. Absence of data is not evidence that the goods are not dangerous.` };
    else if (!results.length) overall = { category: "UNKNOWN", message: "No match in the loaded datasets. This does NOT mean the product is non-dangerous. Obtain the SDS (Section 14), composition and test data and refer to a qualified DG professional." };
    else overall = { category: "CANDIDATE", message: "Candidate classification — more information or qualified verification required." };
    const missing = [["concentration", "concentration / composition"], ["physical_state", "physical state"], ["quantity", "quantity per package"], ["packaging", "packaging type"], ["flash_point", "flash point / classification test data"]].filter(([k]) => !context[k]).map(([, l]) => l);
    const ghs = text && /\bH[2-4]\d{2}\b/.test(text) ? "GHS hazard statements detected. GHS (workplace/supply) classification is distinct from transport classification: a product may be GHS-hazardous without being regulated for a given transport mode, and vice versa." : null;
    return { overall, candidates: results, unmatched_un_numbers: unmatched, notes, missing_information: missing, ghs_note: ghs };
  }

  // ---------------------------------------------------------------- compatibility screening
  const RULES = [
    [["ACID"], ["BASE"], "high", "Violent neutralisation, heat and spattering."],
    [["ACID"], ["HYPOCHLORITE"], "high", "Release of chlorine gas."],
    [["AMMONIA"], ["HYPOCHLORITE"], "high", "Formation of toxic chloramine gases."],
    [["ACID"], ["CYANIDE"], "high", "Release of highly toxic hydrogen cyanide."],
    [["OXIDIZER"], ["FLAMMABLE"], "high", "Oxidizers intensify fire and may cause ignition/explosion of combustibles."],
    [["ORGANIC_PEROXIDE"], ["FLAMMABLE", "ACID", "BASE", "OXIDIZER", "AMMONIA"], "high", "Organic peroxides may decompose violently on contamination."],
    [["WATER_REACTIVE"], ["AQUEOUS", "ACID", "BASE", "HYPOCHLORITE", "AMMONIA"], "high", "Contact with water/aqueous material may release flammable or toxic gas and heat."],
    [["CORROSIVE_UNSPECIFIED"], ["CORROSIVE_UNSPECIFIED", "ACID", "BASE"], "medium", "Possible acid/base incompatibility — determine whether each corrosive is acidic or alkaline."],
    [["OXIDIZER"], ["AMMONIA"], "medium", "Some oxidizers react hazardously with ammonia/ammonium compounds."],
  ];
  function groupsFor(it) {
    const g = new Set(it.reactive_groups || []);
    const hz = new Set([it.hazard_class || "", ...(it.subsidiary_hazards || [])]);
    const name = [it.name, it.proper_shipping_name].filter(Boolean).join(" ").toUpperCase();
    const any = (...xs) => xs.some((x) => hz.has(x));
    if (any("3", "2.1", "4.1")) g.add("FLAMMABLE");
    if (hz.has("5.1")) g.add("OXIDIZER");
    if (hz.has("5.2")) g.add("ORGANIC_PEROXIDE");
    if (hz.has("4.3")) g.add("WATER_REACTIVE");
    if (any("6.1", "2.3")) g.add("TOXIC");
    if (name.includes("HYPOCHLORITE")) { g.add("HYPOCHLORITE"); g.add("OXIDIZER"); }
    if (name.includes("AMMONIA") || name.includes("AMMONIUM")) g.add("AMMONIA");
    if (name.includes("CYANIDE")) g.add("CYANIDE");
    if (name.includes("ACID")) g.add("ACID");
    if (name.includes("HYDROXIDE") || name.includes("CAUSTIC") || name.includes("AMMONIA SOLUTION")) g.add("BASE");
    if (name.includes("SOLUTION") || name.includes("AQUEOUS")) g.add("AQUEOUS");
    if (hz.has("8") && !g.has("ACID") && !g.has("BASE")) g.add("CORROSIVE_UNSPECIFIED");
    return [...g].sort();
  }
  function screen(items) {
    const en = items.map((it) => ({ ...it, groups: groupsFor(it) }));
    const pairs = [];
    for (let i = 0; i < en.length; i++) for (let j = i + 1; j < en.length; j++) {
      const ga = new Set(en[i].groups), gb = new Set(en[j].groups), flags = [];
      for (const [x, y, sev, why] of RULES) {
        const hx = (s) => x.some((k) => s.has(k)), hy = (s) => y.some((k) => s.has(k));
        if ((hx(ga) && hy(gb)) || (hx(gb) && hy(ga))) flags.push({ severity: sev, reason: why });
      }
      pairs.push({ a: en[i].id, b: en[j].id, flags, result: flags.some((f) => f.severity === "high") ? "INCOMPATIBLE — REVIEW" : flags.length ? "CAUTION — REVIEW" : "NO SCREENING FLAG" });
    }
    return { items: en, pairs };
  }

  // ---------------------------------------------------------------- segregation
  const IDX = { 1.1: 0, 1.2: 0, 1.5: 0, 1.3: 1, 1.6: 1, 1.4: 2, 2.1: 3, 2.2: 4, 2.3: 5, 3: 6, 4.1: 7, 4.2: 8, 4.3: 9, 5.1: 10, 5.2: 11, 6.1: 12, 6.2: 13, 7: 14, 8: 15, 9: 16 };
  const RANK = { X: 0, 1: 1, 2: 2, 3: 3, 4: 4 };
  function enrich(items) {
    const notes = [];
    const out = items.map((raw, i) => {
      const it = { ...raw, id: raw.id || `item${i + 1}` };
      it.hazard_class = normClass(it.hazard_class);
      it.subsidiary_hazards = (it.subsidiary_hazards || []).filter(Boolean).map(normClass);
      it.data_origin = "user";
      const [un] = normalizeUN(it.un_number);
      it.un_number = un;
      const e = un && ENTRIES.find((x) => x.un_number === un);
      if (e && !it.hazard_class) {
        it.hazard_class = e.hazard_class; it.subsidiary_hazards = [...e.subsidiary_hazards]; it.proper_shipping_name = e.proper_shipping_name;
        it.data_origin = "looked up from DEMO-UN-SEED (demo_seed)";
        notes.push(`${it.id}: class/subsidiary taken from DEMO-UN-SEED — NOT authoritative data.`);
      } else if (e) {
        it.proper_shipping_name = it.proper_shipping_name || e.proper_shipping_name;
        if (e.hazard_class !== it.hazard_class || [...e.subsidiary_hazards].sort().join() !== [...it.subsidiary_hazards].sort().join()) {
          notes.push(`${it.id}: declared class/subsidiary (${it.hazard_class} / ${it.subsidiary_hazards.join(",") || "none"}) differs from loaded data for ${un} (${e.hazard_class} / ${e.subsidiary_hazards.join(",") || "none"}). Resolve before relying on result.`);
          it.data_conflict = true;
        }
      }
      return it;
    });
    return [out, notes];
  }
  function imdgPair(a, b, arr) {
    const t = DATA.imdg, issues = [], conds = [];
    const ha = a.hazard_class ? [a.hazard_class, ...a.subsidiary_hazards] : [], hb = b.hazard_class ? [b.hazard_class, ...b.subsidiary_hazards] : [];
    if (!ha.length || !hb.length) return { status: "hold", code: null, label: "Hazard class missing", issues: ["Hazard class missing for one or both items — cannot evaluate."], conditions: [] };
    const unm = [...ha, ...hb].filter((h) => !(h in IDX));
    if (unm.length) return { status: "hold", code: null, label: "Class not mapped", issues: [`Cannot map hazard(s) ${unm.join(", ")} to the segregation table (division required for Class 1/2/4/5/6).`], conditions: [] };
    let worst = "X", combo = null, star = false;
    for (const x of ha) for (const y of hb) {
      const code = t.matrix[IDX[x]][IDX[y]];
      if (code === "*") { star = true; continue; }
      if (RANK[code] > RANK[worst]) { worst = code; combo = [x, y]; }
    }
    if (star) issues.push(t.codes["*"]);
    if (ha.length + hb.length > 2) conds.push("Subsidiary hazards were included and the most stringent requirement applied. The applicable edition may contain exceptions or specific provisions that alter this — qualified review required.");
    if (a.hazard_class === b.hazard_class) conds.push("Both items share the same primary class; check the applicable provisions for goods of the same class and whether the substances react dangerously with each other.");
    for (const it of [a, b]) conds.push(`${it.id}: individual Dangerous Goods List segregation provisions NOT LOADED — must be checked manually.`);
    const label = t.codes[worst];
    let status;
    if (star) status = "hold";
    else if (arr === "same_ctu" && worst !== "X") {
      status = "conflict";
      issues.push(worst === "1" ? "Goods requiring 'away from' segregation in the same CTU: only permissible where the applicable provisions/competent authority allow — treat as prohibited until verified." : `'${label}' cannot be achieved within one cargo transport unit.`);
    } else if (worst === "X") status = "no_general_requirement";
    else { status = "requirement"; issues.push(`Required segregation: '${label}'. Actual stowage positions must be verified against the applicable stowage/segregation provisions for the ship type.`); }
    return { status, code: star ? "*" : worst, label: star ? t.codes["*"] : label, governing_combination: combo, issues, conditions: conds };
  }
  function iataPair(a, b, arr) {
    const t = DATA.iata;
    const ha = new Set([a.hazard_class, ...a.subsidiary_hazards].filter(Boolean)), hb = new Set([b.hazard_class, ...b.subsidiary_hazards].filter(Boolean));
    if (!ha.size || !hb.size) return { status: "hold", code: null, label: "Hazard class missing", issues: ["Hazard class missing — cannot evaluate."], conditions: [] };
    const issues = [], conds = [];
    let hit = null;
    for (const p of t.pairs) if ((ha.has(p.a) && hb.has(p.b)) || (ha.has(p.b) && hb.has(p.a))) hit = p;
    for (const [it, hs] of [[a, ha], [b, hb]])
      if ([...hs].some((h) => h.startsWith("1")) && !((it.explosive_compat_group || "").toUpperCase() === "S" && hs.has("1.4"))) issues.push(`${it.id}: ${t.class1_rule}`);
    let status;
    if (hit) { status = ["same_uld", "same_ctu"].includes(arr) ? "conflict" : "requirement"; issues.push(`Packages of ${hit.a} and ${hit.b} require segregation (${hit.note}).`); }
    else if (issues.length) status = "hold";
    else { status = "no_pair_in_loaded_subset"; conds.push("No pair found in the LOADED subset. The loaded IATA table is partial; this is not evidence that segregation is not required."); }
    return { status, code: hit ? "segregate" : null, label: hit ? "Segregation required" : "No pair in loaded subset", issues, conditions: conds };
  }
  function segregate(rawItems, mode, arr) {
    const [items, notes] = enrich(rawItems);
    const missing = [];
    for (const it of items) { for (const k of ["quantity", "package"]) if (!it[k]) missing.push(`${it.id}: ${k} not provided`); if (!it.hazard_class) missing.push(`${it.id}: hazard class unknown`); }
    const scr = screen(items);
    if (mode === "WAREHOUSE") return { mode, items: scr.items, pairs: scr.pairs.map((p) => ({ ...p, status: p.flags.some((f) => f.severity === "high") ? "conflict" : p.flags.length ? "requirement" : "no_general_requirement", label: p.result, issues: p.flags.map((f) => `${f.severity}: ${f.reason}`), conditions: [] })), decision: HOLD, notes, missing_information: missing,
      limitations: ["Transport segregation rules are not storage rules. Warehouse storage requires the site-specific risk assessment, local fire code and permit conditions, and SDS Sections 7/10.", "Screening only: 'NO SCREENING FLAG' is not a confirmation of compatibility."] };
    const pairs = [];
    for (let i = 0; i < items.length; i++) for (let j = i + 1; j < items.length; j++) {
      const a = items[i], b = items[j];
      const r = (mode === "IMDG" ? imdgPair : iataPair)(a, b, arr);
      if (a.data_conflict || b.data_conflict) { if (r.status !== "conflict") r.status = "hold"; r.issues.push("Declared data conflicts with loaded data — resolve first."); }
      const sp = scr.pairs.find((p) => (p.a === a.id && p.b === b.id));
      if (sp && sp.flags.length) {
        r.conditions.push(...sp.flags.map((f) => `NON-REGULATORY screening (${f.severity}): ${f.reason} Check DGL segregation provisions (e.g. segregation groups) and SDS Section 10.`));
        if (["no_general_requirement", "no_pair_in_loaded_subset"].includes(r.status) && sp.flags.some((f) => f.severity === "high")) {
          r.status = "hold"; r.issues.push("Chemical compatibility screening flags a hazardous reaction; the general table alone cannot clear this pair.");
        }
      }
      pairs.push({ ...r, a: a.id, b: b.id });
    }
    const st = new Set(pairs.map((p) => p.status));
    return { mode, items, pairs, notes, missing_information: missing, decision: st.has("conflict") ? CONFLICT : HOLD,
      table: mode === "IMDG" ? "IMDG-SEG-DEMO (demo transcription, not authoritative)" : "IATA-SEG-DEMO (partial demo subset, not authoritative)",
      alternative: st.has("conflict") && arr === "same_ctu" && !missing.length ? "Load the conflicting items in separate CTUs and determine the required stowage separation between those CTUs from the applicable stowage/segregation provisions." : null,
      manual_checks: mode === "IATA" ? DATA.iata.manual_checks : [],
      limitations: [`Rule table comes from a DEMO SEED source and is not authoritative.${mode === "IATA" ? " It is a partial subset; absent rules are not evidence of compliance." : ""}`, "A generic class-vs-class table is never the sole basis for approval: individual entry provisions, segregation groups, special provisions and exceptions apply."] };
  }

  // ---------------------------------------------------------------- spill response
  const PROFILES = {
    1: ["Explosive", ["Explosion / mass detonation risk. Do not approach if fire threatens the cargo.", "Evacuate and call emergency services immediately."]],
    2.1: ["Flammable gas", ["Vapour cloud ignition / explosion risk.", "Pressure receptacle failure if heated."]],
    2.2: ["Non-flammable gas", ["Asphyxiation in confined/low areas.", "Pressure receptacle failure if heated.", "Cryogenic burns if refrigerated liquefied gas."]],
    2.3: ["Toxic gas", ["Inhalation hazard — potentially fatal.", "Treat as major incident: evacuate/shelter-in-place."]],
    3: ["Flammable liquid", ["Flammable vapours; vapours may travel to ignition sources and flash back.", "Vapour accumulation in drains/low areas."]],
    4.1: ["Flammable solid", ["Readily combustible; some are self-reactive or desensitised explosives."]],
    4.2: ["Spontaneously combustible", ["May ignite on contact with air."]],
    4.3: ["Dangerous when wet", ["Contact with water emits flammable and/or toxic gas."]],
    5.1: ["Oxidizer", ["Intensifies fire; may ignite combustibles (wood, paper, absorbents, oils)."]],
    5.2: ["Organic peroxide", ["Thermally unstable; may decompose explosively; contamination sensitive."]],
    6.1: ["Toxic", ["Toxic by ingestion, skin contact and/or inhalation."]],
    6.2: ["Infectious", ["Biological hazard — specialist response."]],
    7: ["Radioactive", ["Radiation exposure — notify radiation protection authority; specialist response."]],
    8: ["Corrosive", ["Severe skin/eye damage; may react with metals releasing hydrogen; may react with water."]],
    9: ["Miscellaneous", ["Hazards vary (e.g. environmentally hazardous, lithium batteries, elevated temperature)."]],
  };
  const PRECAUTIONS = {
    3: ["Eliminate ignition sources; use only intrinsically safe/explosion-protected equipment if trained.", "Prevent entry to drains and confined spaces."],
    2.1: ["Eliminate ignition sources; do not operate electrical switches in the vapour area."],
    4.3: ["Do NOT apply water or aqueous agents; keep material dry."],
    5.1: ["Do NOT use combustible absorbents (sawdust, paper, rags)."],
    5.2: ["Do NOT use combustible absorbents; avoid confinement; keep away from heat."],
    8: ["Avoid all skin/eye contact; do not use incompatible metal tools/containers.", "Do NOT apply neutralising chemicals unless the SDS / specialist confirms the method."],
    2.3: ["Approach only from upwind by trained responders with appropriate respiratory protection."],
    6.1: ["Avoid contact and inhalation; prevent spread; trained responders only."],
    7: ["Do not touch or move damaged packages; minimise time, maximise distance."],
    6.2: ["Do not touch damaged packages; isolate; notify public health authority."],
    1: ["Do not fight fire involving the cargo; evacuate to a safe distance."],
  };
  function spill(d) {
    const threshold = 200;
    const [un, unNotes] = normalizeUN(d.un_number);
    let hc = normClass(d.hazard_class), subs = (d.subsidiary_hazards || []).filter(Boolean).map(normClass);
    const notes = [...unNotes], ev = [];
    let entry = null;
    if (un) {
      entry = ENTRIES.find((e) => e.un_number === un) || null;
      if (entry) { ev.push(evidence(entry)); if (!hc) { hc = entry.hazard_class; subs = [...entry.subsidiary_hazards]; notes.push("Hazard class taken from DEMO-UN-SEED (demo_seed) — confirm against transport documents/SDS."); } }
      else notes.push(`${un} not found in loaded data — hazards cannot be inferred from the UN number.`);
    }
    const identified = !!hc && !!(un || d.chemical_name);
    const hz = [...(hc ? [hc] : []), ...subs];
    const q = d.quantity_estimate, f = (k) => !!d[k], trained = f("trained_responders_available");
    const trig = [];
    if (!identified) trig.push("Material unidentified or hazard class unknown");
    if (f("fire")) trig.push("Fire present or imminent");
    if (f("injuries_or_exposure")) trig.push("Injury or personnel exposure");
    if (f("vapour_release") || hz.includes("2.3")) trig.push("Toxic/flammable vapour or gas release");
    if (hz.some((h) => ["1", "1.1", "1.2", "1.3", "1.4", "1.5", "1.6", "6.2", "7", "5.2"].includes(h))) trig.push("Explosive, infectious, radioactive or organic peroxide material");
    if (f("waterway_nearby")) trig.push("Waterway / environmental receptor at risk");
    if (f("pressure_receptacle_involved")) trig.push("Pressure receptacle involved");
    if (q === null || q === undefined || q === "") trig.push("Quantity unknown");
    else if (Number(q) >= threshold) trig.push(`Quantity ≥ ${threshold} (site threshold)`);
    if (!trained) trig.push("No trained hazmat responders available on site");
    const immediate = ["Protect life first: raise the alarm and warn people nearby.",
      "Isolate the area, establish a cordon upwind/uphill, and prevent unauthorised entry.",
      "Do not touch, walk through or attempt to identify the material by smell or contact.",
      "Notify the designated site emergency response team / incident controller.",
      "Eliminate ignition sources only if this can be done without entering the hazard area.",
      "Decide evacuation or shelter-in-place with the incident controller based on wind direction, vapour release and the emergency response guidance for the material."];
    if (trig.length) immediate.splice(3, 0, "Call external emergency services now (escalation trigger(s) present).");
    if (!identified) immediate.push("Treat as UNKNOWN and potentially severe: maximise distance, stay upwind, await specialist assessment. No containment or cleanup by site personnel.");
    if (f("injuries_or_exposure")) immediate.push("Move casualties to fresh air only if rescuers are not exposed; obtain medical help; follow SDS Section 4 first aid.");
    const key = (h) => (h in PROFILES ? h : h.split(".")[0]);
    const hazards = hz.filter((h) => key(h) in PROFILES).map((h) => ({ hazard: h, name: PROFILES[key(h)][0], considerations: PROFILES[key(h)][1], role: h === hc ? "primary" : "subsidiary" }));
    if (f("drains_nearby") || f("waterway_nearby") || hz.includes("9")) hazards.push({ hazard: "ENV", name: "Environmental", considerations: ["Risk of release to drains/waterways — protect drains only if it can be done safely and with compatible materials."] });
    const precautions = [...new Set(hz.flatMap((h) => PRECAUTIONS[h] || PRECAUTIONS[h.split(".")[0]] || []))].sort();
    const containment = !identified ? ["WITHHELD: material not identified. No containment or cleanup by site personnel."]
      : !trained ? ["WITHHELD: no trained responders. Isolate and await the emergency response team."]
      : ["Containment/cleanup method: select ONLY from SDS Section 6 and verified emergency guidance, after confirming compatibility of absorbents/booms/neutralisers with the material.", "Not recommended automatically by this system: water, absorbents, neutralising chemicals."];
    return { response_level: trig.length ? "MAJOR — ESCALATE TO EXTERNAL EMERGENCY SERVICES / SPECIALIST HAZMAT RESPONSE" : "SITE EMERGENCY RESPONSE TEAM — SUPERVISED RESPONSE PER APPROVED SITE ERP",
      escalation_triggers: trig, identified, material: { un_number: un, hazard_class: hc, subsidiary_hazards: subs, proper_shipping_name: entry?.proper_shipping_name },
      immediate_priorities: immediate, hazard_assessment: hazards, incompatible_material_groups: groupsFor({ hazard_class: hc, subsidiary_hazards: subs, name: d.chemical_name, proper_shipping_name: entry?.proper_shipping_name }),
      precautions_do_not: precautions,
      response_references: ["SDS Section 4 (first aid), 5 (fire-fighting), 6 (accidental release), 8 (exposure controls/PPE), 10 (stability/reactivity), 13 (disposal)" + (f("sds_available") ? "" : " — SDS NOT AVAILABLE: obtain urgently"),
        "IMDG EmS / transport emergency guidance: NOT LOADED for this material — consult the official publication", "Approved site Emergency Response Plan and the incident controller's instructions",
        "Initial isolation / protective action distances: use the applicable official emergency response guide adopted in your jurisdiction (not loaded in this system)"],
      containment, ppe: "Select from SDS Section 8 and the emergency guidance, by a competent person, matched to the substance, concentration and exposure. Respiratory protection only by trained, fit-tested personnel. This system does not specify PPE without verified substance data.",
      medical: ["Follow SDS Section 4; provide SDS to medical personnel.", "Record all persons potentially exposed (name, duration, route) for medical surveillance.", "Decontaminate casualties per SDS and medical advice before transport where safe.", "Report occupational exposure/injury per local legal requirements."],
      notifications: ["Site incident controller / HSE manager", "Port / terminal authority (if in port area)", "Environmental regulator if release to drains, soil or water", "Carrier / shipper / consignee and DGSA", "Competent authority reporting of dangerous goods incidents as required by applicable regulations"],
      data_notes: notes, evidence: ev,
      limitations: ["Decision support only. Does not replace the approved site ERP, the SDS, emergency services or specialist responders.", "Untrained personnel must not enter hazardous atmospheres or attempt cleanup.", "Hazard considerations are generic for the hazard class and must be confirmed against substance-specific data."] };
  }

  return { verify, identify, segregate, screen, spill, normalizeUN, casOK, psnAlternatives, ratio, ENTRIES, NOT_VERIFIED };
})();
if (typeof module !== "undefined") module.exports = E;
