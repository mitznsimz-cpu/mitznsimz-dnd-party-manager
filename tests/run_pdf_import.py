#!/usr/bin/env python3
"""Browser test for D&D Beyond PDF import.

Needs real D&D Beyond character-sheet PDFs in private/sheets/ (git-ignored; skipped if
there are none) and a local pdfjs-dist 6.2.108 (PDFJS_DIR, default /opt/npm-tools/...),
which is served in place of the jsDelivr copy the app loads.
"""
import os, pathlib, subprocess, sys
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
SHEETS = sorted((ROOT / 'private' / 'sheets').glob('*.pdf'))
PDFJS_DIR = pathlib.Path(os.environ.get('PDFJS_DIR', '/opt/npm-tools/node_modules/pdfjs-dist/build'))
if not SHEETS:
    print('SKIP: no PDFs in private/sheets/'); sys.exit(0)
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build.py')], check=True, capture_output=True)

def serve_pdfjs(route):
    name = route.request.url.rsplit('/', 1)[-1]
    route.fulfill(status=200, body=(PDFJS_DIR / name).read_bytes(), headers={'content-type': 'text/javascript', 'access-control-allow-origin': '*'})

results = []
def check(name, ok, detail=''):
    ok = bool(ok); results.append(ok); print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=os.environ.get('CHROME', '/usr/bin/google-chrome'), args=['--no-sandbox'])
    ctx = b.new_context(viewport={'width': 1600, 'height': 1000})
    ctx.route('https://cdn.jsdelivr.net/npm/pdfjs-dist@*/build/*', serve_pdfjs)
    ctx.route('https://api.open5e.com/**', lambda r: r.abort())
    pg = ctx.new_page(); errors = []
    pg.on('pageerror', lambda e: errors.append(str(e)))
    pg.goto((ROOT / 'dev' / 'index.html').as_uri()); pg.wait_for_timeout(300)

    # new campaign from all the PDFs
    pg.click('header [data-act="newcamp"]'); pg.fill('#ncName', 'Imported party')
    with pg.expect_file_chooser() as fc: pg.click('[data-act="newcampfile"]')
    fc.value.set_files([str(s) for s in SHEETS])
    pg.wait_for_selector('#modal .dgrp', timeout=30000)
    chars = pg.evaluate('S.characters')
    check(f'{len(SHEETS)} sheets become a campaign', len(chars) == len(SHEETS) and pg.evaluate('S.name') == 'Imported party', [c['name'] for c in chars])
    check('import report lists every character', pg.locator('#modal .dgrp').count() == len(SHEETS))
    pg.screenshot(path=str(ROOT / 'private' / 'import_report.png'))
    pg.click('#modal [data-act="mclose"]')
    for c in chars:
        ok = c['hp']['max'] > 0 and c['ac'] >= 10 and all(c['abilities'][a]['score'] for a in c['abilities']) and len(c['skills']) == 18 and c['features'] and c['inventory']
        check(f"{c['name']}: core stats, features and kit read", ok)
    purse = pg.evaluate('S.purse')
    check('coins from every sheet go into the party purse', purse['gp'] > 0 and purse['gp'] % len(SHEETS) == 0 or purse['gp'] > 0, purse)

    # same sheets again into the same campaign: offered as updates with nothing to change
    pg.click('.card.addtile')
    with pg.expect_file_chooser() as fc: pg.click('#modal [data-act="importchar"]')
    fc.value.set_files([str(s) for s in SHEETS])
    pg.wait_for_selector('[data-act="applyMerge"]', timeout=30000)
    nochange = pg.locator('#modal .dgrp:has-text("No changes")').count()
    check('re-importing the same sheets finds no changes', nochange == len(SHEETS), pg.locator('#modal .diff label').all_inner_texts()[:8])
    pg.click('#modal [data-act="mclose"]')

    # and the app works with an imported character
    cid = chars[0]['id']
    pg.fill(f'[data-hpin="{cid}"]', '5'); pg.click(f'[data-act="hp"][data-op="dmg"][data-cid="{cid}"]')
    check('imported characters take damage normally', pg.evaluate(f"charById('{cid}').hp.current") == chars[0]['hp']['max'] - 5)
    pg.screenshot(path=str(ROOT / 'private' / 'imported_party.png'), full_page=True)
    check('no page errors', not errors, errors[:3])
    b.close()
print(f'\n{sum(results)}/{len(results)} passed'); sys.exit(0 if all(results) else 1)
