#!/usr/bin/env python3
"""
Write the two small inputs behind the Sales page's Ad Budget Pacing section.

  python3 scripts/pacing.py budget 2026-10 --tab "Oct" CC_US=136000 CC_CA=25400 ...
  python3 scripts/pacing.py spend  2026-10 2026-10-03 CC_US=12345.67:si CL_US=321.00:h10 ...

budget -> data/budgets/<month>.json  (column C of the month's tab in NIC_Monthly_Budgets)
spend  -> data/pacing/<month>.json   (ad spend from the 1st through <through>, each channel in its own currency)
Channel keys must be one of CHANNELS. Unknown keys abort, so a typo never ships.
"""
import json, os, sys, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CHANNELS = {  # sheet "Sales Channel" -> tab
    'Amazon US - Cerakote Ceramics': 'CC_US', 'Amazon Canada': 'CC_CA', 'Amazon UK': 'CC_UK', 'Amazon Australia': 'CC_AUS',
    'Amazon Germany': 'CC_DE', 'Amazon France': 'CC_FR', 'Amazon Spain': 'CC_ES', 'Amazon Italy': 'CC_IT',
    'Amazon Netherlands': 'CC_NL', 'Saudi Arabia': 'CC_SA', 'Amazon US - Legacy Cerakote': 'CL_US', 'Amazon US - Prismatic Powders': 'PP_US'}
TABS = set(CHANNELS.values())


def kv(pairs):
    out = {}
    for p in pairs:
        k, v = p.split('=', 1)
        if k not in TABS:
            sys.exit(f'unknown channel {k}; use one of {sorted(TABS)}')
        out[k] = v
    return out


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('budget', 'spend'):
        sys.exit(__doc__)
    cmd, month = sys.argv[1], sys.argv[2]
    dt.datetime.strptime(month, '%Y-%m')
    today = dt.date.today().isoformat()
    if cmd == 'budget':
        args = sys.argv[3:]
        tab = None
        if '--tab' in args:
            i = args.index('--tab'); tab = args[i + 1]; del args[i:i + 2]
        ch = {k: round(float(v), 2) for k, v in kv(args).items()}
        path = os.path.join(ROOT, 'data', 'budgets', month + '.json')
        doc = {'month': month, 'source_tab': tab, 'read_at': today, 'channels': ch}
    else:
        through = sys.argv[3]
        if not through.startswith(month):
            sys.exit(f'through {through} is not in {month}')
        ch = {}
        for k, v in kv(sys.argv[4:]).items():
            amt, _, src = v.partition(':')
            ch[k] = {'spend': round(float(amt), 2), 'source': src or None}
        path = os.path.join(ROOT, 'data', 'pacing', month + '.json')
        doc = {'month': month, 'through': through, 'pulled_at': today, 'channels': ch, 'notes': []}
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, 'w') as f:
        json.dump(doc, f, indent=1)
    print(f'wrote {os.path.relpath(path, ROOT)}: {len(ch)} channels')


if __name__ == '__main__':
    main()
