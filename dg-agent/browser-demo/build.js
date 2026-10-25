// Inlines data + engine, transpiles the two module scripts to ES2018 for older browsers.
const fs = require('fs'); const esbuild = require('esbuild');
const html = fs.readFileSync('ui.html', 'utf8');
const data = fs.readFileSync('data.js', 'utf8'), engine = fs.readFileSync('engine.js', 'utf8');
const t = (code) => esbuild.transformSync(code, { target: 'es2018', loader: 'js' }).code;
let out = html.replace('/*__DATA__*/\n/*__ENGINE__*/', () => data + t(engine));
const i = out.lastIndexOf('<script>'), j = out.lastIndexOf('</script>');
out = out.slice(0, i + 8) + '\n' + t(out.slice(i + 8, j)) + out.slice(j);
fs.writeFileSync('dg-compliance-assistant.html', out);
console.log('built', out.length, 'bytes; ?? left:', (out.match(/\?\?/g) || []).length, '?. left:', (out.match(/\?\.[a-zA-Z_(\[]/g) || []).length, 'matchAll:', out.includes('matchAll'));
