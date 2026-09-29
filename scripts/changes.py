#!/usr/bin/env python3
"""
Ad-change markers for the Sales page (data/changes.json), from Scale Insights get_change_history.
Only changes logged in Scale Insights are counted; edits made straight in the Amazon Ads console are not.

  python3 scripts/changes.py counts 2026-10-04 US=1949:3769 CA=12:40 ...     # week ending Sunday, manual:automation
  python3 scripts/changes.py budget US <tool-result.json> [...]              # get_change_history raw, action=budget
"""
import json, os, sys, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATH = os.path.join(ROOT, 'data', 'changes.json')
TAB = {'US': 'CC_US', 'CA': 'CC_CA', 'UK': 'CC_UK', 'DE': 'CC_DE', 'FR': 'CC_FR', 'IT': 'CC_IT', 'ES': 'CC_ES', 'NL': 'CC_NL', 'AU': 'CC_AUS'}


def load():
    if os.path.exists(PATH):
        return json.load(open(PATH))
    return {'source': 'Scale Insights get_change_history, changes logged in Scale Insights only', 'weeks': {}, 'budget_changes': {}}


def parse(path):
    raw = open(path).read()
    try:
        d = json.loads(raw)
        if isinstance(d, list):
            d = json.JSONDecoder().raw_decode(d[0]['text'])[0]
    except json.JSONDecodeError:
        d = json.JSONDecoder().raw_decode(raw)[0]
    return d


def main():
    if len(sys.argv) < 3 or sys.argv[1] not in ('counts', 'budget'):
        sys.exit(__doc__)
    doc = load()
    if sys.argv[1] == 'counts':
        we = dt.date.fromisoformat(sys.argv[2])
        if we.weekday() != 6:
            sys.exit('week key must be the Sunday')
        wk = doc['weeks'].setdefault(we.isoformat(), {})
        for kv in sys.argv[3:]:
            c, v = kv.split('=')
            m, a = v.split(':')
            wk[TAB[c]] = {'manual': int(m), 'automation': int(a)}
    else:
        tab = TAB[sys.argv[2]]
        have = {json.dumps(x, sort_keys=True) for x in doc['budget_changes'].get(tab, [])}
        for p in sys.argv[3:]:
            for c in parse(p).get('Changes', []):
                if c.get('Action') != 'budget':
                    continue
                day = dt.date.fromisoformat(c['TimestampUtc'][:10])
                rec = {'date': day.isoformat(), 'we': (day + dt.timedelta(days=6 - day.weekday())).isoformat(), 'type': c['SponsoredType'],
                       'campaign': c['CampaignId'], 'old': c['OldValue'], 'new': c['NewValue'],
                       'by': 'manual' if c['Source'] == 'manual' else c['Actor']}
                have.add(json.dumps(rec, sort_keys=True))
        doc['budget_changes'][tab] = sorted((json.loads(x) for x in have), key=lambda r: r['date'])
    with open(PATH, 'w') as f:
        json.dump(doc, f, indent=1)
    print('wrote', os.path.relpath(PATH, ROOT))


if __name__ == '__main__':
    main()
