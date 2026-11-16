#!/usr/bin/env python3
"""Build the Party Manager from src/party_manager.html.

  python3 tools/build.py
      index.html      production build (storage namespace '', no starter data)
      dev/index.html  dev build (storage namespace 'dev_', so testing never touches real data)

  python3 tools/build.py --seed private/party.json --out private/party_manager.html [--ns dev_]
      a private build with a party embedded as starter data (keep it out of git)
"""
import argparse, json, pathlib, sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
SRC = ROOT / 'src' / 'party_manager.html'
NS_HOOK, SEED_HOOK = "/*NS*/'dev_'", '/*SEED*/null'


def build(ns, seed=None):
    html = SRC.read_text(encoding='utf-8')
    for hook in (NS_HOOK, SEED_HOOK):
        if html.count(hook) != 1:
            sys.exit(f'build: expected exactly one {hook!r} in {SRC.name}')
    html = html.replace(NS_HOOK, f"/*NS*/'{ns}'")
    if seed is not None:
        html = html.replace(SEED_HOOK, json.dumps(seed, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/'))
    return html


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--seed', help='party JSON to embed as starter data')
    ap.add_argument('--out', help='output path for a seeded build')
    ap.add_argument('--ns', default='dev_', help="storage namespace for a seeded build (default 'dev_')")
    a = ap.parse_args()
    if a.seed:
        out = pathlib.Path(a.out or ROOT / 'private' / 'party_manager.html')
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(build(a.ns, json.loads(pathlib.Path(a.seed).read_text(encoding='utf-8'))), encoding='utf-8')
        print('wrote', out)
        return
    (ROOT / 'index.html').write_text(build(''), encoding='utf-8')
    (ROOT / 'dev').mkdir(exist_ok=True)
    (ROOT / 'dev' / 'index.html').write_text(build('dev_'), encoding='utf-8')
    print('wrote index.html (production) and dev/index.html (dev_)')


if __name__ == '__main__':
    main()
