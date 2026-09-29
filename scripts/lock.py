#!/usr/bin/env python3
"""
Password lock for the Cerakote Ops site. Uses only the openssl CLI and the Python stdlib.

How it works
  setup (once, on Barcus's Mac):  python3 scripts/lock.py setup
    Makes an RSA-3072 key pair. The public key goes in config/lock.json in plain form.
    The private key is encrypted with a key derived from the password (PBKDF2-SHA256,
    600k rounds) and also goes in config/lock.json. The password itself is stored nowhere.
  every build (build.py calls encrypt_site when config/lock.json exists):
    A fresh random AES-256 key encrypts each page and each download file.
    That AES key is encrypted with the public key and written into each page.
    So the build never needs the password, and the scheduled run can build unattended.
  in the browser:
    The password unlocks the private key, the private key unlocks the AES key, the AES key
    unlocks the page. "Remember on this device" keeps the unlocked private key in
    localStorage so the other pages open without the password.

  python3 scripts/lock.py setup            # prompts for the password twice
  python3 scripts/lock.py setup --stdin    # reads the password from stdin (testing)
  python3 scripts/lock.py status
Changing the password: run setup again. Every device then needs the new password once.
"""
import base64, hashlib, json, os, subprocess, sys, tempfile, getpass

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
CFG = os.path.join(ROOT, 'config', 'lock.json')
ITER = 600000
b64 = lambda b: base64.b64encode(b).decode()


def ossl(*args, data=None):
    r = subprocess.run(['openssl', *args], input=data, capture_output=True)
    if r.returncode:
        raise RuntimeError('openssl ' + ' '.join(args[:2]) + ': ' + r.stderr.decode()[:300])
    return r.stdout


def aes_cbc(key, iv, data):
    return ossl('enc', '-aes-256-cbc', '-K', key.hex(), '-iv', iv.hex(), data=data)


def setup(pw):
    if len(pw) < 12:
        sys.exit('password must be at least 12 characters')
    with tempfile.TemporaryDirectory() as t:
        pem = os.path.join(t, 'k.pem')
        ossl('genpkey', '-algorithm', 'RSA', '-pkeyopt', 'rsa_keygen_bits:3072', '-out', pem)
        pk8 = ossl('pkcs8', '-topk8', '-nocrypt', '-in', pem, '-outform', 'DER')
        spki = ossl('pkey', '-in', pem, '-pubout', '-outform', 'DER')
    salt, iv = os.urandom(16), os.urandom(16)
    wk = hashlib.pbkdf2_hmac('sha256', pw.encode(), salt, ITER, 32)
    cfg = {'v': 1, 'spki': b64(spki), 'salt': b64(salt), 'iter': ITER, 'iv': b64(iv),
           'wrapped': b64(aes_cbc(wk, iv, pk8))}
    os.makedirs(os.path.dirname(CFG), exist_ok=True)
    with open(CFG, 'w') as f:
        json.dump(cfg, f, indent=1)
    print('wrote', CFG, '(safe to commit: it holds no password and no usable private key)')


def enabled():
    return os.path.exists(CFG)


class Session:
    """One random AES key per build, shared by every page and file of that build."""

    def __init__(self):
        self.cfg = json.load(open(CFG))
        self.key = os.urandom(32)
        with tempfile.TemporaryDirectory() as t:
            der, pem = os.path.join(t, 'p.der'), os.path.join(t, 'p.pem')
            open(der, 'wb').write(base64.b64decode(self.cfg['spki']))
            ossl('pkey', '-pubin', '-inform', 'DER', '-in', der, '-out', pem)
            self.ek = ossl('pkeyutl', '-encrypt', '-pubin', '-inkey', pem, '-pkeyopt', 'rsa_padding_mode:oaep',
                           '-pkeyopt', 'rsa_oaep_md:sha256', '-pkeyopt', 'rsa_mgf1_md:sha256', data=self.key)

    def blob(self, data):
        iv = os.urandom(16)
        return iv + aes_cbc(self.key, iv, data)

    def page(self, html, title):
        c = self.cfg
        lock = {'salt': c['salt'], 'iter': c['iter'], 'iv': c['iv'], 'wrapped': c['wrapped'],
                'ek': b64(self.ek), 'ct': b64(self.blob(html.encode('utf-8')))}
        return LOADER.replace('__TITLE__', title).replace('/*__LOCK__*/', json.dumps(lock, separators=(',', ':')))


def encrypt_site(pages, file_dirs):
    """pages: [(path, title)] of built html files. file_dirs: dirs whose files become <name>.enc."""
    s = Session()
    for p, title in pages:
        html = open(p, encoding='utf-8').read()
        open(p, 'w', encoding='utf-8').write(s.page(html, title))
        print(f'  locked {os.path.relpath(p, ROOT)}')
    n, stuck = 0, []
    for d in file_dirs:
        for dp, _, fs in os.walk(d):
            for fn in fs:
                if fn.endswith('.enc'):
                    continue
                src = os.path.join(dp, fn)
                open(src + '.enc', 'wb').write(s.blob(open(src, 'rb').read()))
                n += 1
                try:
                    os.remove(src)
                except OSError:
                    stuck.append(os.path.relpath(src, ROOT))
    print(f'  locked {n} download files')
    if stuck:
        print('  WARNING: could not delete these plain files; remove them before pushing (git rm):')
        for x in stuck:
            print('   ', x)
    return stuck


LOADER = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><meta name="robots" content="noindex,nofollow">
<title>__TITLE__ · NIC Industries</title>
<style>
:root{--bg:#0a0a0a;--card:#141414;--line:#262626;--txt:#e5e5e5;--dim:#8a8a8a;--acc:#ff9800;--red:#ef4444}
body{margin:0;background:var(--bg);color:var(--txt);font:14px/1.5 system-ui,-apple-system,sans-serif;display:flex;min-height:100vh;align-items:center;justify-content:center;padding:16px;box-sizing:border-box}
form{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:28px;width:100%;max-width:340px;box-sizing:border-box}
h1{font-size:15px;margin:0 0 4px;letter-spacing:.04em;text-transform:uppercase}p{color:var(--dim);margin:0 0 18px;font-size:13px}
input[type=password]{width:100%;box-sizing:border-box;background:#0d0d0d;border:1px solid var(--line);color:var(--txt);border-radius:6px;padding:10px 12px;font-size:15px}
input[type=password]:focus{outline:none;border-color:var(--acc)}
label{display:flex;gap:8px;align-items:center;color:var(--dim);font-size:13px;margin:12px 0 16px}
button{width:100%;background:var(--acc);color:#111;border:0;border-radius:6px;padding:10px;font-weight:600;font-size:14px;cursor:pointer}
button:disabled{opacity:.6;cursor:wait}#err{color:var(--red);font-size:13px;min-height:18px;margin-top:10px}
</style></head><body>
<form id="f" autocomplete="on" style="display:none">
<h1>Cerakote Ops</h1><p>Enter the dashboard password.</p>
<input type="text" name="username" value="cerakote-ops" autocomplete="username" hidden>
<input type="password" id="pw" autocomplete="current-password" autofocus required>
<label><input type="checkbox" id="rm" checked> Remember on this device</label>
<button id="go" type="submit">Unlock</button><div id="err"></div></form>
<noscript>This page needs JavaScript.</noscript>
<script>
(function(){
var L=/*__LOCK__*/, S=crypto.subtle, KEY='cerakote_ops_key';
function u8(b){var s=atob(b),a=new Uint8Array(s.length);for(var i=0;i<s.length;i++)a[i]=s.charCodeAt(i);return a}
function b64(buf){var a=new Uint8Array(buf),s='';for(var i=0;i<a.length;i+=8192)s+=String.fromCharCode.apply(null,a.subarray(i,i+8192));return btoa(s)}
function get(){try{return localStorage.getItem(KEY)}catch(e){return null}}
function put(v){try{v?localStorage.setItem(KEY,v):localStorage.removeItem(KEY)}catch(e){}}
async function fromPassword(pw){
  var base=await S.importKey('raw',new TextEncoder().encode(pw),'PBKDF2',false,['deriveKey']);
  var wk=await S.deriveKey({name:'PBKDF2',salt:u8(L.salt),iterations:L.iter,hash:'SHA-256'},base,{name:'AES-CBC',length:256},false,['decrypt']);
  return S.decrypt({name:'AES-CBC',iv:u8(L.iv)},wk,u8(L.wrapped));
}
async function open(pk8){
  var priv=await S.importKey('pkcs8',pk8,{name:'RSA-OAEP',hash:'SHA-256'},false,['decrypt']);
  var raw=await S.decrypt({name:'RSA-OAEP'},priv,u8(L.ek));
  var k=await S.importKey('raw',raw,'AES-CBC',false,['decrypt']);
  var ct=u8(L.ct);
  var pt=await S.decrypt({name:'AES-CBC',iv:ct.slice(0,16)},k,ct.slice(16));
  window.__opsKey=k;
  var html=new TextDecoder().decode(pt);
  document.open();document.write(html);document.close();
  window.addEventListener('click',dl,true); // document.open() drops window listeners, so attach after
}
// Download links (a[download] under files/) fetch <file>.enc and decrypt it in the browser.
function dl(e){
  var a=e.target&&e.target.closest?e.target.closest('a[download]'):null;
  if(!a||!window.__opsKey)return;var h=a.getAttribute('href')||'';
  if(!h||h==='#'||/^(blob:|data:|https?:)/.test(h))return;
  e.preventDefault();
  fetch(h+'.enc').then(function(r){if(!r.ok)throw Error(r.status);return r.arrayBuffer()}).then(function(b){
    b=new Uint8Array(b);return S.decrypt({name:'AES-CBC',iv:b.slice(0,16)},window.__opsKey,b.slice(16))
  }).then(function(pt){
    var x=document.createElement('a');x.href=URL.createObjectURL(new Blob([pt]));x.download=decodeURIComponent(h.split('/').pop());
    document.body.appendChild(x);x.click();setTimeout(function(){URL.revokeObjectURL(x.href);x.remove()},2000);
  }).catch(function(err){alert('Download failed: '+err.message)});
}
var f=document.getElementById('f'),go=document.getElementById('go'),er=document.getElementById('err');
function ask(){f.style.display='';document.getElementById('pw').focus()}
f.onsubmit=async function(e){e.preventDefault();go.disabled=true;er.textContent='';
  var keep=document.getElementById('rm').checked;
  try{var pk8=await fromPassword(document.getElementById('pw').value);put(keep?b64(pk8):null);await open(pk8);}
  catch(x){put(null);er.textContent='Wrong password.';go.disabled=false;}
};
// Wait for the loader to finish loading: document.open() during the initial load is not reliable.
function start(){var saved=get();if(saved){open(u8(saved)).catch(function(){put(null);ask()})}else ask()}
if(document.readyState==='complete')start();else window.addEventListener('load',start,{once:true});
})();
</script></body></html>
"""

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else ''
    if cmd == 'setup':
        if '--stdin' in sys.argv:
            pw = sys.stdin.readline().rstrip('\n')
        else:
            pw = getpass.getpass('Dashboard password (12+ chars): ')
            if pw != getpass.getpass('Again: '):
                sys.exit('passwords do not match')
        setup(pw)
    elif cmd == 'status':
        print('locked builds: ON' if enabled() else 'locked builds: OFF (no config/lock.json)')
    else:
        print(__doc__)
