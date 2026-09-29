#!/usr/bin/env python3
"""
Cerakote Ops site: one URL, three pages, one shell.

  sales/       <- NIC repo data/weeks/*.json + config, plus data/budgets + data/pacing (this repo)
  health/      <- INTL repo data/snapshots/*.json, account-health, compliance and Seller Support items only
  inventory/   <- INTL repo data/q4/*.json + q4/files/

The NIC and INTL repos stay the data pipelines. This repo only renders. Nothing here writes to them.
Usage: python3 scripts/build.py --nic ../NIC --intl ../INTL
"""
import json, os, glob, sys, shutil, re, datetime as dt
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def arg(name, default):
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv else default


NIC = os.path.abspath(arg('--nic', os.path.join(ROOT, '..', 'NIC')))
INTL = os.path.abspath(arg('--intl', os.path.join(ROOT, '..', 'INTL')))
MAX_WEEKS = 52


def js(obj):
    return json.dumps(obj, ensure_ascii=False, separators=(',', ':')).replace('</', '<\\/')


def read(p):
    with open(p, encoding='utf-8') as f:
        return f.read()


def write(p, s):
    os.makedirs(os.path.dirname(p), exist_ok=True)
    with open(p, 'w', encoding='utf-8') as f:
        f.write(s)
    print(f'  wrote {os.path.relpath(p, ROOT)} ({len(s)//1024} KB)')


# ---------------------------------------------------------------- shell
LOGO = read(os.path.join(ROOT, 'pages', 'logo.svg'))
PAGES = [('sales', 'Sales'), ('health', 'Account Health'), ('inventory', 'Inventory')]

SHELL_CSS = """
/* ---- shell (shared by all three pages) ---- */
.header{gap:16px;}
.header-left{min-width:0;}
.site-nav{display:flex;align-items:center;gap:4px;background:var(--bg3);border:1px solid var(--border);border-radius:8px;padding:3px;}
.site-nav a{font-family:var(--font-display);font-size:12px;font-weight:600;letter-spacing:0.2px;color:var(--muted);text-decoration:none;padding:6px 14px;border-radius:6px;white-space:nowrap;transition:background .15s,color .15s;}
.site-nav a:hover{color:var(--text);background:var(--bg4);}
.site-nav a.on{color:#0a0a0a;background:var(--accent);}
.site-nav a:focus-visible{outline:2px solid var(--accent);outline-offset:2px;}
.asof{display:flex;flex-direction:column;align-items:flex-end;gap:1px;}
.asof .lbl{font-size:9px;color:var(--dim);text-transform:uppercase;letter-spacing:1px;font-family:var(--font-mono);}
.asof .val{font-family:var(--font-mono);font-size:11px;color:var(--text2);font-weight:500;white-space:nowrap;}
@media(max-width:900px){
  .header{height:auto!important;padding:10px 16px!important;flex-wrap:wrap;row-gap:10px;}
  .header-left{flex-wrap:wrap;row-gap:8px;}
  .header .divider-v,.header .header-meta,.header .header-title{display:none;}
  .header-right{margin-left:auto;}
  .site-nav{order:3;width:100%;overflow-x:auto;}
  .site-nav a{flex:1;text-align:center;padding:7px 8px;}
  .page{padding:16px!important;}
  .mkt-bar,.week-ctrl,.trend-bar,.filter-bar{padding-left:16px!important;padding-right:16px!important;}
  .brand-ribbon{gap:18px;padding:12px 16px;}
  .week-ctrl,.filter-bar,.filter-group{flex-wrap:wrap;row-gap:8px;}
  .week-range{margin-left:0!important;}
  .asof .lbl{display:none;}
}
"""


def shell_header(page, meta_html='', right_html=''):
    on = ' class="on" aria-current="page"'
    nav = ''.join(f'<a href="../{k}/"{on if k == page else ""}>{n}</a>' for k, n in PAGES)
    built = dt.datetime.now(ZoneInfo('America/Chicago')).strftime('%b %-d, %Y %-I:%M %p CT')  # CDT/CST aware
    return (f'<header class="header">\n  <div class="header-left">\n'
            f'    <a href="https://www.nicindustries.com/" target="_blank" rel="noopener" class="brand-logo" aria-label="NIC Industries">{LOGO}</a>\n'
            f'    <div class="divider-v"></div>\n    <nav class="site-nav" aria-label="Dashboards">{nav}</nav>\n'
            f'    {meta_html}\n  </div>\n'
            f'  <div class="header-right">{right_html}<div class="asof"><div class="lbl">Updated</div><div class="val">{built}</div></div></div>\n</header>')


def swap_header(tpl, header):
    a = tpl.index('<header class="header">')
    b = tpl.index('</header>', a) + len('</header>')
    return tpl[:a] + header + tpl[b:]


def add_css(tpl):
    i = tpl.index('</style>')
    tpl = tpl[:i] + SHELL_CSS + tpl[i:]
    if 'name="robots"' not in tpl:  # client data: keep it out of search indexes
        tpl = tpl.replace('<meta charset="UTF-8">', '<meta charset="UTF-8">\n<meta name="robots" content="noindex, nofollow">', 1)
    return tpl


# ---------------------------------------------------------------- sales
def build_sales():
    accounts = json.load(open(os.path.join(NIC, 'config', 'accounts.json')))
    fx = {k: v for k, v in json.load(open(os.path.join(NIC, 'config', 'fx.json'))).items() if not k.startswith('_')}
    keys_ = ('name', 'revenue', 'units', 'orders', 'sessions', 'pageviews', 'cvr', 'adSpend', 'adSales', 'organic', 'acos', 'tacos', 'roas',
             'ntbOrders', 'ntbSales', 'ntbPct', 'bsr', 'status', 'subcategory', 'subcategoryBSR', 'categoryBSR')
    files = sorted(glob.glob(os.path.join(NIC, 'data', 'weeks', 'WE_*.json')))[-MAX_WEEKS:]
    archived = {a['tab'] for a in accounts if a.get('archived')}
    weeks = []
    for p in reversed(files):
        w = json.load(open(p))
        weeks.append({'id': w['id'], 'label': w['label'], 'range': w['range'], 'fullLabel': w['fullLabel'], 'we': w['we'],
                      'generated_at': w.get('generated_at'),
                      'markets': {t: {'acct': m['acct'], 'products': [{k: pr.get(k) for k in keys_} for pr in m['products']],
                                      'flags': m['flags'], 'source': m.get('source'),
                                      # NTB comes from the Wednesday Reports Beta email; a Monday build has none yet
                                      'ntbLoaded': not any('NTB not loaded' in f for f in m['flags'])}
                                  for t, m in w['markets'].items() if t not in archived}})
    # Amazon only reports NTB on some ad types/markets (SB/SD, plus SP in the US). A market that never shows an NTB
    # order in any loaded week does not report it: the page shows n/a there instead of a misleading 0.
    ntb_markets = sorted({t for w in weeks for t, m in w['markets'].items() if m['ntbLoaded'] and (m['acct'].get('ntbOrders') or 0) > 0})
    meta = {'GLOBAL': {'name': 'Global (All Markets)', 'currency': '', 'flag': ''}}
    for a in accounts:
        meta[a['tab']] = {'name': a['name'], 'currency': a['currency'], 'flag': a['market'], 'label': a['label'], 'code': a['code']}
    mkeys = ['GLOBAL'] + [a['tab'] for a in accounts if not a.get('archived')]

    # budget pacing: every month that has a budget file; spend comes from data/pacing/<month>.json
    pacing = []
    for bp in sorted(glob.glob(os.path.join(ROOT, 'data', 'budgets', '*.json'))):
        b = json.load(open(bp))
        pp = os.path.join(ROOT, 'data', 'pacing', os.path.basename(bp))
        s = json.load(open(pp)) if os.path.exists(pp) else None
        pacing.append({'month': b['month'], 'budgets': b.get('channels', {}), 'source_tab': b.get('source_tab'),
                       'through': s and s['through'], 'spend': (s or {}).get('channels', {}), 'notes': (s or {}).get('notes', [])})
    # a month with spend but no budget yet (e.g. October before the client sets it)
    have = {p['month'] for p in pacing}
    for sp in sorted(glob.glob(os.path.join(ROOT, 'data', 'pacing', '*.json'))):
        s = json.load(open(sp))
        if s['month'] not in have:
            pacing.append({'month': s['month'], 'budgets': {}, 'source_tab': None, 'through': s['through'],
                           'spend': s.get('channels', {}), 'notes': s.get('notes', [])})
    pacing.sort(key=lambda x: x['month'])

    # exact calendar-month totals (NIC data/periods/<YYYY-MM>.json, normalize.py --period); the Month view prefers these
    periods = {}
    for pp in sorted(glob.glob(os.path.join(NIC, 'data', 'periods', '*.json'))):
        d = json.load(open(pp))
        periods[d['month']] = {k: d[k] for k in ('month', 'start', 'end', 'days', 'complete', 'label', 'fullLabel')}
        periods[d['month']]['markets'] = {t: {'acct': m['acct'], 'products': [{k: pr.get(k) for k in keys_} for pr in m['products']],
                                              'flags': m['flags'], 'ntbLoaded': not any('NTB not loaded' in f for f in m['flags'])}
                                          for t, m in d['markets'].items() if t not in archived}
    stock = build_stock_links(files)
    changes = json.load(open(os.path.join(ROOT, 'data', 'changes.json'))) if os.path.exists(os.path.join(ROOT, 'data', 'changes.json')) else {}

    tpl = read(os.path.join(ROOT, 'pages', 'sales.html'))
    tpl = add_css(swap_header(tpl, shell_header('sales')))
    html = (tpl.replace('/*__MKT_META__*/', js(meta)).replace('/*__MKT_KEYS__*/', js(mkeys)).replace('/*__FX__*/', js(fx))
            .replace('/*__WEEKS__*/', js(weeks)).replace('/*__PACING__*/', js(pacing)).replace('/*__NTB_MKTS__*/', js(ntb_markets))
            .replace('/*__PERIODS__*/', js(periods)).replace('/*__STOCK__*/', js(stock)).replace('/*__CHANGES__*/', js(changes)))
    write(os.path.join(ROOT, 'sales', 'index.html'), html)


# Inventory page -> Sales page: what is out of stock right now, per sales tab and product, from the latest Q4 projection.
Q4_TO_TAB = {'CC_US': 'CC_US', 'CC_CA': 'CC_CA', 'CC_UK': 'CC_UK', 'CC_DE': 'CC_DE', 'CC_AU': 'CC_AUS', 'CC_SA': 'CC_SA',
             'CL_US': 'CL_US', 'PP_US': 'PP_US'}
EU_TAB = {'DE': 'CC_DE', 'FR': 'CC_FR', 'IT': 'CC_IT', 'ES': 'CC_ES', 'NL': 'CC_NL'}
# main ASIN per Cerakote Auto product (NIC RUNBOOK 1c). An out-of-stock variant is not the product being out.
MAIN_ASINS = {'B084RQKLV8', 'B07SHJVK4G', 'B0B94G13CN', 'B0F45C2YHV', 'B0FYRJ1966', 'B0CN8HJSYM', 'B0DJMW6283', 'B0DKVZRX69',
              'B0CQN1RXYB', 'B0DVB4P9KQ', 'B0FW6WFX4D', 'B0FX5WH19H', 'B0DVV6K9Y6'}


def build_stock_links(week_files):
    q4 = sorted(glob.glob(os.path.join(INTL, 'data', 'q4', '*.json')))
    if not q4 or not week_files:
        return {}
    d = json.load(open(q4[-1]))
    latest = json.load(open(week_files[-1]))
    a2p = {}  # (tab, asin) -> sales product name, from the latest NIC week
    for t, m in latest['markets'].items():
        for pr in m['products']:
            for a in pr.get('asins') or []:
                a2p[(t, a)] = pr['name']
            if re.fullmatch(r'B0[A-Z0-9]{8}', pr.get('asin') or ''):
                a2p[(t, pr['asin'])] = pr['name']
    dm = json.load(open(os.path.join(NIC, 'config', 'data_map.json'))).get('asin_to_product', {})
    for t in latest['markets']:
        if t.startswith('CC_'):
            for asin, prod in dm.items():   # products map by ASIN even in a week the ASIN sold nothing
                if prod and not str(prod).startswith('OTHER:'):
                    a2p.setdefault((t, asin), prod)
    out = {'as_of': d.get('as_of'), 'week': d.get('week'), 'tabs': {}}
    for r in d['rows']:
        if r['status'] != 'OUT':
            continue
        tabs = [EU_TAB[mk] for mk in r['markets'] if mk in EU_TAB] if r['account'] == 'CC_EU' else [Q4_TO_TAB.get(r['account'])]
        for t in [x for x in tabs if x]:
            e = out['tabs'].setdefault(t, {'out': 0, 'lost_usd': 0.0, 'items': []})
            e['out'] += 1
            if not r.get('blocked'):
                e['lost_usd'] += r.get('lost_usd') or 0
            e['items'].append({'asin': r['asin'], 'name': r['name'], 'product': a2p.get((t, r['asin'])), 'since': r.get('oos_start'),
                               'main': (r['asin'] in MAIN_ASINS) if t.startswith('CC_') else True,
                               'days': r.get('oos_days'), 'lost_usd': round(r.get('lost_usd') or 0), 'inbound': r.get('inbound'),
                               'hold': bool(r.get('blocked')), 'pool': r['label'] if r['pooled'] else None})
    for e in out['tabs'].values():
        e['lost_usd'] = round(e['lost_usd'])
        e['items'].sort(key=lambda x: -x['lost_usd'])
    return out


# ---------------------------------------------------------------- health
KEEP_TYPES = {'account', 'case'}


def build_health():
    snaps = []
    for p in sorted(glob.glob(os.path.join(INTL, 'data', 'snapshots', '*.json')))[-MAX_WEEKS:]:
        s = json.load(open(p))
        s['items'] = [i for i in s['items'] if i.get('type') in KEEP_TYPES]
        s.pop('selling', None)
        for a in s['accounts'].values():  # stock lives on the Inventory page now
            for k in ('inventory',):
                a.pop(k, None)
        snaps.append(s)
    tpl = read(os.path.join(ROOT, 'pages', 'health.html'))
    meta = ('<div class="divider-v"></div>'
            '<div class="header-meta"><div class="lbl">Week</div><div class="val" id="hdr-week">—</div></div>'
            '<div class="header-meta"><div class="lbl">Read</div><div class="val" id="hdr-gen">—</div></div>')
    tpl = add_css(swap_header(tpl, shell_header('health', meta, '<span id="hdr-sources" hidden></span>')))
    html = tpl.replace('/*__DATA__*/', 'var SNAPSHOTS = ' + js(snaps) + ';')
    write(os.path.join(ROOT, 'health', 'index.html'), html)


# ---------------------------------------------------------------- inventory
def build_inventory():
    tpl = read(os.path.join(ROOT, 'pages', 'health.html'))  # same head, CSS and ribbon as the health page
    meta = ('<div class="divider-v"></div>'
            '<div class="header-meta"><div class="lbl">Projection</div><div class="val" id="hdr-week">—</div></div>'
            '<div class="header-meta"><div class="lbl">Data</div><div class="val" id="hdr-gen">—</div></div>')
    tpl = add_css(swap_header(tpl, shell_header('inventory', meta)))
    tpl = tpl.replace('<title>NIC Industries · Account Health</title>', '<title>NIC Industries · Q4 Inventory</title>')
    head = tpl[:tpl.index('</header>') + len('</header>')]
    tail = tpl[tpl.index('<div class="brand-ribbon">'):tpl.index('<div class="toast"')]
    tail = tail.replace('Account Health &middot;', 'Q4 Inventory &middot;')
    body = read(os.path.join(ROOT, 'pages', 'inventory_body.html'))
    app = read(os.path.join(ROOT, 'pages', 'inventory_app.js'))
    snaps = []
    for p in sorted(glob.glob(os.path.join(INTL, 'data', 'q4', '*.json')))[-26:]:
        s = json.load(open(p))
        mf = os.path.join(INTL, 'q4', 'files', s['week'], 'manifest.json')
        if os.path.exists(mf):
            s['files'] = json.load(open(mf))
        snaps.append(s)
    html = (head + '\n' + body + tail + '<div class="toast" id="toast"></div>\n<script>\nvar Q4 = ' + js(snaps) + ';\n</script>\n<script>\n'
            + app + '\n</script>\n</body>\n</html>\n')
    write(os.path.join(ROOT, 'inventory', 'index.html'), html)
    src = os.path.join(INTL, 'q4', 'files')
    dst = os.path.join(ROOT, 'inventory', 'files')
    if os.path.isdir(src):
        shutil.rmtree(dst, ignore_errors=True)
        shutil.copytree(src, dst, dirs_exist_ok=True)  # survives a folder where deletes are blocked


def build_root():
    write(os.path.join(ROOT, 'index.html'),
          '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
          '<title>NIC Industries · Cerakote Ops</title><meta http-equiv="refresh" content="0; url=sales/">'
          '<style>body{background:#0a0a0a;color:#a3a3a3;font:13px system-ui;padding:40px}a{color:#ff9800}</style></head>'
          '<body><a href="sales/">Open the Sales dashboard</a></body></html>\n')


if __name__ == '__main__':
    for d in (NIC, INTL):
        if not os.path.isdir(d):
            sys.exit(f'missing source repo: {d}')
    print(f'NIC  = {NIC}\nINTL = {INTL}')
    build_sales()
    build_health()
    build_inventory()
    build_root()
    sys.path.insert(0, os.path.join(ROOT, 'scripts'))
    import lock
    if lock.enabled():
        stuck = lock.encrypt_site([(os.path.join(ROOT, p, 'index.html'), t) for p, t in PAGES],
                                  [os.path.join(ROOT, 'inventory', 'files')])
        if stuck:
            sys.exit('plain download files left behind; delete them before publishing')
    else:
        print('  lock OFF: pages are published unencrypted (run scripts/lock.py setup to turn it on)')
