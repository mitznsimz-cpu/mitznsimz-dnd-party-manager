# MitzNSimz Party Manager

A fast at-the-table tracker for a **whole D&D 5e party**: built for when you're running every character yourself, or just want the party's numbers in one place while you play with paper and dice.

It's the sibling of the [MitzNSimz Encounter Tracker](https://github.com/mitznsimz-cpu/DnD-Encounter-Tracker): the tracker runs the monsters, this runs the heroes.

No install, no account. It runs entirely in your browser and keeps everything on your own device.

## What it does

- **Import from D&D Beyond** – pick your characters' D&D Beyond PDFs and the party is built for you: stats, saves, skills, attacks, features with their action types and uses, spells and slots, equipment, coins and backstory. Pick a character's new PDF after a level-up and review just what changed.
- **Campaigns** – one page lists your campaigns; each has its own party, purse, journal, notes and portraits. Duplicate, archive, export or delete (with a Recently deleted bin).
- **Party at a glance** – a card per character: HP with damage / heal / temp, death saves, conditions with rules text, concentration, saving throws, attacks (with attacks per Attack action), bonus actions and reactions, limited uses as tappable pips, and spell slots.
- **Character sheets** – open any character's full sheet: abilities, skills, senses, actions, bonus actions, reactions, special and limited uses, traits, spellcasting, equipment, notes and backstory. On a laptop they open in a side panel; several can be open at once.
- **Details everywhere** – tap a spell, item, feature or condition for its details in a pop-up you can drag anywhere (it doesn't block the page), with **Use** / **Cast** buttons that spend the right slot, charge or use. Spells and items are looked up on [Open5e](https://open5e.com).
- **Homebrew** – add or edit features, actions, limited uses, attacks, spells and items (with their own actions and charges) for anything your character sheet doesn't export properly.
- **Hit dice** – shown on each card as pips. Tap the name to spend one: type your roll and CON is added. Tap a pip to correct the count. A long rest gives back half (2014) or all (2024). Everything is logged.
- **Text size** – Standard, Large (default), Larger or Largest, in 🎨 Appearance.
- **Cast at any level** – a spell's pop-up lists every slot level you can cast it at and what it does there ("3rd: 3d4 + 4 healing, avg 11.5"). It reads the spell text, so it also handles extra darts, rays or targets, and cantrips at your character level. Cast spends that slot and logs the effect.
- **Uses on the card** – feature and item pills show uses left (●●○), and grey out when spent.
- **Death saves** – at 0 HP, type the d20 you rolled (1 = two failures, 20 = back up with 1 HP) or tap ✓/✗. There are also buttons for a critical hit while down and for Stabilise. Damage while down counts as a failure, and massive damage kills outright. Dead characters grey out until Revived.
- **Automatic journal entries** – damage, healing, temp HP, conditions, exhaustion, concentration, temporary AC/max HP, death saves and rests are logged for you (marked ⚙) as a reference for write-ups. Untick “⚙ auto entries” to hide them from the journal and the export.
- **Temporary AC and max HP** – click AC or the HP bar on a card to set a value for now (Aid, Shield of Faith, a curse). The sheet value stays underneath, the card marks it with ✦, and a long rest clears it unless you say otherwise.
- **Other conditions** – add your own conditions as free text, as many as you need. The condition picker shows each condition's rules (ⓘ) in the same pop-up.
- **Reference** – look up any spell, item or condition on Open5e (not just ones your party has), read it in a movable pop-up, and add it to a character's spell list or inventory, or apply the condition, from there.
- **Paste from D&D Beyond** – copy an item's text from D&D Beyond (homebrew included) and paste it into the item pop-up. The app finds the charges and how they come back, the actions, bonus actions and reactions it gives, spells cast from it with their charge cost, and bonuses worth a reminder. You tick what to add. The full text is always kept as the item's description. Feature text pasted into the feature form fills in the type and uses the same way.
- **Rests** – short rest with hit-dice spending (type your roll), long rest for the whole party in one click.
- **Party purse** – one shared purse with per-person shares and spending notes.
- **Party checks** – every save and skill for the whole party side by side, best highlighted.
- **Journal** – a floating panel you can keep open, move and resize while you play: a combat log tagged by character and round, with ★ memorable moments, plus shared party notes. Exports to Markdown for session write-ups.
- **Level-ups without losing anything** – import an updated character and review the changes. Sheet data updates; your HP, used slots, notes, journal, portraits and homebrew are kept.
- **Undo** – Ctrl/Cmd+Z for anything.

## Privacy

Everything is stored in your browser (`localStorage`). Nothing is uploaded and there's no server. Spell and item lookups go to the Open5e API. Use **Backup & import → Export everything** now and then: browser storage can be cleared.

## Repository layout

| Path | What it is |
|---|---|
| `index.html` | The app, production build. This is what GitHub Pages serves. |
| `dev/index.html` | Dev build: same app, separate storage (`dev_` namespace) so testing never touches real data. |
| `src/party_manager.html` | Source. Edit this, then build. |
| `tools/build.py` | Builds `index.html` and `dev/index.html` from the source. |
| `tools/ddb_harness.mjs` | Runs the app's D&D Beyond parser on PDFs from the command line (development). |
| `tools/ddb_tables.py` | Older reference parser for D&D Beyond PDF text. |
| `tests/run_paste_reader.mjs` | Unit checks for the paste reader, run with node against `tests/fixtures/pasted/` (invented items). |
| `tests/run_e2e.py` | End-to-end browser tests (Playwright + Chrome) against an anonymised test party. |
| `tests/run_pdf_import.py` | Browser test of PDF import, using your own sheets in `private/sheets/` (skipped if there are none). |
| `tests/fixtures/party.json` | The anonymised test party. |
| `assets/` | The app icon (also embedded in the HTML). |
| `private/` | Git-ignored: your own party files, sheets and seeded builds. |

## Building and testing

```sh
python3 tools/build.py          # writes index.html and dev/index.html
python3 tests/run_e2e.py        # needs: pip install playwright, and Chrome
node tests/run_paste_reader.mjs
```

A private build with your own party embedded as starter data:

```sh
python3 tools/build.py --seed private/party.json --out private/party_manager.html
```

## How PDF import works

D&D Beyond's character-sheet PDF keeps every value in a named form field. The app loads [pdf.js](https://mozilla.github.io/pdf.js/) from jsDelivr the first time you import, reads those fields in your browser and builds the character. Nothing is uploaded.

What it can't know, it tells you after the import: how many charges a homebrew item has, which spells a cleric or wizard has prepared (the sheet lists the whole class list), and any equipment lines it tidied up. Homebrew item rules aren't in the PDF either: copy them from D&D Beyond and use 📋 Paste from D&D Beyond in the item pop-up, or type them in with ✎ Edit.

## Data format and the merge

A party file is `{"name", "characters": [...]}`; a campaign export is `{"campaign": {...}, "portraits": {...}}`. Each character carries **sheet-owned** data (identity, scores, skills, max HP, attacks, spells, features, slot and use maximums) and **session-owned** data (current HP, used slots and uses, conditions, concentration, notes, prepared choices, item notes).

When an updated sheet is imported, only sheet-owned data changes, and every change is shown for approval first. Anything added in the app is marked *custom* and is never removed by a merge; anything edited in the app is marked *edited*, and the sheet's version of it starts unticked. Item removals and quantity changes also start unticked, because the app is usually more up to date than the sheet.

## Releasing

1. Edit `src/party_manager.html` and bump `APP_VERSION`.
2. `python3 tools/build.py` and `python3 tests/run_e2e.py`.
3. Commit the source and both builds together.

---

⚔ Created by [MitzNSimz](https://mitznsimz.com): miniatures and tools for Dungeon Masters · [☕ Support on Ko-fi](https://ko-fi.com/mitznsimz)
