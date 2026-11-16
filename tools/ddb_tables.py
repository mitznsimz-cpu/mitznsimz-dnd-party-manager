"""Parse spell tables and equipment lists from D&D Beyond flattened PDF text (pdftotext -layout)."""
import json, re, sys

LEVEL_RE = re.compile(r"=== (CANTRIPS|(\d)(?:st|nd|rd|th) LEVEL) ===(.*)")
SPELL_RE = re.compile(r"^([OP])\s{3}(\S.*)$")
PAGE_RE = re.compile(r"\s(PHB-2024 \d+|PHB \d+|DDBD|MoDr \d+|XGtE \d+|TCoE \d+)\s")
TIME_RE = re.compile(r"\s(\d+(?:A|BA|R)(?: \+ 10m)?|\d+[mh])\s")
COMP_RE = re.compile(r"\s(V,S,M|V,S|V,M|S,M|V|S|M)\s")


def parse_spells(lines):
    spells, slots, pact = [], {}, None
    level = None
    header = None
    for ln in lines:
        if "PREP SPELL NAME" in ln:
            header = {k: ln.index(k) for k in ("SPELL NAME", "SOURCE", "SAVE/ATK")}
            continue
        m = LEVEL_RE.search(ln)
        if m:
            level = 0 if m.group(1) == "CANTRIPS" else int(m.group(2))
            rest = m.group(3)
            sm = re.search(r"(\d+) Slots", rest)
            if sm:
                slots[level] = int(sm.group(1))
            pm = re.search(r"(\d+) Pact", rest)
            if pm:
                pact = {"level": level, "max": int(pm.group(1))}
            continue
        m = SPELL_RE.match(ln)
        if not m or header is None or level is None:
            continue
        name = ln[4:header["SOURCE"]].strip()
        source = ln[header["SOURCE"]:header["SAVE/ATK"]].strip()
        tail = ln[header["SAVE/ATK"]:]
        pg = PAGE_RE.search(tail + " ")
        page = pg.group(1) if pg else ""
        notes = tail[pg.end():].strip() if pg else ""
        tm = TIME_RE.search(" " + tail + " ")
        time = tm.group(1) if tm else ""
        saveatk = tail[: tm.start()].strip() if tm else ""
        cm = COMP_RE.search(tail[tm.end() - 1 if tm else 0:] + " ") if tm else None
        comp = cm.group(1) if cm else ""
        rng = ""
        dur = ""
        if tm and cm:
            after_time = tail[tm.end() - 1:]
            rng = after_time[: cm.start()].strip()
            dur_start = cm.end()
            dur = after_time[dur_start: (after_time.find(page) if page else None)].strip()
        ritual = "[R]" in name
        name = name.replace("[R]", "").strip()
        spells.append({
            "name": name,
            "level": level,
            "source": source.replace(" (Always Prepared)", ""),
            "alwaysPrepared": m.group(1) == "P" or "(Always Prepared)" in source,
            "saveAtk": saveatk,
            "time": time,
            "range": rng,
            "components": comp,
            "duration": dur,
            "concentration": dur.lower().startswith("concentration"),
            "ritual": ritual,
            "ref": page,
            "notes": notes,
        })
    return spells, slots, pact


ITEM_RE = re.compile(r"(\S(?:.*?\S)?)\s{2,}([\d,]+)\s{2,}(--|[\d.]+ lb\.)")


def parse_equipment(lines):
    items, attuned = [], []
    page = 0
    in_equip = False
    attune_col = None
    for ln in lines:
        if re.search(r"NAME\s+QTY\s+WEIGHT", ln):
            page += 1
            in_equip = True
            continue
        if not in_equip:
            continue
        if "EQUIPMENT" in ln and "QTY" not in ln:
            in_equip = False
            attune_col = None
            continue
        if "ATTUNED MAGIC ITEMS" in ln:
            attune_col = ln.index("ATTUNED MAGIC ITEMS")
            # left part of the line may hold an item
            ln = ln[:attune_col]
        # strip coin / weight-summary prefixes in the far-left column
        work = ln
        lead = re.match(r"^(\s*(?:CP|SP|EP|GP|PP)\s+[\d,]+|\s*[\d.,]+ lb\.)", work)
        if lead:
            work = " " * len(lead.group(0)) + work[len(lead.group(0)):]
        for m in ITEM_RE.finditer(work):
            name = re.sub(r"^(ENCUMBERED|PUSH/DRAG/LIFT|WEIGHT CARRIED)\s+", "", m.group(1).strip())
            if name in ("WEIGHT CARRIED", "ENCUMBERED", "PUSH/DRAG/LIFT"):
                continue
            entry = {"name": name, "qty": int(m.group(2).replace(",", "")),
                     "weight": None if m.group(3) == "--" else m.group(3), "_page": page}
            if attune_col is not None and m.start() >= attune_col - 5:
                attuned.append(name)
            else:
                items.append(entry)
    merged, log = [], []
    last_page = max((i["_page"] for i in items), default=0)
    tail = {id(i) for i in [i for i in items if i["_page"] == last_page][-3:]} if last_page > 1 else set()
    for it in items:
        prev = next((x for x in merged if x["name"] == it["name"]), None)
        if prev is None:
            merged.append(it)
        elif prev["_page"] != it["_page"] and id(it) in tail and prev["qty"] == it["qty"]:
            log.append(f"dropped overflow repeat: {it['name']} x{it['qty']}")
        else:
            prev["qty"] += it["qty"]
            log.append(f"summed duplicate lines: {it['name']} -> x{prev['qty']}")
    for x in merged:
        x.pop("_page")
    return merged, attuned, log


def parse_coins(text):
    coins = {}
    for c in ("CP", "SP", "EP", "GP", "PP"):
        m = re.search(rf"^\s*{c}\s+([\d,]+)", text, re.M)
        coins[c.lower()] = int(m.group(1).replace(",", "")) if m else 0
    return coins


if __name__ == "__main__":
    out = {}
    for path in sys.argv[1:]:
        text = open(path, encoding="utf-8").read()
        lines = text.splitlines()
        name = lines[2].strip()
        spells, slots, pact = parse_spells(lines)
        items, attuned, dedupe = parse_equipment(lines)
        out[name] = {"spells": spells, "slots": slots, "pact": pact,
                     "items": items, "attuned": attuned, "dedupe": dedupe, "coins": parse_coins(text)}
    json.dump(out, sys.stdout, indent=1, ensure_ascii=False)
