#!/usr/bin/env python3
"""
Cerakote Auto rolling 6-week PPC budget: inputs + the weekly ceiling math behind the Sales page section.

Scope (NIC / Matt Reid, 2026-10-01; Barcus's rules): Cerakote Auto only, every marketplace pooled into ONE weekly
bucket in USD. SP + SB + SD. Excludes Legacy, Prismatic and DSP. Weeks run Mon-Sun. Non-USD spend converts at
that day's rate. The bucket is a ceiling, not a spend target.
Carryover (Barcus): a week's leftover rolls into the NEXT week in full; an overspend comes out of the next week
in full. Carryover stacks. A finished week locks on the Tuesday after it ends; until then it is provisional.
Carryover only starts after the newest schedule's first week: NIC's own re-issued schedule already includes
everything before it, so it is never applied twice.
Per marketplace (Barcus 2026-10-08): each week's NIC total is split from the September monthly budgets. Each
market's base = its September budget in USD (schedule fx) x 7/30; the difference between NIC's week and that sum
goes us_share to Auto US and the rest to the other markets pro rata to September. Carryover runs per market, so
the markets always add up to the global bucket.

  python3 scripts/weekly.py schedule FILE.json            replace data/weekly/schedule.json (validates totals)
  python3 scripts/weekly.py si-daily CC_US FILE.json      SI get_sales_data(group_by=day) result -> daily spend
  python3 scripts/weekly.py day CC_SA 2026-10-05=12.40 ... daily spend by hand, local currency
  python3 scripts/weekly.py campaign CC_US 2026-10-05 2026-10-11 18796.65
        SI get_campaign_performance agg.TotalSpend for a range. Any gap above the daily rows (multi-ASIN SB/SD
        spend the per-ASIN daily feed cannot attribute) is spread across those days pro rata.
  python3 scripts/weekly.py fx FILE.json                  frankfurter.dev time series, USD base
  python3 scripts/weekly.py show                          print the computed weeks
"""
import json, os, sys, datetime as dt

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DIR = os.path.join(ROOT, 'data', 'weekly')
SCHED = os.path.join(DIR, 'schedule.json')
SPEND = os.path.join(DIR, 'spend.json')
CUR = {'CC_US': 'USD', 'CC_CA': 'CAD', 'CC_UK': 'GBP', 'CC_AUS': 'AUD', 'CC_DE': 'EUR', 'CC_FR': 'EUR',
       'CC_ES': 'EUR', 'CC_IT': 'EUR', 'CC_NL': 'EUR', 'CC_SA': 'SAR'}
PEGGED = {'USD': 1.0, 'SAR': 3.75}   # SAR is pegged to the dollar
D = dt.date.fromisoformat


def load(p, default):
    return json.load(open(p)) if os.path.exists(p) else default


def save(p, doc):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w') as f:
        json.dump(doc, f, indent=1, sort_keys=True)


def blank():
    return {'markets': {}, 'campaign': [], 'fx': {}}


def rate(fx, cur, day):
    """units of cur per 1 USD on day: that day's rate, else the last published rate before it (weekends)."""
    if cur in PEGGED:
        return PEGGED[cur], None
    ds = sorted(d for d in fx if cur in fx[d])
    prior = [d for d in ds if d <= day]
    if prior:
        return fx[prior[-1]][cur], None
    if ds:
        return fx[ds[0]][cur], f'{cur} on {day} used the {ds[0]} rate'
    return None, f'no {cur} rate for {day}'


def daily_usd(sp):
    """{market: {date: (local, usd)}} after the campaign-total top-up and conversion."""
    days = {m: {d: float(v) for d, v in r.get('days', {}).items()} for m, r in sp['markets'].items()}
    for c in sp.get('campaign', []):
        rows = {d: v for d, v in days.get(c['mkt'], {}).items() if c['start'] <= d <= c['end']}
        base = sum(rows.values())
        gap = c['total'] - base
        if rows and base > 0 and gap > 0.005:
            for d, v in rows.items():
                days[c['mkt']][d] = v + gap * v / base
    out, notes = {}, set()
    for m, r in days.items():
        for d, v in r.items():
            fxr, note = rate(sp.get('fx', {}), CUR[m], d)
            if note:
                notes.add(note)
            out.setdefault(m, {})[d] = (v, v / fxr if fxr else None)
    return out, sorted(notes)


def allocate(sched, base):
    """{market: USD base} for one week from the schedule's September split."""
    a = sched.get('allocation')
    if not a:
        return None
    sept = {m: a['sept_local'][m] / (PEGGED.get(CUR[m]) or a['fx'][CUR[m]]) * 7 / 30 for m in a['sept_local']}
    tot = sum(sept.values())
    intl = tot - sept.get('CC_US', 0)
    extra = base - tot
    out = {}
    for m, v in sept.items():
        share = a['us_share'] if m == 'CC_US' else (1 - a['us_share']) * v / intl
        out[m] = v + extra * share
    return out


def compute(today=None):
    today = today or dt.date.today()
    sched, sp = load(SCHED, None), load(SPEND, blank())
    if not sched:
        return None
    usd, notes = daily_usd(sp)
    through = max((d for m in usd.values() for d in m), default=None)
    first = sched['weeks'][0]['wk']
    weeks, carry, mcarry = [], 0.0, {}
    for w in sched['weeks']:
        s, e = D(w['start']), D(w['start']) + dt.timedelta(days=6)
        lock = e + dt.timedelta(days=2)
        mk, have = {}, set()
        for m, r in usd.items():
            for d, (loc, u) in r.items():
                if w['start'] <= d <= e.isoformat():
                    x = mk.setdefault(m, {'local': 0.0, 'usd': 0.0, 'cur': CUR[m]})
                    x['local'] += loc
                    x['usd'] += u or 0
                    have.add(d)
        days_in = len(have)
        if today > e:
            status = 'locked' if today >= lock else 'provisional'
        elif today >= s:
            status = 'current'
        else:
            status = 'upcoming'
        carry_in = carry if w['wk'] != first else 0.0
        ceiling = w['base'] + carry_in
        spend = sum(x['usd'] for x in mk.values()) if mk else None
        missing = [m for m in CUR if m not in mk] if mk else []
        row = {'wk': w['wk'], 'start': w['start'], 'end': e.isoformat(), 'base': w['base'], 'carry_in': round(carry_in, 2),
               'ceiling': round(ceiling, 2), 'spend': round(spend, 2) if spend is not None else None, 'days': days_in,
               'status': status, 'lock_date': lock.isoformat(), 'missing': missing,
               'markets': {m: {k: (round(v, 2) if isinstance(v, float) else v) for k, v in x.items()} for m, x in mk.items()}}
        row['left'] = round(ceiling - spend, 2) if spend is not None else None
        alloc = allocate(sched, w['base'])
        done = status in ('locked', 'provisional') and spend is not None and days_in == 7
        if alloc:
            row['alloc'] = {}
            for m, b in alloc.items():
                ci = mcarry.get(m, 0.0) if w['wk'] != first else 0.0
                ce = b + ci
                sp = mk.get(m, {}).get('usd') if mk else None
                loc = mk.get(m, {}).get('local') if mk else None
                row['alloc'][m] = {'base': round(b, 2), 'carry_in': round(ci, 2), 'ceiling': round(ce, 2),
                                   'spend': round(sp, 2) if sp is not None else None, 'spend_local': round(loc, 2) if loc is not None else None,
                                   'cur': CUR[m], 'left': round(ce - sp, 2) if sp is not None else None}
                mcarry[m] = (ce - (sp or 0)) if done and m in mk else 0.0
        if status in ('locked', 'provisional') and spend is not None and days_in == 7:
            carry = ceiling - spend          # full carryover into the next week, either direction
        else:
            carry = 0.0                      # nothing known yet beyond this week
        weeks.append(row)
    return {'source': sched.get('source'), 'issued': sched.get('issued'), 'total': sched.get('total'), 'scope': sched.get('scope'),
            'through': through, 'built': today.isoformat(), 'weeks': weeks,
            'alloc_note': (sched.get('allocation') or {}).get('note'), 'notes': notes + sched.get('notes', [])}


def main():
    a = sys.argv[1:]
    if not a:
        sys.exit(__doc__)
    cmd = a[0]
    if cmd == 'schedule':
        doc = json.load(open(a[1]))
        tot = round(sum(w['base'] for w in doc['weeks']), 2)
        if doc.get('total') is not None and abs(tot - doc['total']) > 0.02:
            sys.exit(f'weeks add to {tot}, schedule says {doc["total"]}')
        for w in doc['weeks']:
            if D(w['start']).weekday() != 0:
                sys.exit(f'week {w["wk"]} starts {w["start"]}, not a Monday')
        save(SCHED, doc)
        print(f'schedule: {len(doc["weeks"])} weeks, ${tot:,.2f}')
        return
    sp = load(SPEND, blank())
    if cmd == 'si-daily':
        m, raw = a[1], open(a[2]).read()
        if m not in CUR:
            sys.exit(f'unknown market {m}')
        r = json.JSONDecoder().raw_decode(raw[raw.index('{'):])[0]
        rows = {x['Date']: round(float(x['PPCCost']), 2) for x in r['Daily']}
        sp['markets'].setdefault(m, {'days': {}})['days'].update(rows)
        print(f'{m}: {len(rows)} days, {sum(rows.values()):,.2f} {CUR[m]}')
    elif cmd == 'day':
        m = a[1]
        if m not in CUR:
            sys.exit(f'unknown market {m}')
        for kv in a[2:]:
            d, v = kv.split('=')
            D(d)
            sp['markets'].setdefault(m, {'days': {}})['days'][d] = round(float(v), 2)
    elif cmd == 'campaign':
        m, s, e, t = a[1], a[2], a[3], float(a[4])
        sp['campaign'] = [c for c in sp['campaign'] if not (c['mkt'] == m and c['start'] == s and c['end'] == e)]
        sp['campaign'].append({'mkt': m, 'start': s, 'end': e, 'total': round(t, 2)})
    elif cmd == 'fx':
        r = json.load(open(a[1]))
        for d, rates in r['rates'].items():
            sp['fx'].setdefault(d, {}).update(rates)
        print(f'fx: {len(r["rates"])} days')
    elif cmd == 'show':
        c = compute()
        for w in c['weeks']:
            print(f"Wk{w['wk']} {w['start']} {w['status']:<11} base {w['base']:>10,.2f} carry {w['carry_in']:>10,.2f} "
                  f"ceiling {w['ceiling']:>10,.2f} spend {w['spend'] or 0:>10,.2f} days {w['days']} left {w['left'] or 0:>10,.2f}")
        for n in c['notes']:
            print('note:', n)
        return
    else:
        sys.exit(__doc__)
    save(SPEND, sp)


if __name__ == '__main__':
    main()
