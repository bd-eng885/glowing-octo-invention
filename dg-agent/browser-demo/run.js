const fs=require('fs'); eval(fs.readFileSync('data.js','utf8').replace('const DATA','global.DATA')); const E=require('./engine.js');
const c=JSON.parse(fs.readFileSync('cases.json'));
const out={verify:c.verify.map(([m,d])=>{const r=E.verify(d,m);return [r.status,r.provisional_status,(r.checks||[]).map(x=>[x.field,x.result,x.message]),r.matched_entry?.un_number??null]}),
identify:c.identify.map(a=>{const r=E.identify({name:a.name,un:a.un,cas:a.cas,text:a.text});return [r.overall.category,r.candidates.map(x=>[x.entry.un_number,x.confidence]),r.unmatched_un_numbers,r.notes]}),
seg:c.seg.map(([m,a,i])=>{const r=E.segregate(i,m,a);return [r.decision,r.pairs.map(p=>[p.a,p.b,p.status,p.code,p.issues,p.conditions]),r.notes,r.missing_information]}),
spill:c.spill.map(d=>{const r=E.spill(d);return [r.response_level,r.escalation_triggers,r.immediate_priorities,r.hazard_assessment,r.precautions_do_not,r.containment,r.incompatible_material_groups,r.data_notes]})};
fs.writeFileSync('js_out.json',JSON.stringify(out));
