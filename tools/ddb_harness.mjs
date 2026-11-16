// Run the app's D&D Beyond parser on PDFs from the command line (for development).
//   node tools/ddb_harness.mjs private/sheets/*.pdf > private/parsed.json
// Needs pdfjs-dist (PDFJS, default /opt/npm-tools/node_modules/pdfjs-dist/legacy/build/pdf.mjs).
import fs from 'fs';
import path from 'path';
import {fileURLToPath} from 'url';
const pdfjs = await import(process.env.PDFJS || '/opt/npm-tools/node_modules/pdfjs-dist/legacy/build/pdf.mjs');
const src = fs.readFileSync(path.join(path.dirname(fileURLToPath(import.meta.url)), '..', 'src', 'party_manager.html'), 'utf8');
const DDB = new Function(src.slice(src.indexOf('/* DDB-PARSER START */'), src.indexOf('/* DDB-PARSER END */')) + '\nreturn DDB;')();
const out = {};
for (const file of process.argv.slice(2)){
  const task = pdfjs.getDocument({data: new Uint8Array(fs.readFileSync(file)), verbosity: 0});
  const doc = await task.promise, pages = [];
  for (let p = 1; p <= doc.numPages; p++){
    const an = await (await doc.getPage(p)).getAnnotations();
    pages.push({widgets: an.filter(a => a.subtype === 'Widget').map(a => ({name: a.fieldName || '', value: a.fieldValue}))});
  }
  task.destroy();
  const r = DDB.parse(pages); out[r.character.id] = r;
  console.error(`${r.character.name}: ${r.character.features.length} features, ${r.character.spells.length} spells, ${r.character.inventory.length} items, ${r.warnings.length} notes`);
}
console.log(JSON.stringify(out, null, 1));
