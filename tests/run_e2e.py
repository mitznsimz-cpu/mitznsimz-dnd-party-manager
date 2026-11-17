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

    # ---- reordering cards (buttons and drag, as in the tracker)
    order = lambda: ev(pg, 'S.characters.map(c=>c.id)')
    start = order()
    check('first card cannot move earlier', pg.locator(f'.card[data-cid="{start[0]}"] [data-act="movechar"][data-d="-1"]').is_disabled())
    pg.click(f'.card[data-cid="{start[0]}"] [data-act="movechar"][data-d="1"]')
    check('move button swaps with the neighbour', order() == [start[1], start[0]] + start[2:], order())
    pg.click('#undoBtn')
    check('reorder can be undone', order() == start)
    src = pg.locator(f'.card[data-cid="{start[3]}"] [data-drag]'); dst = pg.locator(f'.card[data-cid="{start[0]}"]')
    box = dst.bounding_box()
    src.drag_to(dst, target_position={'x': 10, 'y': box['height'] / 2})
    check('dragging onto the left half of a card drops it before', order() == [start[3]] + start[:3], order())
    src = pg.locator(f'.card[data-cid="{start[3]}"] [data-drag]'); dst = pg.locator(f'.card[data-cid="{start[2]}"]')
    box = dst.bounding_box()
    src.drag_to(dst, target_position={'x': box['width'] - 10, 'y': box['height'] / 2})
    check('dragging onto the right half drops it after', order() == start, order())
    pg.click(f'.card[data-cid="{start[1]}"] [data-act="movechar"][data-d="-1"]')
    pg.wait_for_timeout(250); pg.reload(); pg.wait_for_timeout(300); ev(pg, "UI.sbMode='below'; renderAll()")
    check('new order is saved', order() == [start[1], start[0]] + start[2:], order())
    pg.click(f'.card[data-cid="{start[1]}"] [data-act="movechar"][data-d="1"]')

    # ---- floating journal: stays open while you use the sheets
    pg.click('header [data-act="journal"]'); pg.wait_for_selector('#journal:not([hidden]) #jtext')
    pg.click(f'#journal [data-act="jtag"][data-cid="{BARD}"]'); pg.fill('#jround', '3')
    pg.fill('#jtext', 'Tilly drops to 0 shielding the cleric.'); pg.check('#jstar'); pg.click('#journal [data-act="jadd"]')
    md = ev(pg, 'markdownLog()')
    check('journal entry exports to markdown with round, star and name', '★ **Round 3.** *Tilly Merrowbuck:*' in md, md[:200])
    pg.fill('#jtext', 'half-typed note')
    pg.fill(f'[data-hpin="{FIGHTER}"]', '3'); pg.click(f'[data-act="hp"][data-op="dmg"][data-cid="{FIGHTER}"]')
    check('journal stays open while using the cards', pg.is_visible('#journal') and ev(pg, f"charById('{FIGHTER}').hp.current") == 86)
    check('text being typed survives other changes', pg.input_value('#jtext') == 'half-typed note')
    pg.fill('#jtext', '')
    box = pg.locator('#journal .jhead').bounding_box()
    pg.mouse.move(box['x'] + 60, box['y'] + 12); pg.mouse.down(); pg.mouse.move(box['x'] - 300, box['y'] - 200, steps=6); pg.mouse.up()
    moved = pg.locator('#journal').bounding_box()
    check('journal can be dragged by its header', abs(moved['x'] - (box['x'] - 360)) < 20, (box, moved))
    pg.click('#journal [data-act="jclose"]')

    # ---- reference pop-ups float and can be moved
    ev(pg, f"UI.open['{CLERIC}'] = true; renderAll()")
    pg.click(f'.card[data-cid="{CLERIC}"] .sb .nm[data-sid="bless-cleric"]'); pg.wait_for_selector('#scrim.open.float')
    pg.fill(f'[data-hpin="{FIGHTER}"]', '1'); pg.click(f'[data-act="hp"][data-op="heal"][data-cid="{FIGHTER}"]')
    check('a spell pop-up does not block the page', pg.is_visible('#modal') and ev(pg, f"charById('{FIGHTER}').hp.current") == 87)
    hb = pg.locator('#modal .mhead').bounding_box()
    pg.mouse.move(hb['x'] + 40, hb['y'] + 15); pg.mouse.down(); pg.mouse.move(hb['x'] - 250, hb['y'] + 120, steps=6); pg.mouse.up()
    after = pg.locator('#modal').bounding_box()
    pg.keyboard.press('Escape')
    pg.click(f'.card[data-cid="{CLERIC}"] .sb .nm[data-sid="cure-wounds-cleric"]'); pg.wait_for_selector('#scrim.open.float')
    again = pg.locator('#modal').bounding_box()
    check('pop-ups can be dragged, and the next opens where you left it', abs(again['x'] - after['x']) < 3 and abs(again['y'] - after['y']) < 3 and after['x'] < hb['x'] - 200, (hb, after, again))
    pg.dblclick('#modal .mhead h2')
    check('double-clicking the header puts it back', not ev(pg, "document.getElementById('modal').classList.contains('moved')"))
    pg.keyboard.press('Escape')
    check('cards say "Character sheet"', 'Character sheet' in pg.inner_text(f'.card[data-cid="{FIGHTER}"] .sbtoggle'))

    # ---- lookups never borrow another item's rules (Open5e's fuzzy search returning 'Acid')
    ACID = {"count": 1, "results": [{"name": "Acid", "desc": "When you take the Attack action, you can replace one of your attacks with throwing a vial of Acid.", "document": {"key": "srd-2024"}}]}
    RING = {"count": 1, "results": [{"name": "Ring of Protection", "desc": "You gain a +1 bonus to AC and saving throws.", "document": {"key": "srd-2014"}}]}
    def fake_open5e(route):
        u = route.request.url
        if 'search=' in u: route.fulfill(json=ACID)                            # fuzzy search: always some unrelated item
        elif 'iexact=Ring%20of%20Protection' in u: route.fulfill(json=RING)
        else: route.fulfill(json={"count": 0, "results": []})
    pg.unroute('https://api.open5e.com/**'); pg.route('https://api.open5e.com/**', fake_open5e)
    ev(pg, f"UI.open['{ROGUE}'] = true; UI.collapsed['{ROGUE}:inventory'] = false; renderAll()")
    pg.click(f'.card[data-cid="{ROGUE}"] .sb .nm[data-iid="lucky-picks"]'); pg.wait_for_function("!document.getElementById('modal').textContent.includes('Looking up')")
    txt = pg.inner_text('#modal')
    check('homebrew item does not pick up another item\'s rules', 'vial of Acid' not in txt and 'Not found on Open5e' in txt, txt[:200])
    pg.keyboard.press('Escape')
    pg.click(f'.card[data-cid="{ROGUE}"] .sb .nm[data-iid="ring-of-protection"]'); pg.wait_for_function("!document.getElementById('modal').textContent.includes('Looking up')")
    check('a real SRD item still gets its description', '+1 bonus to AC' in pg.inner_text('#modal'))
    pg.keyboard.press('Escape')
    pg.unroute('https://api.open5e.com/**'); pg.route('https://api.open5e.com/**', lambda r: r.abort())
    ev(pg, f"UI.open['{ROGUE}'] = false; UI.collapsed['{ROGUE}:inventory'] = true; renderAll()")

    # ---- paste from D&D Beyond: item text read into charges, actions and spells; the full text is always kept
    PASTED = ROOT / 'tests' / 'fixtures' / 'pasted'
    def paste_item(cid, iid, fixture):
        ev(pg, f"closeModal(); itemModal('{cid}', '{iid}')"); pg.wait_for_function("!document.getElementById('modal').textContent.includes('Looking up')")
        pg.click('#modal [data-act="pasteitem"] >> nth=0'); pg.wait_for_selector('#pasteText')
        pg.fill('#pasteText', (PASTED / fixture).read_text()); pg.click('#modal [data-act="pasteread"]'); pg.wait_for_selector('#modal [data-act="pasteapply"]')
        found = pg.inner_text('#modal'); pg.click('#modal [data-act="pasteapply"]'); pg.wait_for_timeout(100)
        return found, ev(pg, f"charById('{cid}').inventory.find(i => i.id === '{iid}')")
    found, it = paste_item(ROGUE, 'lucky-picks', 'staff.txt')
    check('paste preview lists the spells with their charge cost', 'Cast Fireball' in found and 'Spends 3 charges' in found, found[:300])
    r = ev(pg, f"resById(charById('{ROGUE}'), charById('{ROGUE}').inventory.find(i => i.id === 'lucky-picks').res)")
    check('paste adds a charge counter', r and r['max'] == 10 and r['reset'] == 'dawn', r)
    fb = next((a for a in it['actions'] if a['name'] == 'Cast Fireball'), None)
    check('spells become item actions that spend charges', fb and fb.get('cost') == 3 and fb.get('res') == it['res'], it['actions'])
    check('pasted text is saved as the description, item marked magic and attuned', 'Staff, rare' in it['desc'] and 'fireball (3 charges)' in it['desc'] and it['magic'] and it['attuned'])
    ev(pg, f"closeModal(); iactModal('{ROGUE}', 'lucky-picks', '{fb['id']}')"); pg.click('#modal [data-act="iactuse"]')
    check('using a 3-charge spell spends 3 charges', ev(pg, f"resById(charById('{ROGUE}'), '{it['res']}').used") == 3)
    found, it = paste_item(ROGUE, 'ring-of-protection', 'homebrew_lines.txt')
    names = [a['name'] for a in it['actions']]
    check('one-line-per-rule homebrew: bonus action and once-every-N-days action found', 'Call a Shroud of Frost' in names and any("Winter's Bite" in n for n in names), names)
    wb = next(a for a in it['actions'] if "Winter's Bite" in a['name'])
    wr = ev(pg, f"resById(charById('{ROGUE}'), '{wb['res']}')")
    check('once every 7 days becomes a 1-use counter reset by hand', wr and wr['max'] == 1 and wr['reset'] == 'none' and '7 days' in wr['notes'], wr)
    check('homebrew rules nobody can parse still end up in the description and notes', 'dual wielder feat' in it['desc'] and 'DC13 Strength' in it['notes'] and 'On a 20' in it['notes'], (it['desc'][-200:], it['notes']))
    pg.keyboard.press('Escape')
    pg.click(f'.card[data-cid="{ROGUE}"] [data-act="toggle"]')
    pg.click(f'.card[data-cid="{ROGUE}"] .addrow [data-act="addfeat"][data-v="action"]'); pg.wait_for_selector('#ff_text')
    pg.fill('#ff_text', (PASTED / 'feature.txt').read_text()); pg.click('#modal [data-act="featpaste"]')
    vals = ev(pg, "['name','act','res','newMax','newReset'].map(k => document.getElementById('ff_' + k).value)")
    check('pasted feature text fills name, type and uses', vals == ['Shadow Step', 'bonus', '__new', '3', 'long'], vals)
    pg.click('#modal [data-act="mclose"]'); pg.click(f'.card[data-cid="{ROGUE}"] [data-act="toggle"]')

    # ---- reference: search Open5e for anything, add it to a character
    SPELLS = {"count": 2, "results": [
        {"name": "Counterspell", "level": 3, "school": {"name": "Abjuration"}, "casting_time": "reaction", "range_text": "60 feet", "duration": "instantaneous", "verbal": False, "somatic": True, "desc": "You attempt to interrupt a creature in the process of casting a spell.", "document": {"key": "srd-2014", "name": "SRD 5.1"}},
        {"name": "Counterspell", "level": 3, "school": {"name": "Abjuration"}, "casting_time": "reaction", "desc": "2024 wording.", "document": {"key": "srd-2024", "name": "SRD 5.2"}}]}
    BAG = {"count": 1, "results": [{"name": "Bag of Holding", "rarity": {"name": "uncommon"}, "category": {"name": "Wondrous Item"}, "desc": "This bag has an interior space considerably larger than its outside dimensions.", "document": {"key": "srd-2014"}}]}
    def fake_ref(route):
        u = route.request.url
        if '/spells/' in u and 'icontains=counter' in u: route.fulfill(json=SPELLS)
        elif '/magicitems/' in u and 'icontains=bag' in u: route.fulfill(json=BAG)
        else: route.fulfill(json={"count": 0, "results": []})
    pg.unroute('https://api.open5e.com/**'); pg.route('https://api.open5e.com/**', fake_ref)
    pg.click('header [data-act="reference"]'); pg.wait_for_selector('#refQ')
    pg.type('#refQ', 'counter'); pg.wait_for_selector('#refBody [data-act="refpick"]')
    check('reference finds a spell once, from the ruleset you play', pg.locator('#refBody [data-act="refpick"]').count() == 1 and 'SRD 5.1' in pg.inner_text('#refBody'), pg.inner_text('#refBody'))
    pg.click('#refBody [data-act="refpick"]'); pg.click(f'#refBody [data-act="refadd"][data-cid="{BARD}"]')
    sp = ev(pg, f"charById('{BARD}').spells.find(s => s.name === 'Counterspell')")
    check('adding a spell from the reference fills in level, reaction and text', sp and sp['level'] == 3 and sp['time'] == '1R' and 'interrupt a creature' in sp['desc'] and sp['custom'], sp)
    check('reference pop-up stays open and marks who has it', pg.is_visible('#refBody') and pg.locator(f'#refBody [data-act="refadd"][data-cid="{BARD}"]').is_disabled())
    pg.click('#modal [data-act="refkind"][data-v="item"]'); pg.fill('#refQ', 'bag'); pg.wait_for_selector('#refBody [data-act="refpick"]')
    pg.click('#refBody [data-act="refpick"]'); pg.click(f'#refBody [data-act="refadd"][data-cid="{CLERIC}"]')
    check('adding an item from the reference', ev(pg, f"charById('{CLERIC}').inventory.some(i => i.name === 'Bag of Holding' && i.magic && i.custom)"))
    pg.click('#modal [data-act="refkind"][data-v="cond"]'); pg.fill('#refQ', 'prone'); pg.click('#refBody [data-act="refpick"]'); pg.click(f'#refBody [data-act="togcond"][data-cid="{FIGHTER}"]')
    check('applying a condition from the reference', 'Prone' in ev(pg, f"charById('{FIGHTER}').conditions"))
    ev(pg, f"charById('{FIGHTER}').conditions = charById('{FIGHTER}').conditions.filter(x => x !== 'Prone'); save(); renderAll()")
    pg.keyboard.press('Escape'); pg.wait_for_selector('#scrim.open', state='hidden')
    pg.unroute('https://api.open5e.com/**'); pg.route('https://api.open5e.com/**', lambda r: r.abort())

    # ---- temporary AC and max HP; custom conditions; rules in the condition picker
    base_ac, base_max = ev(pg, f"[charById('{CLERIC}').ac, charById('{CLERIC}').hp.max]")
    pg.click(f'.card[data-cid="{CLERIC}"] .stat.ac'); pg.fill('#tsVal', str(base_ac + 2)); pg.fill('#tsNote', 'Shield of Faith'); pg.click('#modal [data-act="tmpsave"]')
    check('temporary AC shows on the card, sheet AC kept underneath', str(base_ac + 2) in pg.inner_text(f'.card[data-cid="{CLERIC}"] .stat.ac') and ev(pg, f"charById('{CLERIC}').ac") == base_ac)
    cur = ev(pg, f"charById('{CLERIC}').hp.current")
    pg.click(f'.card[data-cid="{CLERIC}"] .hpbar'); pg.fill('#tsVal', str(base_max + 5)); pg.fill('#tsNote', 'Aid'); pg.click('#modal [data-act="tmpsave"]')
    check('temporary max HP raises current like Aid', ev(pg, f"[hpMaxOf(charById('{CLERIC}')), charById('{CLERIC}').hp.current]") == [base_max + 5, min(cur + 5, base_max + 5)])
    pg.click(f'.card[data-cid="{CLERIC}"] .hpbar'); pg.fill('#tsVal', str(base_max - 20)); pg.click('#modal [data-act="tmpsave"]')
    check('lowering max HP clamps current HP', ev(pg, f"charById('{CLERIC}').hp.current") <= base_max - 20 and f'{base_max - 20}' in pg.inner_text(f'.card[data-cid="{CLERIC}"] .hptext'))
    ev(pg, f"mutate(() => longRestChar(charById('{CLERIC}')))")
    check('long rest clears the temporary values and heals to the sheet max', ev(pg, f"[acOf(charById('{CLERIC}')), hpMaxOf(charById('{CLERIC}')), charById('{CLERIC}').hp.current]") == [base_ac, base_max, base_max])
    pg.click(f'.card[data-cid="{CLERIC}"] [data-act="cond"]'); pg.wait_for_selector('#condOther')
    pg.fill('#condOther', 'Hexed'); pg.press('#condOther', 'Enter'); pg.fill('#condOther', 'Marked by the Hunter'); pg.click('#modal [data-act="condother"]')
    pg.fill('#condOther', 'prone'); pg.press('#condOther', 'Enter')
    check('Other conditions: free text, several at once, standard names matched', ev(pg, f"charById('{CLERIC}').conditions") == ['Hexed', 'Marked by the Hunter', 'Prone'], ev(pg, f"charById('{CLERIC}').conditions"))
    pg.click('#modal [data-act="condrule"][data-v="Restrained"]')
    check('condition rules show in the picker', 'speed becomes 0' in pg.inner_text('#modal .condrules').lower() or 'Restrained' in pg.inner_text('#modal .condrules'), pg.inner_text('#modal .condrules'))
    check('custom conditions show as chips on the card', 'Hexed' in pg.inner_text(f'.card[data-cid="{CLERIC}"]'))
    pg.click('#modal [data-act="mclose"]')
    ev(pg, f"mutate(() => charById('{CLERIC}').conditions = [])")
    pg.click(f'.card[data-cid="{CLERIC}"] [data-act="cond"]'); pg.wait_for_selector('#condOther')
    check('used custom conditions are offered again', pg.locator('#modal [data-act="togcond"][data-v="Hexed"]').count() == 1)
    pg.click('#modal [data-act="mclose"]')

    # ---- death saves (type the d20 or tap) and automatic journal entries
    F = FIGHTER
    hp = lambda: ev(pg, f"charById('{F}').hp.current")
    ds = lambda: ev(pg, f"[charById('{F}').deathSaves.successes, charById('{F}').deathSaves.failures, !!charById('{F}').dead]")
    def hit(n):
        pg.fill(f'[data-hpin="{F}"]', str(n)); pg.click(f'[data-act="hp"][data-op="dmg"][data-cid="{F}"]')
    def roll(n):
        pg.fill(f'[data-dsin="{F}"]', str(n)); pg.press(f'[data-dsin="{F}"]', 'Enter')
    n_log = ev(pg, 'S.log.length')
    hit(hp())
    check('dropping to 0 shows the death-save controls', pg.locator(f'[data-dsin="{F}"]').count() == 1)
    roll(14); roll(5)
    check('typed d20: 10+ succeeds, under 10 fails', ds() == [1, 1, False], ds())
    roll(1)
    check('a natural 1 counts as two failures', ds() == [1, 3, True], ds())
    check('three failures: dead, card greyed, healing blocked', pg.locator(f'.card.dead[data-cid="{F}"]').count() == 1 and (ev(pg, f"heal(charById('{F}'), 5), charById('{F}').hp.current") == 0))
    pg.click(f'[data-act="revive"][data-cid="{F}"]')
    check('revived with 1 HP', hp() == 1 and not ds()[2])
    hit(1); roll(20)
    check('a natural 20 brings them back with 1 HP', hp() == 1 and 'Unconscious' not in ev(pg, f"charById('{F}').conditions"))
    hit(1); pg.click(f'[data-act="ds"][data-v="stab"][data-cid="{F}"]')
    check('stabilise', ev(pg, f"charById('{F}').deathSaves.stable") and 'Stable' in pg.inner_text(f'.card[data-cid="{F}"] .deathsaves'))
    hit(3)
    check('damage while stable starts the saves again with a failure', ds() == [0, 1, False] and not ev(pg, f"charById('{F}').deathSaves.stable"), ds())
    pg.click(f'[data-act="ds"][data-v="crit"][data-cid="{F}"]')
    check('critical hit while down: two failures', ds() == [0, 3, True], ds())
    pg.click(f'[data-act="revive"][data-cid="{F}"]'); hit(1 + ev(pg, f"hpMaxOf(charById('{F}'))"))
    check('massive damage kills outright', ds()[2])
    pg.click(f'[data-act="revive"][data-cid="{F}"]')
    auto = ev(pg, f"S.log.slice({n_log}).filter(e => e.auto).map(e => e.text)")
    check('HP changes and death saves are logged automatically', any('drops to 0 HP' in a for a in auto) and any('rolls 14 on a death save' in a for a in auto) and any('natural 20' in a for a in auto) and any('dies' in a.lower() or 'They die' in a for a in auto) and any('massive damage' in a for a in auto), auto[:6])
    pg.click(f'.card[data-cid="{F}"] [data-act="cond"]'); pg.click(f'#modal [data-act="togcond"][data-v="Poisoned"]'); pg.click('#modal [data-act="mclose"]')
    check('conditions are logged', ev(pg, "S.log[S.log.length - 1].text").endswith('is Poisoned.'))
    pg.click(f'.card[data-cid="{F}"] [data-act="rmcond"][data-v="Poisoned"]')
    if not pg.is_visible('#journal'): pg.click('header [data-act="journal"]')
    check('auto entries show in the journal, marked ⚙', '⚙' in pg.inner_text('#jlist'))
    pg.click('#journal [data-act="jauto"]')
    check('and can be hidden, which also leaves them out of the export', '⚙' not in pg.inner_text('#jlist') and 'death save' not in ev(pg, 'markdownLog()'))
    pg.click('#journal [data-act="jauto"]')
    check('shown again, they are in the export for the write-up', 'death save' in ev(pg, 'markdownLog()'))
    pg.click('#journal [data-act="jclose"]')
    ev(pg, f"mutate(() => longRestChar(charById('{F}')))")

    # ---- hit dice on the card: spend with a typed roll, correct with pips, long rest gives them back
    R = ROGUE
    hd = lambda: ev(pg, f"charById('{R}').hitDice.map(h => h.max - h.used)")
    full = hd(); die = ev(pg, f"charById('{R}').hitDice[0].die"); con = ev(pg, f"charById('{R}').abilities.con.mod")
    check('hit dice show on the card', pg.locator(f'.card[data-cid="{R}"] .hdrow').count() == len(full))
    ev(pg, f"mutate(() => damage(charById('{R}'), 20))"); hp0 = ev(pg, f"charById('{R}').hp.current")
    pg.click(f'.card[data-cid="{R}"] .hdrow [data-act="hdinfo"]'); pg.wait_for_selector('#modal [data-hdroll]')
    pg.fill('#modal [data-hdroll]', '5'); pg.press('#modal [data-hdroll]', 'Enter')
    check('spending a hit die heals roll + CON and uses the die', ev(pg, f"charById('{R}').hp.current") == hp0 + 5 + con and hd()[0] == full[0] - 1, (hp0, ev(pg, f"charById('{R}').hp.current"), hd()))
    check('the spend is logged with the roll', f'{die} hit die: rolled 5' in ev(pg, "S.log[S.log.length - 1].text"), ev(pg, "S.log[S.log.length - 1].text"))
    pg.keyboard.press('Escape')
    pg.click(f'.card[data-cid="{R}"] .hdrow .pip.avail >> nth=0')
    check('tapping a hit-die pip corrects the count, logged', hd()[0] == full[0] - 2 and 'hit dice set to' in ev(pg, "S.log[S.log.length - 1].text"))
    ev(pg, f"S.ruleset = '2014'; charById('{R}').hitDice.forEach(h => h.used = h.max); mutate(() => longRestChar(charById('{R}')))")
    total = sum(full)
    check('2014 long rest gives back half the hit dice', sum(hd()) == max(1, total // 2), hd())
    ev(pg, f"S.ruleset = '2024'; charById('{R}').hitDice.forEach(h => h.used = h.max); mutate(() => longRestChar(charById('{R}')))")
    check('2024 long rest gives them all back', hd() == full and 'regains' in ev(pg, "S.log[S.log.length - 1].text"), hd())
    ev(pg, "S.ruleset = '2014'; save(); renderAll()")

    # ---- homebrew editing and merge protection
    pg.click(f'.card[data-cid="{ROGUE}"] [data-act="toggle"]')
    pg.click(f'.card[data-cid="{ROGUE}"] .addrow [data-act="addfeat"][data-v="bonus"]'); pg.wait_for_selector('#ff_name')
    pg.fill('#ff_name', 'Shadow Step'); pg.fill('#ff_text', 'Teleport between shadows.'); pg.select_option('#ff_res', '__new'); pg.fill('#ff_newMax', '2')
    pg.click('#modal [data-act="formsave"]'); pg.wait_for_selector('#scrim.open', state='hidden')
    check('homebrew bonus action appears on the card', 'Shadow Step' in ' '.join(pg.locator(f'.card[data-cid="{ROGUE}"] .chip.act-bonus').all_inner_texts()))
    pg.click(f'.card[data-cid="{ROGUE}"] .en[data-fid="sneak-attack"]'); pg.click('#modal [data-act="editfeat"]'); pg.wait_for_selector('#ff_name'); pg.fill('#ff_text', 'EDITED'); pg.click('#modal [data-act="formsave"]'); pg.wait_for_selector('#scrim.open', state='hidden')
    pg.click(f'.card[data-cid="{ROGUE}"] .sh[data-k="inventory"]'); pg.wait_for_selector(f'.card[data-cid="{ROGUE}"] [data-act="additemfull"]')
    pg.click(f'.card[data-cid="{ROGUE}"] [data-act="additemfull"]'); pg.wait_for_selector('#ff_name'); pg.fill('#ff_name', 'Cloak of the Night Market'); pg.fill('#ff_desc', 'Homebrew cloak.'); pg.click('#modal [data-act="formsave"]'); pg.wait_for_selector('#scrim.open', state='hidden')
    ev(pg, "jsonMode='merge'"); pg.set_input_files('#fileJson', str(LEVELUP)); pg.wait_for_selector('[data-act="applyMerge"]')
    labels = pg.locator('#modal label').all_inner_texts()
    check('merge does not offer to remove your homebrew', not any('Shadow Step' in l or 'Cloak of the Night' in l for l in labels))
    sneak = ev(pg, "[...document.querySelectorAll('#modal label')].filter(l=>l.textContent.includes('Sneak Attack')).map(l=>l.querySelector('input').checked)")
    check('sheet change to an edited feature starts unticked', sneak == [] or sneak == [False], sneak)
    pg.click('[data-act="applyMerge"]')
    c = ev(pg, f"charById('{ROGUE}')")
    check('level-up merge applied', c['level'] == 8 and c['hp']['max'] == 79 and any(s['name'] == 'Shield' for s in c['spells']))
    check('homebrew survives the merge', any(f['name'] == 'Shadow Step' for f in c['features']) and any(i['name'] == 'Cloak of the Night Market' for i in c['inventory']), ([f['name'] for f in c['features'] if f.get('custom')], [i['name'] for i in c['inventory'] if i.get('custom')], [i['name'] for i in c['inventory']][-3:]))
    check('item removals default off (Bell kept)', any(i['name'] == 'Bell' for i in c['inventory']))

    # ---- campaigns and characters
    pg.click('[data-act="home"]'); pg.click('header [data-act="newcamp"]'); pg.fill('#ncName', 'One-shot')
    pg.click('#modal label:has-text("Tilly Merrowbuck") input'); pg.click('[data-act="docreatecamp"]'); pg.wait_for_timeout(200)
    check('new campaign with a copied character', ev(pg, 'S.name') == 'One-shot' and ev(pg, 'S.characters.map(c=>c.name)') == ['Tilly Merrowbuck'])
    check('copied character starts fresh', ev(pg, f"charById('{BARD}').hp.current") == 70 and ev(pg, f"resById(charById('{BARD}'),'bardic-inspiration').used") == 0)
    pg.click('.card.addtile'); pg.click('#modal [data-act="newchar"]'); pg.wait_for_selector('#ff_name')
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
    pg.click('header [data-act="journal"]')
    check('journal reopens where you left it', pg.is_visible('#journal') and abs(pg.locator('#journal').bounding_box()['x'] - moved['x']) < 20)
    pg.click('#journal [data-act="jclose"]')

    # ---- appearance (same choices as the Encounter Tracker)
    attr = lambda k: ev(pg, f"document.documentElement.getAttribute('{k}')")
    first = attr('data-theme')
    pg.click('#themeBtn')
    check('Day/Night button switches the theme', attr('data-theme') != first)
    pg.click('header [data-act="appearance"]'); pg.click('#modal [data-act="setlook"][data-v="blue"]'); pg.click('#modal [data-act="setlook"][data-k="font"]')
    check('accent and legible font apply', attr('data-accent') == 'blue' and attr('data-font') == 'legible')
    pg.keyboard.press('Escape'); pg.reload(); pg.wait_for_timeout(300)
    check('appearance is remembered', attr('data-theme') != first and attr('data-accent') == 'blue' and attr('data-font') == 'legible')
    pg.click('header [data-act="appearance"]'); pg.click('#modal [data-act="setlook"][data-v="gold"]'); pg.click('#modal [data-act="setlook"][data-k="font"]'); pg.keyboard.press('Escape')
    check('gold accent clears the attribute', attr('data-accent') is None and attr('data-font') is None)

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
