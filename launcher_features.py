"""Oyun Launcher: yapılandırma yedeği, telefondan kumanda (yerel web sunucusu) ve
boşta kalma ekranı yardımcıları.

Launcher ile aynı klasöre koy. Ek paket gerekmez (QR kodu için isteğe bağlı: pip install qrcode).
"""
import hmac
import ipaddress
import json
import os
import secrets
import socket
import threading
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

# ===================================================================== DOSYA YAZMA


def atomic_write(path, data):
    """Önce geçici dosyaya yazıp yerine koyar: yazma sırasında kapanma/elektrik kesilmesi
    yapılandırmayı yarım bırakıp bozamaz."""
    if isinstance(data, str):
        data = data.encode("utf-8")
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(data)
        f.flush()
        try:
            os.fsync(f.fileno())
        except OSError:
            pass
    try:
        os.replace(tmp, path)
    except OSError:  # antivirüs / OneDrive dosyayı kısa süre kilitlemiş olabilir
        with open(path, "wb") as f:
            f.write(data)
        try:
            os.remove(tmp)
        except OSError:
            pass


# ===================================================================== YAPILANDIRMA YEDEĞİ

BACKUP_KEEP = 5
_BK_PREFIX = "launcher_config_"


def backup_dir(config_file):
    return os.path.join(os.path.dirname(os.path.abspath(config_file)), "backups")


def _read_valid(path):
    """(ham_bayt, veri) döner; dosya yok ya da bozuksa (None, None)."""
    try:
        with open(path, "rb") as f:
            raw = f.read()
        return raw, json.loads(raw.decode("utf-8"))
    except Exception:
        return None, None


def _count_games(data):
    if isinstance(data, list):
        return len(data)
    if isinstance(data, dict) and isinstance(data.get("games"), list):
        return len(data["games"])
    return 0


def list_backups(config_file):
    """Yedekleri yeniden eskiye döner: {path, name, time, games, valid, size}."""
    d = backup_dir(config_file)
    try:
        names = os.listdir(d)
    except OSError:
        return []
    out = []
    for n in names:
        if not (n.startswith(_BK_PREFIX) and n.endswith(".json")):
            continue
        p = os.path.join(d, n)
        raw, data = _read_valid(p)
        try:
            when = datetime.strptime(n[len(_BK_PREFIX):-5][:15], "%Y%m%d_%H%M%S")
        except ValueError:
            try:
                when = datetime.fromtimestamp(os.path.getmtime(p))
            except OSError:
                continue
        out.append({"path": p, "name": n, "time": when, "valid": data is not None,
                    "games": _count_games(data) if data is not None else -1,
                    "size": len(raw) if raw else 0})
    out.sort(key=lambda b: b["name"], reverse=True)
    return out


def _prune(config_file, keep):
    for old in list_backups(config_file)[keep:]:
        try:
            os.remove(old["path"])
        except OSError:
            pass


def make_backup(config_file, keep=BACKUP_KEEP, force=False):
    """Geçerli yapılandırmanın yedeğini alır, son `keep` yedeği tutar. Yeni yedek yolunu döner.
    force=False iken: dosya bozuksa, son yedekle aynıysa ya da kütüphane boşsa yedek alınmaz
    (böylece iyi yedekler boş/yinelenen kopyalarla silinip gitmez)."""
    raw, data = _read_valid(config_file)
    if raw is None:
        return None
    d = backup_dir(config_file)
    try:
        os.makedirs(d, exist_ok=True)
        existing = list_backups(config_file)
        if not force and existing:
            if _count_games(data) == 0:
                return None
            try:
                with open(existing[0]["path"], "rb") as f:
                    if f.read() == raw:
                        return None
            except OSError:
                pass
        stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        path, n = os.path.join(d, f"{_BK_PREFIX}{stamp}.json"), 2
        while os.path.exists(path):
            path = os.path.join(d, f"{_BK_PREFIX}{stamp}_{n}.json")
            n += 1
        atomic_write(path, raw)
        _prune(config_file, keep)
        return path
    except OSError:
        return None


def restore_backup(config_file, backup_path):
    """Yedeği geçerli yapılandırmanın yerine koyar. Önce yedeği doğrular, sonra mevcut hali de
    yedekler (geri alınabilsin diye)."""
    raw, data = _read_valid(backup_path)
    if raw is None:
        raise ValueError("Yedek dosyası okunamıyor ya da bozuk.")
    make_backup(config_file, force=True)
    atomic_write(config_file, raw)


def quarantine_corrupt(config_file):
    """Okunamayan yapılandırmayı silmeden yanına taşır (üzerine boş dosya yazılmasın)."""
    if not os.path.isfile(config_file):
        return None
    base, ext = os.path.splitext(config_file)
    dst = f"{base}.bozuk_{datetime.now():%Y%m%d_%H%M%S}{ext}"
    try:
        os.replace(config_file, dst)
        return dst
    except OSError:
        return None


# ===================================================================== YARDIMCILAR

_MONTHS_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
              "Eylül", "Ekim", "Kasım", "Aralık")
_DAYS_TR = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")


def date_tr(dt=None):
    dt = dt or datetime.now()
    return f"{dt.day} {_MONTHS_TR[dt.month - 1]} {dt.year}, {_DAYS_TR[dt.weekday()]}"


def qr_image(text, size=300):
    """QR kodunu PIL görüntüsü olarak döndürür; 'qrcode' paketi yoksa None."""
    try:
        import qrcode
        from PIL import Image
        img = qrcode.make(text, box_size=8, border=2)
        img = getattr(img, "get_image", lambda: img)().convert("RGB")
        return img.resize((size, size), Image.NEAREST)
    except Exception:
        return None


# ===================================================================== TELEFONDAN KUMANDA


def new_token():
    return secrets.token_urlsafe(12)


def local_ip():
    for target in ("10.255.255.255", "8.8.8.8"):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            s.connect((target, 1))  # paket gönderilmez; yalnızca doğru ağ arayüzünü seçtirir
            ip = s.getsockname()[0]
            if ip and not ip.startswith("127."):
                return ip
        except OSError:
            pass
        finally:
            s.close()
    try:
        return socket.gethostbyname(socket.gethostname())
    except OSError:
        return "127.0.0.1"


PAGE = r"""<!doctype html>
<html lang="tr"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1,maximum-scale=1,user-scalable=no">
<meta name="theme-color" content="#000000"><title>Oyun Launcher</title>
<style>
:root{--ac:#6366f1;--pn:#111;--ch:#1c1c1c;--tx:#e2e8f0;--mu:#737373}
*{box-sizing:border-box;-webkit-tap-highlight-color:transparent;-webkit-user-select:none;user-select:none}
body{margin:0;background:#000;color:var(--tx);font:16px system-ui,Arial,sans-serif;touch-action:manipulation}
main{max-width:520px;margin:auto;padding:14px 14px 60px}
.card{background:var(--pn);border-radius:16px;padding:14px;margin-bottom:12px}
h1{font-size:22px;margin:2px 0;color:#fff;word-break:break-word}
.mu{color:var(--mu);font-size:13px}
#off{display:none;background:#7f1d1d;color:#fff;padding:8px 12px;border-radius:10px;margin-bottom:10px;font-size:14px}
button{font:inherit;color:var(--tx);background:var(--ch);border:0;border-radius:14px;height:60px;font-size:22px}
button:active{background:#2e2e2e}
.pad{display:grid;grid-template-columns:repeat(3,1fr);gap:10px}
.pad .play{background:var(--ac);color:#000;font-weight:700;font-size:17px}
.pad .sm{font-size:15px}
.row{display:flex;gap:10px;align-items:center}
.row button{flex:1}
input[type=range]{flex:3;accent-color:var(--ac);height:40px}
#q{width:100%;background:var(--ch);border:0;border-radius:12px;color:var(--tx);padding:12px;font-size:16px;margin-bottom:8px;-webkit-user-select:text;user-select:text}
#list{max-height:340px;overflow:auto;position:relative}
.g{padding:12px 10px;border-radius:10px;font-size:16px}
.g.on{background:var(--ch);color:#fff;font-weight:600;border-left:4px solid var(--ac)}
</style></head><body><main>
<div id="off">Bağlantı yok. Launcher açık mı, aynı Wi-Fi'de misin?</div>
<div class="card"><div class="mu" id="src">&nbsp;</div><h1 id="gn">...</h1><div class="mu" id="st">&nbsp;</div></div>
<div class="card"><div class="pad">
<span></span><button id="up">&#9650;</button><span></span>
<button id="left">&#9664;</button><button class="play" id="play">OYNA</button><button id="right">&#9654;</button>
<button id="back" class="sm">&#9638; Izgara</button><button id="down">&#9660;</button><span></span>
</div></div>
<div class="card"><div class="mu" id="tr" style="margin-bottom:8px">&nbsp;</div>
<div class="row"><button id="prev">&#9198;</button><button id="mp">&#9654;</button><button id="next">&#9197;</button></div>
<div class="row" style="margin-top:10px"><button id="vm">&#128265;</button><input id="vol" type="range" min="0" max="100"><button id="vp">&#128266;</button></div></div>
<div class="card"><input id="q" placeholder="Oyun ara..." autocomplete="off"><div id="list"></div></div>
</main><script>
const K=new URLSearchParams(location.search).get('k')||'',H={'X-Key':K,'Content-Type':'application/json'};
const $=i=>document.getElementById(i);
let games=[],gv=null,rg=null,sel=-1,pt=0,drag=false,lastVol=0;
function send(c,a){fetch('/api/cmd',{method:'POST',headers:H,body:JSON.stringify({c:c,a:a})}).catch(()=>{});
 if(navigator.vibrate)navigator.vibrate(10);clearTimeout(pt);pt=setTimeout(poll,300)}
function hold(id,c,a){const el=$(id);let t,i;const stop=()=>{clearTimeout(t);clearInterval(i)};
 el.addEventListener('pointerdown',e=>{e.preventDefault();send(c,a);t=setTimeout(()=>{i=setInterval(()=>send(c,a),130)},400)});
 ['pointerup','pointerleave','pointercancel'].forEach(v=>el.addEventListener(v,stop))}
['up','down','left','right'].forEach(d=>hold(d,'nav',d));
$('play').onclick=()=>send('play');$('back').onclick=()=>send('back');
$('mp').onclick=()=>send('music','toggle');$('prev').onclick=()=>send('music','prev');$('next').onclick=()=>send('music','next');
$('vm').onclick=()=>send('volume',-5);$('vp').onclick=()=>send('volume',5);
$('vol').oninput=e=>{drag=true;const n=Date.now();if(n-lastVol>90){lastVol=n;send('volume_set',+e.target.value)}};
$('vol').onchange=e=>{send('volume_set',+e.target.value);drag=false};
$('q').oninput=render;
function render(){const f=$('q').value.trim().toLowerCase(),L=$('list');L.textContent='';const fr=document.createDocumentFragment();let on=null;
 games.forEach((n,i)=>{if(f&&!n.toLowerCase().includes(f))return;const d=document.createElement('div');
  d.className='g'+(i===sel?' on':'');d.textContent=n;d.onclick=()=>send('select',i);if(i===sel)on=d;fr.appendChild(d)});
 L.appendChild(fr);if(on&&!f)L.scrollTop=on.offsetTop-L.clientHeight/2}
async function poll(){try{const r=await fetch('/api/state',{headers:H});if(!r.ok)throw 0;const s=await r.json();
 $('off').style.display='none';document.documentElement.style.setProperty('--ac',s.accent||'#6366f1');
 $('gn').textContent=s.game||'Oyun yok';$('src').textContent=s.src||'\u00a0';
 $('st').textContent=s.running?('\u25b6 A\u00e7\u0131k: '+s.running):(s.idle?'Bo\u015fta ekran\u0131':(s.away?'Launcher gizli':'\u00a0'));
 $('tr').textContent=s.track?('\u266a '+s.track):'\u00a0';$('mp').textContent=s.playing?'\u23f8':'\u25b6';
 if(!drag)$('vol').value=s.vol;
 if(s.gv!==gv){const g=await fetch('/api/games',{headers:H});games=await g.json();gv=s.gv}
 if(s.sel!==sel||rg!==gv){sel=s.sel;rg=gv;render()}
}catch(e){$('off').style.display='block'}}
poll();setInterval(poll,1500);document.addEventListener('visibilitychange',()=>{if(!document.hidden)poll()});
</script></body></html>
"""


class _Server(ThreadingHTTPServer):
    daemon_threads = True

    def handle_error(self, request, client_address):  # bağlantı kopmaları konsola yazılmasın
        pass


def _make_handler(srv):
    class Handler(BaseHTTPRequestHandler):
        server_version = "OyunLauncher"

        def log_message(self, *a):
            pass

        def _authed(self):
            try:  # yalnızca yerel ağ / aynı bilgisayar
                ip = ipaddress.ip_address(self.client_address[0])
                if not (ip.is_private or ip.is_loopback or ip.is_link_local):
                    return False
            except ValueError:
                return False
            q = parse_qs(urlparse(self.path).query)
            key = self.headers.get("X-Key") or (q.get("k") or [""])[0]
            return hmac.compare_digest(key.encode("utf-8"), srv.token.encode("utf-8"))

        def _send(self, code, body, ctype="application/json; charset=utf-8"):
            if isinstance(body, (dict, list)):
                body = json.dumps(body, ensure_ascii=False)
            if isinstance(body, str):
                body = body.encode("utf-8")
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if not self._authed():
                return self._send(403, "Erisim reddedildi", "text/plain; charset=utf-8")
            path = urlparse(self.path).path
            if path in ("/", "/index.html"):
                self._send(200, PAGE, "text/html; charset=utf-8")
            elif path == "/api/state":
                self._send(200, srv.get_state())
            elif path == "/api/games":
                self._send(200, srv.get_games())
            else:
                self._send(404, "Yok", "text/plain; charset=utf-8")

        def do_POST(self):
            if not self._authed():
                return self._send(403, "Erisim reddedildi", "text/plain; charset=utf-8")
            if urlparse(self.path).path != "/api/cmd":
                return self._send(404, "Yok", "text/plain; charset=utf-8")
            try:
                n = int(self.headers.get("Content-Length") or 0)
                if n > 2048:
                    raise ValueError
                data = json.loads(self.rfile.read(n) or b"{}")
                c, a = str(data.get("c", "")), data.get("a")
            except Exception:
                return self._send(400, "Hatali istek", "text/plain; charset=utf-8")
            srv.on_cmd(c, a)
            self._send(200, {"ok": True})

    return Handler


class RemoteServer:
    """Telefondan kumanda için küçük yerel web sunucusu (yalnızca standart kütüphane).
    Her istek gizli anahtar ister; komutlar launcher'ın arayüz iş parçacığına on_cmd ile iletilir."""

    def __init__(self, token, get_state, get_games, on_cmd, port=8765):
        self.token, self.get_state, self.get_games, self.on_cmd = token, get_state, get_games, on_cmd
        self.port = port
        self.httpd = None

    def start(self):
        handler, last = _make_handler(self), None
        for p in range(self.port, self.port + 10):
            try:
                self.httpd = _Server(("0.0.0.0", p), handler)
                self.port = p
                break
            except OSError as e:
                last = e
        else:
            raise last or OSError("Uygun port bulunamadı.")
        threading.Thread(target=self.httpd.serve_forever, kwargs={"poll_interval": 0.4},
                         daemon=True).start()

    def stop(self, wait=True):
        h, self.httpd = self.httpd, None
        if h is None:
            return

        def close():
            try:
                h.shutdown()
                h.server_close()
            except Exception:
                pass
        if wait:
            close()
        else:
            threading.Thread(target=close, daemon=True).start()

    def url(self):
        return f"http://{local_ip()}:{self.port}/?k={self.token}"
