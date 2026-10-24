const { chromium } = require('playwright');
// UI smoke test (Playwright). Usage: node ui_smoke.js  (env BASE_URL, DEMO_USERS_PASSWORD; run make_docs.py first)
const BASE = process.env.BASE_URL || 'http://127.0.0.1:5173';
const PW = process.env.DEMO_USERS_PASSWORD || 'choose-a-password';
const ROUTES = ['/', '/identify', '/verify', '/imdg', '/iata', '/segregation', '/compat', '/sds', '/spill', '/erp', '/inspection', '/risk', '/reports', '/sources', '/users'];
const out = []; const R = (k, v) => { out.push(`${v ? 'PASS' : 'FAIL'}  ${k}`); };
async function login(b, who, vp = { width: 1360, height: 900 }) {
  const p = await b.newPage({ viewport: vp, acceptDownloads: true });
  p.errs = []; p.on('pageerror', e => p.errs.push('pageerror: ' + e.message));
  p.on('response', r => { if (r.status() >= 500) p.errs.push(`HTTP ${r.status()} ${r.url()}`); });
  await p.goto('' + BASE + '/');
  await p.fill('input[autocomplete=username]', `${who}@demo.local`);
  await p.fill('input[type=password]', PW);
  await p.click('button[type=submit]');
  await p.waitForSelector('.tiles', { timeout: 10000 });
  return p;
}
(async () => {
  const b = await chromium.launch();
  // wrong password
  const x = await b.newPage(); await x.goto('' + BASE + '/');
  await x.fill('input[autocomplete=username]', 'operator@demo.local'); await x.fill('input[type=password]', 'wrong'); await x.click('button[type=submit]');
  R('login rejects wrong password', await x.waitForSelector('.alert.bad', { timeout: 5000 }).then(() => true).catch(() => false));
  const p = await login(b, 'admin');
  R('login (admin) shows dashboard', true);
  for (const r of ROUTES) {
    await p.goto('' + BASE + '/#' + r); await p.waitForTimeout(350);
    const ok = await p.$('main .card, main .tiles');
    R(`navigate ${r} renders`, !!ok);
  }
  R('no page errors / 5xx during admin navigation', p.errs.length === 0); if (p.errs.length) console.log(p.errs);
  await p.close();

  const o = await login(b, 'operator');
  R('operator: Users nav hidden', !(await o.$('nav a[href="#/users"]')));
  // file upload through UI
  await o.goto('' + BASE + '/#/sds');
  await o.setInputFiles('input[type=file]', 'sds_text.pdf');
  await o.click('button:has-text("Upload")');
  R('SDS PDF upload via UI extracts UN1992', await o.waitForSelector('text=Verify UN1992', { timeout: 15000 }).then(() => true).catch(() => false));
  await o.click('text=Verify UN1992');
  R('SDS → verify prefill carries PSN', (await o.inputValue('.card .grid input >> nth=1')).startsWith('FLAMMABLE LIQUID'));
  await o.click('button:has-text("Run check")');
  R('verification result shows NOT VERIFIED', await o.waitForSelector('text=NOT VERIFIED — HUMAN REVIEW REQUIRED', { timeout: 8000 }).then(() => true).catch(() => false));
  // inspection with photo
  await o.goto('' + BASE + '/#/inspection'); await o.waitForSelector('table.edit');
  await o.setInputFiles('input[type=file][multiple]', 'scan.png'); await o.waitForSelector('text=Uploaded: #', { timeout: 10000 });
  await o.selectOption('table.edit tbody tr:nth-child(6) select >> nth=0', 'nonconformity');
  await o.click('button:has-text("Run check")');
  R('inspection with leak → STOP', await o.waitForSelector('text=STOP — QUARANTINE', { timeout: 8000 }).then(() => true).catch(() => false));
  // ERP generate + save + export via UI
  await o.goto('' + BASE + '/#/erp'); await o.waitForTimeout(400);
  await o.check('.save-row input[type=checkbox]'); await o.click('button:has-text("Generate")');
  R('ERP generated (18 sections)', (await o.waitForSelector('text=18. Regulatory references', { timeout: 8000 }).then(() => true).catch(() => false)));
  await o.goto('' + BASE + '/#/reports'); await o.waitForSelector('.clickable'); await o.click('.clickable >> nth=0');
  for (const f of ['PDF', 'DOCX', 'XLSX', 'CSV']) {
    const dl = o.waitForEvent('download', { timeout: 8000 }); await o.click(`button:has-text("Export ${f}")`);
    const d = await dl.catch(() => null); R(`UI export ${f} downloads`, !!d && d.suggestedFilename().endsWith(f.toLowerCase()));
  }
  R('operator: audit panel hidden', !(await o.$('text=Audit trail (tamper-evident')));
  await o.click('button:has-text("Submit for review")'); await o.waitForTimeout(400);
  await o.click('button:has-text("Approve")'); 
  R('operator approve → refused message', await o.waitForSelector("text=not authorised to approve", { timeout: 5000 }).then(() => true).catch(() => false));
  R('no page errors / 5xx during operator flows', o.errs.length === 0); if (o.errs.length) console.log(o.errs);
  // Arabic
  await o.click('button:has-text("العربية")'); await o.waitForTimeout(300);
  R('Arabic: <html dir=rtl lang=ar>', (await o.getAttribute('html', 'dir')) === 'rtl' && (await o.getAttribute('html', 'lang')) === 'ar');
  const navAr = await o.$$eval('nav a', as => as.filter(a => /[؀-ۿ]/.test(a.textContent)).length + '/' + as.length);
  R('Arabic: nav labels translated ' + navAr, navAr.split('/')[0] === navAr.split('/')[1]);
  await o.goto('' + BASE + '/#/spill'); await o.waitForTimeout(300);
  const labels = await o.$$eval('main label.field > span, main label.check', ls => { const a = ls.filter(l => /[؀-ۿ]/.test(l.textContent)).length; return a + '/' + ls.length; });
  console.log('INFO  Arabic: spill page form labels translated ' + labels);
  await o.screenshot({ path: 'ar-spill.png' });
  await o.click('button:has-text("English")'); R('English restored dir=ltr', (await o.getAttribute('html', 'dir')) === 'ltr');
  // approver approves
  const a = await login(b, 'approver'); await a.goto('' + BASE + '/#/reports'); await a.waitForSelector('.clickable');
  await a.click('.clickable:has-text("PENDING") >> nth=0'); await a.fill('input[placeholder=Comment]', 'Reviewed in E2E');
  await a.click('button:has-text("Approve")');
  R('approver approves pending report', await a.waitForSelector('.card-head:has-text("APPROVED")', { timeout: 5000 }).then(() => true).catch(() => false));
  R('approver sees audit trail', !!(await a.$('text=Audit trail (tamper-evident')));
  await a.click('button:has-text("Verify hash chain")'); R('audit chain valid in UI', await a.waitForSelector('text=Chain valid', { timeout: 5000 }).then(() => true).catch(() => false));
  // viewer
  const v = await login(b, 'viewer'); await v.goto('' + BASE + '/#/verify'); await v.fill('input[placeholder=UN1203]', 'UN1090');
  await v.click('button:has-text("Run check")'); R('viewer analysis refused (403 shown)', await v.waitForSelector('text=not authorised', { timeout: 5000 }).then(() => true).catch(() => false));
  // mobile
  const m = await login(b, 'operator', { width: 390, height: 844 });
  const sw = await m.evaluate(() => document.documentElement.scrollWidth); R(`mobile 390px: no horizontal page scroll (scrollWidth ${sw})`, sw <= 390);
  await m.click('.menu-btn'); await m.click('nav >> text=Spill Response Assistant'); R('mobile menu navigates', !!(await m.waitForSelector('text=In an emergency', { timeout: 5000 }).catch(() => null)));
  console.log(out.join('\n')); await b.close();
})();
