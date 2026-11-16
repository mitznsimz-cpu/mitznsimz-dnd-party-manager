#!/usr/bin/env python3
"""End-to-end browser tests for the Party Manager.

Builds a temporary copy seeded with tests/fixtures/party.json (an anonymised party)
and drives it in headless Chrome with Playwright. Open5e is blocked, so lookups
exercise their offline paths.

    python3 tests/run_e2e.py            # all checks
    CHROME=/path/to/chrome python3 tests/run_e2e.py

Exit code is non-zero if any check fails.
"""
import copy, json, os, pathlib, subprocess, sys, tempfile
from playwright.sync_api import sync_playwright

ROOT = pathlib.Path(__file__).resolve().parent.parent
FIX = ROOT / 'tests' / 'fixtures' / 'party.json'
TMP = pathlib.Path(tempfile.mkdtemp(prefix='pm-e2e-'))
SEEDED = TMP / 'seeded.html'
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build.py'), '--seed', str(FIX), '--out', str(SEEDED)], check=True, capture_output=True)
subprocess.run([sys.executable, str(ROOT / 'tools' / 'build.py')], check=True, capture_output=True)

# A level-up file for the rogue: level 8, more HP, DEX 20, Shield, an ASI feature, one item swapped.
party = json.loads(FIX.read_text())
rogue = copy.deepcopy(next(c for c in party['characters'] if c['id'] == 'lira-swiftwind'))
rogue['level'] = 8; rogue['classes'][0]['level'] = 8; rogue['xp'] = 34000; rogue['hp']['max'] = 79
rogue['abilities']['dex'].update(score=20, mod=5, save=9); rogue['skills']['stealth']['mod'] = 11
rogue['spells'].append({"name": "Shield", "level": 1, "source": "Rogue", "alwaysPrepared": False, "saveAtk": "--", "time": "1R", "range": "Self",
                        "components": "V,S", "duration": "1 round", "concentration": False, "ritual": False, "ref": "PHB 275", "notes": ""})
rogue['features'].append({"id": "asi-8", "name": "Ability Score Improvement", "src": "Rogue", "act": "passive", "text": "+2 DEX"})
rogue['inventory'] = [i for i in rogue['inventory'] if i['name'] != 'Bell'] + [{"name": "Potion of Healing", "qty": 2, "weight": None, "attuned": False, "magic": True, "consumable": True}]
LEVELUP = TMP / 'rogue_l8.json'; LEVELUP.write_text(json.dumps(rogue))

results = []
def check(name, ok, detail=''):
    results.append((name, bool(ok), detail)); print(('PASS ' if ok else 'FAIL ') + name + (f'  [{detail}]' if detail and not ok else ''))

FIGHTER, ROGUE, BARD, CLERIC = 'brand-ashcroft', 'lira-swiftwind', 'tilly-merrowbuck', 'dorn-ironmantle'

with sync_playwright() as pw:
    b = pw.chromium.launch(executable_path=os.environ.get('CHROME', '/usr/bin/google-chrome'), args=['--no-sandbox'])
    errors = []

    def page(width=1600, height=1000):
        ctx = b.new_context(viewport={'width': width, 'height': height}, accept_downloads=True)
        pg = ctx.new_page()
        pg.on('pageerror', lambda e: errors.append(str(e)))
        pg.route('https://api.open5e.com/**', lambda r: r.abort())
        return pg
    ev = lambda pg, js: pg.evaluate(js)

    # ---- production build boots empty
    pg = page(); pg.goto((ROOT / 'index.html').as_uri()); pg.wait_for_timeout(300)
    check('prod build opens on an empty campaigns page', ev(pg, 'VIEW') == 'home' and ev(pg, 'IDX.list.length') == 0)
    check('prod build uses the production storage namespace', ev(pg, 'STORAGE_NS') == '')
    pg.context.close()

    # ---- seeded build: core table play
    pg = page(); pg.goto(SEEDED.as_uri()); pg.wait_for_timeout(300)
    check('seed becomes the first campaign', ev(pg, 'VIEW') == 'party' and ev(pg, 'S.characters.length') == 4)
    check('party purse is the sum of the four shares', ev(pg, 'S.purse.gp') == 2528, ev(pg, 'S.purse'))
    ev(pg, "UI.sbMode='below'; renderAll()")

    pg.click(f'.card[data-cid="{CLERIC}"] [data-act="toggle"]')
    pg.click(f'.card[data-cid="{CLERIC}"] .sb [data-act="spellview"][data-v="all"]')
    pg.click(f'.card[data-cid="{CLERIC}"] .li:has-text("Spirit Guardians") [data-act="prep"]')
    pg.click(f'.card[data-cid="{CLERIC}"] .li:has-text("Spirit Guardians") [data-act="cast"]')
    pg.click('#modal [data-act="docast"][data-lvl="3"]')
    c = ev(pg, f"charById('{CLERIC}')")
    check('casting uses the chosen slot and sets concentration', c['concentration'] == 'Spirit Guardians' and next(s for s in c['spellSlots'] if s['level'] == 3)['used'] == 1)
    pg.fill(f'[data-hpin="{CLERIC}"]', '24'); pg.click(f'[data-act="hp"][data-op="dmg"][data-cid="{CLERIC}"]')
    check('damage applies', ev(pg, f"charById('{CLERIC}').hp.current") == 67)
    check('concentration check prompt shows', 'DC 12' in pg.inner_text('#toasts'))

    pg.fill(f'[data-hpin="{BARD}"]', '80'); pg.press(f'[data-hpin="{BARD}"]', 'Enter')
    c = ev(pg, f"charById('{BARD}')")
    check('dropping to 0 adds Unconscious', c['hp']['current'] == 0 and 'Unconscious' in c['conditions'])
    pg.fill(f'[data-hpin="{BARD}"]', '5'); pg.click(f'[data-act="hp"][data-op="heal"][data-cid="{BARD}"]')
    check('healing from 0 clears Unconscious', 'Unconscious' not in ev(pg, f"charById('{BARD}').conditions"))

    pg.click(f'.card[data-cid="{FIGHTER}"] .uses [data-kind="res"][data-ref="action-surge"]')
    check('tapping a pip spends one use', ev(pg, f"resById(charById('{FIGHTER}'),'action-surge').used") == 1)
    pg.click(f'.card[data-cid="{BARD}"] .uses [data-kind="res"][data-ref="bardic-inspiration"] >> nth=0')
    check('tapping the first of four pips spends only one', ev(pg, f"resById(charById('{BARD}'),'bardic-inspiration').used") == 1)
    ev(pg, f"charById('{FIGHTER}').hp.current = 60")
    pg.click(f'.card[data-cid="{FIGHTER}"] .chip[data-fid="second-wind"]'); pg.fill('#effRoll', '7'); pg.click('#modal [data-act="usefeat"]')
    check('Second Wind heals roll + level and spends its use', ev(pg, f"[charById('{FIGHTER}').hp.current, resById(charById('{FIGHTER}'),'second-wind').used]") == [73, 1])
    pg.click('#undoBtn')
    check('undo reverts the last action', ev(pg, f"resById(charById('{FIGHTER}'),'second-wind').used") == 0)

    pg.click('header [data-act="shortRest"]'); pg.click('[data-act="doShort"]')
    check('short rest resets short-rest uses', ev(pg, f"resById(charById('{FIGHTER}'),'action-surge').used") == 0)
    pg.click('header [data-act="longRest"]'); pg.click('[data-act="doLong"]')
    check('long rest restores HP, slots and drops concentration', ev(pg, f"[charById('{CLERIC}').hp.current, charById('{CLERIC}').spellSlots.every(s=>!s.used), charById('{CLERIC}').concentration]") == [91, True, None])

    pg.click('header [data-act="journal"]'); pg.click(f'#modal [data-act="jtag"][data-cid="{BARD}"]'); pg.fill('#jround', '3')
    pg.fill('#jtext', 'Tilly drops to 0 shielding the cleric.'); pg.check('#jstar'); pg.click('[data-act="jadd"]')
    md = ev(pg, 'markdownLog()')
    check('journal entry exports to markdown with round, star and name', '★ **Round 3.** *Tilly Merrowbuck:*' in md, md[:200])
    pg.keyboard.press('Escape')

    # ---- homebrew editing and merge protection
    pg.click(f'.card[data-cid="{ROGUE}"] [data-act="toggle"]')
    pg.click(f'.card[data-cid="{ROGUE}"] .addrow [data-act="addfeat"][data-v="bonus"]')
    pg.fill('#ff_name', 'Shadow Step'); pg.fill('#ff_text', 'Teleport between shadows.'); pg.select_option('#ff_res', '__new'); pg.fill('#ff_newMax', '2')
    pg.click('#modal [data-act="formsave"]')
    check('homebrew bonus action appears on the card', 'Shadow Step' in ' '.join(pg.locator(f'.card[data-cid="{ROGUE}"] .chip.act-bonus').all_inner_texts()))
    pg.click(f'.card[data-cid="{ROGUE}"] .en[data-fid="sneak-attack"]'); pg.click('#modal [data-act="editfeat"]'); pg.fill('#ff_text', 'EDITED'); pg.click('#modal [data-act="formsave"]')
    pg.click(f'.card[data-cid="{ROGUE}"] .sh[data-k="inventory"]')
    pg.click(f'.card[data-cid="{ROGUE}"] [data-act="additemfull"]'); pg.fill('#ff_name', 'Cloak of the Night Market'); pg.fill('#ff_desc', 'Homebrew cloak.'); pg.click('#modal [data-act="formsave"]')
    ev(pg, "jsonMode='merge'"); pg.set_input_files('#fileJson', str(LEVELUP)); pg.wait_for_timeout(300)
    labels = pg.locator('#modal label').all_inner_texts()
    check('merge does not offer to remove your homebrew', not any('Shadow Step' in l or 'Cloak of the Night' in l for l in labels))
    sneak = ev(pg, "[...document.querySelectorAll('#modal label')].filter(l=>l.textContent.includes('Sneak Attack')).map(l=>l.querySelector('input').checked)")
    check('sheet change to an edited feature starts unticked', sneak == [] or sneak == [False], sneak)
    pg.click('[data-act="applyMerge"]')
    c = ev(pg, f"charById('{ROGUE}')")
    check('level-up merge applied', c['level'] == 8 and c['hp']['max'] == 79 and any(s['name'] == 'Shield' for s in c['spells']))
    check('homebrew survives the merge', any(f['name'] == 'Shadow Step' for f in c['features']) and any(i['name'] == 'Cloak of the Night Market' for i in c['inventory']))
    check('item removals default off (Bell kept)', any(i['name'] == 'Bell' for i in c['inventory']))

    # ---- campaigns and characters
    pg.click('[data-act="home"]'); pg.click('header [data-act="newcamp"]'); pg.fill('#ncName', 'One-shot')
    pg.click('#modal label:has-text("Tilly Merrowbuck") input'); pg.click('[data-act="docreatecamp"]'); pg.wait_for_timeout(200)
    check('new campaign with a copied character', ev(pg, 'S.name') == 'One-shot' and ev(pg, 'S.characters.map(c=>c.name)') == ['Tilly Merrowbuck'])
    check('copied character starts fresh', ev(pg, f"charById('{BARD}').hp.current") == 70 and ev(pg, f"resById(charById('{BARD}'),'bardic-inspiration').used") == 0)
    pg.click('.card.addtile'); pg.click('#modal [data-act="newchar"]')
    pg.fill('#ff_name', 'Brakka'); pg.fill('#ff_c1', 'Barbarian'); pg.fill('#ff_l1', '5'); pg.fill('#ff_hpmax', '55'); pg.fill('#ff_ac', '15')
    for a, v in zip(['str', 'dex', 'con', 'int', 'wis', 'cha'], [18, 14, 16, 8, 12, 10]): pg.fill(f'#ff_ab_{a}', str(v))
    pg.check('#ff_sp_str'); pg.select_option('#ff_sk_intimidation', 'expert')
    pg.click('#modal [data-act="savechar"]'); pg.wait_for_timeout(200)
    br = ev(pg, "S.characters.find(c=>c.name==='Brakka')")
    check('new-character form works out saves, skills and initiative', br and br['abilities']['str']['save'] == 7 and br['skills']['intimidation']['mod'] == 6 and br['initiative'] == 2, br and (br['abilities']['str'], br['skills']['intimidation']))
    pg.click(f'.card[data-cid="{BARD}"] [data-act="charmenu"]'); pg.click('#modal [data-act="removechar"]'); pg.click('#undoBtn')
    check('remove character can be undone', ev(pg, 'S.characters.length') == 2)
    pg.click('[data-act="home"]'); one = ev(pg, "IDX.list.find(e=>e.name==='One-shot').id")
    pg.click(f'[data-act="campdel"][data-id="{one}"]'); pg.click(f'[data-act="camprestore"][data-id="{one}"]')
    check('deleted campaign can be restored', not ev(pg, f"campById('{one}').deleted"))
    pg.click('.ccard:has-text("Test Party") [data-act="campopen"]'); pg.wait_for_timeout(100)
    check('first campaign untouched by the second', ev(pg, f"charById('{ROGUE}').level") == 8 and ev(pg, 'S.characters.length') == 4)
    pg.reload(); pg.wait_for_timeout(300)
    check('reload reopens the last campaign', ev(pg, 'VIEW') == 'party' and ev(pg, 'S.name') == 'Test Party')

    # ---- layout
    ev(pg, "UI.sbMode='auto'; S.characters.forEach(c=>UI.open[c.id]=false); UI.open['" + FIGHTER + "']=true; renderAll()")
    check('stat blocks open in the side panel on wide screens', pg.locator('#dock .dblk').count() == 1 and pg.locator('#grid .sb').count() == 0)
    pg.set_viewport_size({'width': 900, 'height': 800}); pg.wait_for_timeout(200)
    check('and below the card on narrow screens', pg.locator('#grid .sb').count() == 1)
    pg.context.close()

    check('no page errors', not errors, errors[:3])
    b.close()

failed = [r for r in results if not r[1]]
print(f'\n{len(results) - len(failed)}/{len(results)} passed')
sys.exit(1 if failed else 0)
