"""Oyun Launcher eklentileri: oyun başlatma ayarları, Windows ile başlatma,
mağaza (Steam / Epic / EA app / Riot / Xbox) oyunlarını otomatik bulma.

Launcher ile aynı klasöre koy. Tarama ve autostart yalnızca Windows'ta çalışır.
"""
import ctypes
import json
import os
import re
import shlex
import string
import subprocess
import sys
import time
import traceback
from datetime import datetime
from xml.etree import ElementTree as ET

IS_WIN = sys.platform.startswith("win")
APP_NAME = "OyunLauncher"
RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"
NO_WINDOW = 0x08000000  # CREATE_NO_WINDOW

# ------------------------------------------------------------------ BAŞLATMA


def is_uri(p):
    p = p or ""
    return bool(re.match(r"^[a-z][a-z0-9+.\-]+://", p, re.I)) or p.lower().startswith("shell:")


def is_launchable(g):
    p = g.get("path", "")
    return bool(p) and (is_uri(p) or os.path.exists(p))


def display_target(g):
    p = g.get("path", "")
    if not p:
        return ""
    if is_uri(p):
        return g.get("source") or "Mağaza bağlantısı"
    return os.path.basename(p)


def launch_game(g):
    """Oyunu başlatır. Dönüş: "store" (mağaza/EA app bağlantısıyla) ya da "direct" (exe ile).
    EA oyunları (anti-cheat'li olanlar dahil) varsayılan olarak EA app üzerinden açılır;
    g['direct'] True ise ya da EA app/oyun kimliği bulunamazsa exe doğrudan çalıştırılır."""
    path = g.get("path", "")
    args = (g.get("args") or "").strip()
    admin = bool(g.get("admin"))
    if IS_WIN:
        if g.get("source") == "EA app" and not g.get("direct") and ea_app_installed():
            uri = ea_launch_uri(g)
            if uri:
                os.startfile(uri)
                return "store"
        if is_uri(path):
            # Mağaza bağlantıları kendi istemcisi üzerinden açılır
            os.startfile(path)
            return "store"
        cwd = g.get("install_dir") or os.path.dirname(path) or None
        verb = "runas" if admin else "open"
        r = ctypes.windll.shell32.ShellExecuteW(None, verb, path, args or None, cwd, 1)
        if r <= 32:
            if admin and r == 5:
                raise OSError("Yönetici izni verilmedi (UAC iptal edildi).")
            raise OSError(f"Başlatılamadı (ShellExecute kodu {r}).")
        return "direct"
    subprocess.Popen([path] + (shlex.split(args) if args else []),
                     cwd=os.path.dirname(path) or None)
    return "direct"


# ------------------------------------------------------------ WINDOWS İLE AÇ


def autostart_command():
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}" --minimized'
    exe = sys.executable
    pyw = os.path.join(os.path.dirname(exe), "pythonw.exe")
    if os.path.exists(pyw):
        exe = pyw
    return f'"{exe}" "{os.path.abspath(sys.argv[0])}" --minimized'


def is_autostart():
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_READ) as k:
            winreg.QueryValueEx(k, APP_NAME)
            return True
    except OSError:
        return False


def set_autostart(enable):
    if not IS_WIN:
        raise OSError("Bu özellik yalnızca Windows'ta çalışır.")
    import winreg
    with winreg.OpenKey(winreg.HKEY_CURRENT_USER, RUN_KEY, 0, winreg.KEY_SET_VALUE) as k:
        if enable:
            winreg.SetValueEx(k, APP_NAME, 0, winreg.REG_SZ, autostart_command())
        else:
            try:
                winreg.DeleteValue(k, APP_NAME)
            except FileNotFoundError:
                pass


# ----------------------------------------------------------- MAĞAZA TARAMASI


def _item(name, path, source, store_id="", args="", install_dir=""):
    return {"name": name, "path": path, "args": args, "install_dir": install_dir,
            "source": source, "store_id": str(store_id)}


def _reg_value(root, sub, name):
    import winreg
    try:
        with winreg.OpenKey(root, sub, 0, winreg.KEY_READ) as k:
            return winreg.QueryValueEx(k, name)[0]
    except OSError:
        return None


def _program_data():
    return os.environ.get("ProgramData", r"C:\ProgramData")


def _drives():
    return [f"{d}:\\" for d in string.ascii_uppercase if os.path.exists(f"{d}:\\")]


# ---- Steam
_STEAM_SKIP = re.compile(r"steamworks common|proton|steam linux runtime|steamvr", re.I)


def scan_steam():
    import winreg
    steam = (_reg_value(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")
             or _reg_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"))
    if not steam or not os.path.isdir(steam):
        return []
    steam = os.path.normpath(steam)
    libs = {steam}
    vdf = os.path.join(steam, "steamapps", "libraryfolders.vdf")
    if os.path.exists(vdf):
        with open(vdf, "r", encoding="utf-8", errors="replace") as f:
            for m in re.finditer(r'"path"\s+"([^"]+)"', f.read()):
                libs.add(os.path.normpath(m.group(1).replace("\\\\", "\\")))
    out = []
    for lib in libs:
        apps = os.path.join(lib, "steamapps")
        if not os.path.isdir(apps):
            continue
        for fn in os.listdir(apps):
            if not (fn.startswith("appmanifest_") and fn.endswith(".acf")):
                continue
            try:
                with open(os.path.join(apps, fn), "r", encoding="utf-8", errors="replace") as f:
                    txt = f.read()
                appid = re.search(r'"appid"\s+"(\d+)"', txt).group(1)
                name = re.search(r'"name"\s+"([^"]*)"', txt).group(1)
                inst = re.search(r'"installdir"\s+"([^"]*)"', txt).group(1)
            except Exception:
                continue
            if appid == "228980" or _STEAM_SKIP.search(name):
                continue
            idir = os.path.join(apps, "common", inst)
            out.append(_item(name, f"steam://rungameid/{appid}", "Steam", appid,
                             install_dir=idir if os.path.isdir(idir) else ""))
    return out


def steam_art_urls(appid):
    base = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/"
    return {"kapak": base + "library_600x900.jpg", "arkaplan": base + "library_hero.jpg"}


# ---- Epic Games
def scan_epic():
    mdir = os.path.join(_program_data(), "Epic", "EpicGamesLauncher", "Data", "Manifests")
    if not os.path.isdir(mdir):
        return []
    out = []
    for fn in os.listdir(mdir):
        if not fn.endswith(".item"):
            continue
        try:
            with open(os.path.join(mdir, fn), "r", encoding="utf-8", errors="replace") as f:
                d = json.load(f)
        except Exception:
            continue
        cats = d.get("AppCategories") or []
        if cats and "games" not in cats:
            continue
        if d.get("bIsIncompleteInstall"):
            continue
        name = d.get("DisplayName") or d.get("AppName")
        loc = d.get("InstallLocation", "")
        if not name or not loc or not os.path.isdir(loc):
            continue
        app, ns, cid = d.get("AppName"), d.get("CatalogNamespace"), d.get("CatalogItemId")
        if app and ns and cid:
            path = f"com.epicgames.launcher://apps/{ns}%3A{cid}%3A{app}?action=launch&silent=true"
        else:
            exe = os.path.join(loc, d.get("LaunchExecutable", ""))
            if not os.path.isfile(exe):
                continue
            path = exe
        out.append(_item(name, path, "Epic Games", app or "", install_dir=loc))
    return out


# ---- EA app / Origin
REPORT = []  # son taramanın raporu (tarama_raporu.txt'ye yazılır)


def _log(msg):
    REPORT.append(msg)


def _base_dir():
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))


REPORT_FILE = os.path.join(_base_dir(), "tarama_raporu.txt")

_EXE_SKIP = re.compile(r"unins|crash|setup|redist|cleanup|activation|touchup|report|helper|launcher_|"
                       r"eaanticheat|easyanticheat|battleye|vc_?redist|dxsetup|dotnet|prereq|"
                       r"installer|updater|ealink|eadesktop|unitycrash|bootstrap", re.I)
_EA_LAUNCHER_NAMES = re.compile(r"^(ea app|ea desktop|origin|ea help|ea anticheat)", re.I)
_SKIP_SUBDIRS = {"__installer", "redist", "_commonredist", "support", "directx", "vcredist", "dotnet",
                 "easyanticheat", "battleye", "eaanticheat", "engine", "thirdparty", "crashreport",
                 "crashpad", "installers"}


def _best_exe(folder):
    """Yalnızca klasörün kendisindeki en büyük uygun exe."""
    best, size = None, -1
    try:
        for fn in os.listdir(folder):
            if fn.lower().endswith(".exe") and not _EXE_SKIP.search(fn):
                s = os.path.getsize(os.path.join(folder, fn))
                if s > size:
                    best, size = os.path.join(folder, fn), s
    except OSError:
        pass
    return best


def _find_game_exe(folder, name="", max_depth=3):
    """Alt klasörlere de bakarak oyunun ana exe'sini bulur.
    Adı oyun adına benzeyen, büyük ve ana klasöre yakın exe tercih edilir."""
    want = _norm(name)
    base = folder.rstrip("\\/")
    base_depth = base.count(os.sep)
    best, best_score = None, None
    for root, dirs, files in os.walk(folder):
        depth = root.rstrip("\\/").count(os.sep) - base_depth
        dirs[:] = [d for d in dirs if d.lower() not in _SKIP_SUBDIRS] if depth < max_depth else []
        for fn in files:
            if not fn.lower().endswith(".exe") or _EXE_SKIP.search(fn):
                continue
            fp = os.path.join(root, fn)
            try:
                size = os.path.getsize(fp)
            except OSError:
                continue
            stem = _norm(os.path.splitext(fn)[0])
            score = size / 1e6 - depth * 30
            if want and stem and (stem in want or want in stem):
                score += 1000
            if best_score is None or score > best_score:
                best, best_score = fp, score
    return best


def _ea_title(folder):
    """Oyun adını __Installer\\installerdata.xml içinden okur (yoksa None)."""
    xml = os.path.join(folder, "__Installer", "installerdata.xml")
    if not os.path.exists(xml):
        return None
    try:
        root = ET.parse(xml).getroot()
        titles = [e for e in root.iter() if e.tag.lower().endswith("gametitle") and (e.text or "").strip()]
        for e in titles:  # tercihen İngilizce
            if (e.get("locale") or "").lower().startswith("en"):
                return e.text.strip()
        if titles:
            return titles[0].text.strip()
    except Exception:
        pass
    return None


def _safe_listdir(p):
    try:
        return [os.path.join(p, n) for n in os.listdir(p)]
    except OSError:
        return []


# Taramada girilmeyecek klasörler (sistem, diğer mağazalar, gereksiz büyük yerler)
_PRUNE = re.compile(r"^(windows.*|\$recycle\.bin|system volume information|programdata|users|windowsapps|"
                    r"xboxgames|steamapps|steamlibrary|steam|epic games|appdata|node_modules|\.git|recovery|"
                    r"perflogs|msocache|common files|internet explorer|microsoft.*|dotnet|msbuild|"
                    r"reference assemblies|nvidia.*|amd|intel|temp|tmp|modifiablewindowsapps)$", re.I)


def _has_installer(folder):
    return os.path.exists(os.path.join(folder, "__Installer", "installerdata.xml"))


def _walk_installers(roots, max_depth, deadline):
    """roots altında (max_depth derinliğe kadar) __Installer\\installerdata.xml içeren
    oyun klasörlerini bulur. Bulunan oyun klasörünün içine girmez."""
    found, seen = [], set()
    stack = [(r, 0) for r in roots]
    while stack:
        if time.time() > deadline:
            _log("  ! tarama süre sınırına takıldı, bazı klasörler atlanmış olabilir")
            break
        path, depth = stack.pop()
        key = os.path.normcase(path)
        if key in seen:
            continue
        seen.add(key)
        if _has_installer(path):
            found.append(path)
            continue
        if depth >= max_depth:
            continue
        try:
            with os.scandir(path) as it:
                for e in it:
                    try:
                        if e.is_dir(follow_symlinks=False) and not _PRUNE.match(e.name):
                            stack.append((e.path, depth + 1))
                    except OSError:
                        pass
        except OSError:
            pass
    return found


_PATH_RE = re.compile(r'[A-Za-z]:(?:\\\\|\\|/)[^"<>|*?\r\n\t]{3,}')


def _ea_config_dirs(deadline):
    """EA app'in kendi veri klasörlerindeki dosyalardan geçen yolları toplar;
    oyun hangi klasöre kurulmuş olursa olsun ipucu verir."""
    bases = [os.path.join(_program_data(), "EA Desktop"),
             os.path.join(os.environ.get("LOCALAPPDATA", ""), "Electronic Arts", "EA Desktop"),
             os.path.join(_program_data(), "Electronic Arts"),
             os.path.join(_program_data(), "Origin")]
    out = set()
    for b in bases:
        if not b or not os.path.isdir(b):
            continue
        for root, dirs, files in os.walk(b):
            if root[len(b):].count(os.sep) > 3 or time.time() > deadline:
                dirs[:] = []
                continue
            for fn in files:
                if not fn.lower().endswith((".json", ".xml", ".txt", ".ini", ".cfg", ".yaml", ".yml", ".mfst")):
                    continue
                fp = os.path.join(root, fn)
                try:
                    if os.path.getsize(fp) > 2_000_000:
                        continue
                    with open(fp, "r", encoding="utf-8", errors="ignore") as f:
                        txt = f.read()
                except OSError:
                    continue
                for m in _PATH_RE.findall(txt):
                    p = m.replace("\\\\", "\\").replace("/", "\\").strip().rstrip("\\")
                    while len(p) > 3 and not os.path.exists(p):
                        p = p.rsplit("\\", 1)[0]
                    if len(p) <= 3:
                        continue
                    if os.path.isfile(p):
                        p = os.path.dirname(p)
                    if re.match(r"^[A-Za-z]:\\(windows|users|programdata)(\\|$)", p, re.I):
                        continue
                    out.add(p)
                    if len(out) > 300:
                        return out
    return out


def _ea_installer_folders(quick=False):
    deadline = time.time() + (12 if quick else 45)
    found = []
    # 1) tüm sürücüler, 4 klasör derinliğe kadar (hızlı modda atlanır)
    if not quick:
        found += _walk_installers(_drives(), 4, deadline)
    # 2) EA app veri dosyalarında geçen yollar (yukarı doğru da bakılır)
    extra_roots = []
    for p in _ea_config_dirs(deadline):
        q = p
        for _ in range(4):
            if _has_installer(q):
                found.append(q)
                break
            nq = os.path.dirname(q)
            if nq == q or len(nq) <= 3:
                extra_roots.append(p)
                break
            q = nq
    found += _walk_installers(extra_roots[:60], 2, deadline)
    return found


def _ea_registry_folders():
    import winreg
    res = []
    subs = (r"SOFTWARE\WOW6432Node\EA Games", r"SOFTWARE\EA Games",
            r"SOFTWARE\WOW6432Node\Electronic Arts", r"SOFTWARE\Electronic Arts")
    for view in (winreg.KEY_WOW64_64KEY, winreg.KEY_WOW64_32KEY):
        for sub in subs:
            try:
                k = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, sub, 0, winreg.KEY_READ | view)
            except OSError:
                continue
            with k:
                i = 0
                while True:
                    try:
                        name = winreg.EnumKey(k, i)
                    except OSError:
                        break
                    i += 1
                    try:
                        with winreg.OpenKey(k, name, 0, winreg.KEY_READ | view) as sk:
                            folder = None
                            for vn in ("Install Dir", "InstallDir", "Install Path", "InstallPath"):
                                try:
                                    folder = winreg.QueryValueEx(sk, vn)[0]
                                    break
                                except OSError:
                                    continue
                    except OSError:
                        continue
                    if folder and os.path.isdir(folder.rstrip("\\/")):
                        res.append((name, folder.rstrip("\\/")))
    return res


def _ea_uninstall_folders():
    """Uninstall kayıtlarında yayıncısı Electronic Arts olan oyunlar."""
    import winreg
    res = []
    key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall"
    for root, view in ((winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_64KEY),
                       (winreg.HKEY_LOCAL_MACHINE, winreg.KEY_WOW64_32KEY),
                       (winreg.HKEY_CURRENT_USER, 0)):
        try:
            k = winreg.OpenKey(root, key, 0, winreg.KEY_READ | view)
        except OSError:
            continue
        with k:
            i = 0
            while True:
                try:
                    sub = winreg.EnumKey(k, i)
                except OSError:
                    break
                i += 1
                if sub.lower().startswith("steam app"):
                    continue
                try:
                    with winreg.OpenKey(k, sub, 0, winreg.KEY_READ | view) as sk:
                        def val(n):
                            try:
                                return winreg.QueryValueEx(sk, n)[0]
                            except OSError:
                                return ""
                        pub, name, loc = val("Publisher"), val("DisplayName"), val("InstallLocation")
                except OSError:
                    continue
                if "electronic arts" not in str(pub).lower() or not name or not loc:
                    continue
                loc = str(loc).strip('"').rstrip("\\/")
                if _EA_LAUNCHER_NAMES.search(name) or "steamapps" in loc.lower() or not os.path.isdir(loc):
                    continue
                res.append((name, loc))
    return res


def scan_ea(quick=False):
    out, seen = [], set()

    def add(name, folder):
        folder = os.path.normpath(folder)
        key = os.path.normcase(folder)
        if key in seen or not os.path.isdir(folder):
            return
        title = _ea_title(folder) or name or os.path.basename(folder)
        exe = _find_game_exe(folder, title)
        if not exe:
            _log(f"  ! EA klasörü bulundu ama exe bulunamadı: {folder}")
            return
        seen.add(key)
        offers = ea_offer_ids(folder)
        out.append(_item(title, exe, "EA app", offers[0] if offers else "", install_dir=folder))

    for folder in _ea_installer_folders(quick):
        add(None, folder)
    for name, folder in _ea_registry_folders():
        add(name, folder)
    for name, folder in _ea_uninstall_folders():
        add(name, folder)
    bases = [os.environ.get("ProgramFiles", ""), os.environ.get("ProgramFiles(x86)", "")] + _drives()
    for root in bases:
        for base in ("EA Games", "Origin Games", "Electronic Arts"):
            p = os.path.join(root, base) if root else ""
            if p and os.path.isdir(p):
                for sub in os.listdir(p):
                    add(sub, os.path.join(p, sub))
    return out


def scan_folder(path):
    """Kullanıcının seçtiği klasörü tarar: EA oyunları (installerdata.xml) varsa onları,
    yoksa klasörü tek oyun (ya da alt klasörlerini ayrı oyunlar) olarak ele alır."""
    REPORT.clear()
    _log(f"Klasör taraması: {path}")
    path = os.path.normpath(path)
    out, seen = [], set()

    def add(title, folder, exe, source, sid=""):
        key = os.path.normcase(folder)
        if key in seen:
            return
        seen.add(key)
        out.append(_item(title, exe, source, sid, install_dir=folder))
        _log(f"  + {title} -> {exe}")

    for f in _walk_installers([path], 5, time.time() + 60):
        title = _ea_title(f) or os.path.basename(f)
        exe = _find_game_exe(f, title)
        if exe:
            add(title, f, exe, "EA app", (ea_offer_ids(f) or [""])[0])
        else:
            _log(f"  ! exe bulunamadı: {f}")
    if not out:
        if _best_exe(path):
            add(os.path.basename(path), path, _find_game_exe(path, os.path.basename(path)), "Klasör")
        else:
            for child in _safe_listdir(path):
                if not os.path.isdir(child) or os.path.basename(child).lower() in _SKIP_SUBDIRS:
                    continue
                exe = _find_game_exe(child, os.path.basename(child), max_depth=2)
                if exe:
                    add(os.path.basename(child), child, exe, "Klasör")
    _write_report()
    return sorted(out, key=lambda x: x["name"].lower())


def _write_report():
    try:
        with open(REPORT_FILE, "w", encoding="utf-8") as f:
            f.write("\n".join(REPORT) + "\n")
    except OSError:
        pass


# ---- Riot Client
_RIOT_NAMES = {"valorant": "VALORANT", "league_of_legends": "League of Legends",
               "bacon": "Legends of Runeterra", "lor": "Legends of Runeterra"}


def scan_riot():
    rc_json = os.path.join(_program_data(), "Riot Games", "RiotClientInstalls.json")
    meta = os.path.join(_program_data(), "Riot Games", "Metadata")
    if not (os.path.exists(rc_json) and os.path.isdir(meta)):
        return []
    try:
        with open(rc_json, "r", encoding="utf-8") as f:
            info = json.load(f)
        rc = info.get("rc_default") or info.get("rc_live")
    except Exception:
        return []
    if not rc or not os.path.exists(rc):
        return []
    out = []
    for folder in os.listdir(meta):
        if "." not in folder:
            continue
        product, patchline = folder.rsplit(".", 1)
        idir = ""
        mdir = os.path.join(meta, folder)
        try:
            for fn in os.listdir(mdir):
                if fn.endswith(".yaml"):
                    with open(os.path.join(mdir, fn), "r", encoding="utf-8", errors="replace") as f:
                        m = re.search(r'product_install_full_path:\s*"?([^"\r\n]+)"?', f.read())
                    if m:
                        idir = m.group(1).strip()
                        break
        except OSError:
            continue
        if not idir or not os.path.isdir(idir):
            continue
        name = _RIOT_NAMES.get(product, product.replace("_", " ").title())
        out.append(_item(name, rc, "Riot", f"{product}.{patchline}",
                         args=f"--launch-product={product} --launch-patchline={patchline}",
                         install_dir=idir))
    return out


# ---- Xbox / Microsoft Store
def _run_ps(script, timeout=60):
    full = "[Console]::OutputEncoding=[Text.Encoding]::UTF8; " + script
    try:
        raw = subprocess.check_output(["powershell", "-NoProfile", "-Command", full],
                                      creationflags=NO_WINDOW, timeout=timeout,
                                      stderr=subprocess.DEVNULL).decode("utf-8", "replace").strip()
        data = json.loads(raw) if raw else []
    except Exception:
        return []
    return [data] if isinstance(data, dict) else data


def _appx_family_names():
    # Konum filtresi YOK: Xbox oyunlarının paket yolu çoğu zaman WindowsApps altında görünür
    data = _run_ps("Get-AppxPackage | Select-Object Name,PackageFamilyName | ConvertTo-Json -Compress")
    return {str(d.get("Name")).lower(): d.get("PackageFamilyName") for d in data if d.get("Name")}


def _start_apps():
    data = _run_ps("Get-StartApps | Select-Object Name,AppID | ConvertTo-Json -Compress", timeout=40)
    return {str(d.get("Name")).lower(): d.get("AppID") for d in data if d.get("Name") and d.get("AppID")}


def _xbox_roots():
    roots = []
    for d in _drives():
        for sub in ("XboxGames", os.path.join("Program Files", "ModifiableWindowsApps")):
            p = os.path.join(d, sub)
            if os.path.isdir(p):
                roots.append(p)
    return roots


def scan_xbox():
    roots = _xbox_roots()
    if not roots:
        return []
    pfn = _appx_family_names()
    start = None  # yalnızca gerekirse yüklenir
    out, seen = [], set()
    for root in roots:
        for game in _safe_listdir(root):
            content = os.path.join(game, "Content")
            if not os.path.isdir(content):
                content = game
            cfg = os.path.join(content, "MicrosoftGame.Config")
            if not os.path.exists(cfg):
                continue
            try:
                xml = ET.parse(cfg).getroot()
                ident = (xml.find("Identity").get("Name") or "")
                app = xml.find(".//Application")
                app_id = (app.get("Id") if app is not None else None) or "Game"
                vis = xml.find(".//ShellVisuals")
                name = vis.get("DefaultDisplayName") if vis is not None else ""
            except Exception:
                continue
            if not name or name.startswith("ms-resource"):
                name = os.path.basename(game)
            if ident.lower() in seen:
                continue
            fam = pfn.get(ident.lower())
            path = None
            if fam:
                path = f"shell:AppsFolder\\{fam}!{app_id}"
            else:
                if start is None:
                    start = _start_apps()
                aid = start.get(name.lower())
                if aid:
                    path = f"shell:AppsFolder\\{aid}"
                else:
                    helper = os.path.join(content, "gamelaunchhelper.exe")
                    path = helper if os.path.exists(helper) else _best_exe(content)
            if not path:
                continue
            seen.add(ident.lower())
            out.append(_item(name, path, "Xbox", ident, install_dir=content))
    return out


SCANNERS = (("Steam", scan_steam), ("Epic Games", scan_epic), ("EA app", scan_ea),
            ("Riot", scan_riot), ("Xbox", scan_xbox))


def scan_all(quick=False):
    """Tüm mağazaları tarar. Bir mağaza hata verirse diğerleri devam eder.
    Ayrıntılar tarama_raporu.txt dosyasına yazılır."""
    if not IS_WIN:
        return []
    REPORT.clear()
    _log(("Otomatik tarama: " if quick else "Tarama: ") + datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
    found = []
    for name, fn in SCANNERS:
        t0 = time.time()
        try:
            items = fn(quick=True) if (quick and fn is scan_ea) else fn()
            _log(f"[{name}] {len(items)} oyun ({time.time() - t0:.1f} sn)")
            for it in items:
                _log(f"  + {it['name']}  ->  {it['path']}")
            found.extend(items)
        except Exception:
            _log(f"[{name}] HATA:\n" + traceback.format_exc())
    found.sort(key=lambda x: x["name"].lower())
    _write_report()
    return found


# ------------------------------------------------------- MAĞAZA GÖRSELLERİ
# art_candidates(g) -> {"kapak": [...], "arkaplan": [...], "ikon": [...]}
# Her aday bir URL, bir dosya yolu ya da "exe:<yol>" (exe'nin kendi ikonu) olur.
# Adaylar sırayla denenir, ilk çalışan kullanılır.
import base64
import io
import urllib.parse
import urllib.request

_UA = {"User-Agent": "Mozilla/5.0"}


def _http_get(url, timeout=15):
    req = urllib.request.Request(url, headers=_UA)
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return r.read()


def _http_json(url):
    return json.loads(_http_get(url).decode("utf-8", "replace"))


def _norm(s):
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def _steam_cdn(appid):
    b = f"https://cdn.cloudflare.steamstatic.com/steam/apps/{appid}/"
    return {"kapak": [b + "library_600x900.jpg", b + "library_600x900_2x.jpg", b + "header.jpg"],
            "arkaplan": [b + "library_hero.jpg", b + "page_bg_generated_v6b.jpg", b + "header.jpg"]}


def _steam_appid_by_name(name):
    """Steam mağazasında oyun adına göre arar. Yanlış görsel almamak için
    yalnızca adı yeterince benzeyen sonucu kabul eder."""
    try:
        url = ("https://store.steampowered.com/api/storesearch/?term="
               + urllib.parse.quote(name) + "&l=english&cc=us")
        items = _http_json(url).get("items", [])
    except Exception:
        return None
    want = _norm(name)
    if not want:
        return None
    for it in items:
        have = _norm(it.get("name"))
        if not have:
            continue
        if have == want:
            return it.get("id")
        short, long_ = sorted((want, have), key=len)
        if short in long_ and len(short) / len(long_) >= 0.6:
            return it.get("id")
    return None


def _exe_for_icon(g):
    idir = g.get("install_dir") or ""
    path = g.get("path", "")
    name = g.get("name", "")
    if path.lower().endswith(".exe") and os.path.isfile(path) and g.get("source") not in ("Riot",):
        return path
    if idir and os.path.isdir(idir):
        exe = _find_game_exe(idir, name)
        if exe:
            return exe
    if path.lower().endswith(".exe") and os.path.isfile(path):
        return path
    return None


def _steam_root():
    try:
        import winreg
        p = (_reg_value(winreg.HKEY_CURRENT_USER, r"Software\Valve\Steam", "SteamPath")
             or _reg_value(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\WOW6432Node\Valve\Steam", "InstallPath"))
        return os.path.normpath(p) if p else None
    except Exception:
        return None


def _epic_images(g):
    m = re.search(r"apps/[^%]+%3A([^%]+)%3A", g.get("path", ""))
    cid = m.group(1) if m else None
    cache = os.path.join(_program_data(), "Epic", "EpicGamesLauncher", "Data", "Catalog", "catcache.bin")
    res = {"kapak": [], "arkaplan": [], "ikon": []}
    if not cid or not os.path.exists(cache):
        return res
    try:
        with open(cache, "rb") as f:
            items = json.loads(base64.b64decode(f.read()).decode("utf-8", "replace"))
    except Exception:
        return res
    for it in items:
        if it.get("id") != cid:
            continue
        by = {}
        for im in it.get("keyImages") or []:
            by.setdefault(im.get("type"), im.get("url"))
        pick = lambda *types: [by[t] for t in types if by.get(t)]
        res["kapak"] = pick("DieselGameBoxTall", "OfferImageTall", "DieselStoreFrontTall")
        res["arkaplan"] = pick("DieselStoreFrontWide", "DieselGameBox", "OfferImageWide")
        res["ikon"] = pick("Thumbnail")
        break
    return res


def _xbox_images(g):
    res = {"kapak": [], "arkaplan": [], "ikon": []}
    content = g.get("install_dir") or ""
    cfg = os.path.join(content, "MicrosoftGame.Config")
    if not os.path.exists(cfg):
        return res
    try:
        xml = ET.parse(cfg).getroot()
    except Exception:
        return res
    # 1) Microsoft Store kataloğu (StoreId ile): poster, hero, logo
    sid = (xml.findtext(".//StoreId") or "").strip()
    if sid:
        try:
            data = _http_json("https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds="
                              + urllib.parse.quote(sid) + "&market=US&languages=en-US")
            imgs = data["Products"][0]["LocalizedProperties"][0]["Images"]
            by = {}
            for im in imgs:
                u = im.get("Uri") or ""
                if u.startswith("//"):
                    u = "https:" + u
                if u:
                    by.setdefault(im.get("ImagePurpose"), u)
            pick = lambda *p: [by[x] for x in p if by.get(x)]
            res["kapak"] = pick("Poster", "BoxArt")
            res["arkaplan"] = pick("SuperHeroArt", "TitledHeroArt", "BrandedKeyArt")
            res["ikon"] = pick("Logo", "Tile")
        except Exception:
            pass
    # 2) Oyun klasöründeki yerel görseller (yedek)
    vis = xml.find(".//ShellVisuals")
    if vis is not None:
        def local(*attrs):
            out = []
            for a in attrs:
                rel = vis.get(a)
                if rel:
                    p = os.path.join(content, rel.replace("/", os.sep))
                    if os.path.isfile(p):
                        out.append(p)
            return out
        res["arkaplan"] += local("SplashScreenImage")
        res["ikon"] += local("Square480x480Logo", "Square150x150Logo", "StoreLogo")
        res["kapak"] += local("Square480x480Logo")
    return res


def art_candidates(g):
    src = g.get("source", "")
    res = {"kapak": [], "arkaplan": [], "ikon": []}
    steam_id = None
    if src == "Steam":
        steam_id = g.get("store_id")
    elif src == "Epic Games":
        res = _epic_images(g)
    elif src == "Xbox":
        res = _xbox_images(g)
    if steam_id:
        for k, v in _steam_cdn(steam_id).items():
            res[k] += v
    # Mağazanın kendi görseli yoksa aynı oyunu Steam mağazasında ara
    if src != "Steam" and not (res["kapak"] and res["arkaplan"]):
        sid = _steam_appid_by_name(g.get("name", ""))
        if sid:
            for k, v in _steam_cdn(sid).items():
                res[k] += v
    # İkon: önce oyunun exe ikonu, olmazsa mağaza görseli
    exe = _exe_for_icon(g)
    if exe:
        res["ikon"].insert(0, "exe:" + exe)
    if src == "Steam" and steam_id:
        root = _steam_root()
        if root:
            for cand in (os.path.join(root, "appcache", "librarycache", f"{steam_id}_icon.jpg"),):
                if os.path.isfile(cand):
                    res["ikon"].append(cand)
    return res


def _exe_icon_image(path, size=256):
    """Exe'nin içindeki en büyük ikonu PIL görüntüsü olarak döndürür (yalnızca Windows)."""
    if not IS_WIN:
        return None
    from ctypes import wintypes
    from PIL import Image

    class ICONINFO(ctypes.Structure):
        _fields_ = [("fIcon", wintypes.BOOL), ("xHotspot", wintypes.DWORD),
                    ("yHotspot", wintypes.DWORD), ("hbmMask", wintypes.HBITMAP),
                    ("hbmColor", wintypes.HBITMAP)]

    class BITMAP(ctypes.Structure):
        _fields_ = [("bmType", wintypes.LONG), ("bmWidth", wintypes.LONG),
                    ("bmHeight", wintypes.LONG), ("bmWidthBytes", wintypes.LONG),
                    ("bmPlanes", wintypes.WORD), ("bmBitsPixel", wintypes.WORD),
                    ("bmBits", wintypes.LPVOID)]

    class BMIH(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG),
                    ("biHeight", wintypes.LONG), ("biPlanes", wintypes.WORD),
                    ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD),
                    ("biClrImportant", wintypes.DWORD)]

    u32, g32 = ctypes.windll.user32, ctypes.windll.gdi32
    u32.PrivateExtractIconsW.argtypes = [wintypes.LPCWSTR, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.POINTER(wintypes.HICON), ctypes.POINTER(wintypes.UINT),
                                         wintypes.UINT, wintypes.UINT]
    u32.PrivateExtractIconsW.restype = wintypes.UINT
    u32.GetIconInfo.argtypes = [wintypes.HICON, ctypes.POINTER(ICONINFO)]
    u32.GetDC.argtypes = [wintypes.HWND]
    u32.GetDC.restype = wintypes.HDC
    u32.ReleaseDC.argtypes = [wintypes.HWND, wintypes.HDC]
    u32.DestroyIcon.argtypes = [wintypes.HICON]
    g32.GetObjectW.argtypes = [wintypes.HGDIOBJ, ctypes.c_int, ctypes.c_void_p]
    g32.GetDIBits.argtypes = [wintypes.HDC, wintypes.HBITMAP, wintypes.UINT, wintypes.UINT,
                              ctypes.c_void_p, ctypes.c_void_p, wintypes.UINT]
    g32.DeleteObject.argtypes = [wintypes.HGDIOBJ]

    hicon, iid = wintypes.HICON(), wintypes.UINT()
    if u32.PrivateExtractIconsW(path, 0, size, size, ctypes.byref(hicon), ctypes.byref(iid), 1, 0) < 1 \
            or not hicon.value:
        return None
    info = ICONINFO()
    hdc = u32.GetDC(None)
    try:
        if not u32.GetIconInfo(hicon, ctypes.byref(info)) or not info.hbmColor:
            return None
        bm = BITMAP()
        g32.GetObjectW(info.hbmColor, ctypes.sizeof(bm), ctypes.byref(bm))
        w, h = bm.bmWidth, bm.bmHeight
        bmi = BMIH(ctypes.sizeof(BMIH), w, -h, 1, 32, 0, 0, 0, 0, 0, 0)
        buf = ctypes.create_string_buffer(w * h * 4)
        if not g32.GetDIBits(hdc, info.hbmColor, 0, h, buf, ctypes.byref(bmi), 0):
            return None
        img = Image.frombuffer("RGBA", (w, h), buf, "raw", "BGRA", 0, 1).copy()
        if img.getchannel("A").getextrema()[1] == 0:  # alfa kanalı olmayan eski ikonlar
            img.putalpha(255)
        return img
    finally:
        u32.ReleaseDC(None, hdc)
        if info.hbmColor:
            g32.DeleteObject(info.hbmColor)
        if info.hbmMask:
            g32.DeleteObject(info.hbmMask)
        u32.DestroyIcon(hicon)


def _exe_icon_ps(path):
    """Yedek yöntem: PowerShell ile ikonu çıkarır (32x32 gibi daha küçük olabilir)."""
    if not IS_WIN:
        return None
    import tempfile
    from PIL import Image
    fd, out = tempfile.mkstemp(suffix=".png")
    os.close(fd)
    try:
        p = path.replace("'", "''")
        o = out.replace("'", "''")
        ps = ("Add-Type -AssemblyName System.Drawing; "
              f"$i=[System.Drawing.Icon]::ExtractAssociatedIcon('{p}'); "
              f"$i.ToBitmap().Save('{o}')")
        subprocess.run(["powershell", "-NoProfile", "-Command", ps], creationflags=NO_WINDOW,
                       timeout=25, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        img = Image.open(out).convert("RGBA")
        img.load()
        return img
    except Exception:
        return None
    finally:
        try:
            os.remove(out)
        except OSError:
            pass


def _exe_icon_any(path):
    try:
        img = _exe_icon_image(path)
    except Exception:
        img = None
    return img or _exe_icon_ps(path)


def load_art(cand):
    """Bir adayı PIL RGBA görüntüsüne çevirir; olmazsa None."""
    from PIL import Image
    try:
        if cand.startswith("exe:"):
            return _exe_icon_any(cand[4:])
        if re.match(r"^https?://", cand, re.I):
            return Image.open(io.BytesIO(_http_get(cand))).convert("RGBA")
        if os.path.isfile(cand):
            return Image.open(cand).convert("RGBA")
    except Exception:
        pass
    return None


# ------------------------------------------------- EA APP İLE BAŞLATMA
def ea_offer_ids(folder):
    """Oyunun __Installer\\installerdata.xml dosyasından EA içerik/teklif kimliklerini okur.
    Önce Origin.OFR.* / OFB-* biçimli kimlikler, sonra sayısal contentID'ler döner."""
    xml = os.path.join(folder or "", "__Installer", "installerdata.xml")
    try:
        with open(xml, "r", encoding="utf-8", errors="ignore") as f:
            txt = f.read()
    except OSError:
        return []
    ids = []

    def add(v):
        v = (v or "").strip()
        if v and v not in ids:
            ids.append(v)

    for m in re.finditer(r"Origin\.OFR\.\d+\.\d+|OFB-[A-Za-z]+:\d+", txt):
        add(m.group(0))
    try:
        for e in ET.fromstring(txt.lstrip("\ufeff")).iter():
            if e.tag.lower().endswith("contentid"):
                add(e.text)
    except Exception:
        pass
    return ids


def ea_app_installed():
    """EA app / Origin'in origin2:// bağlantısını kaydettiği kontrol edilir."""
    if not IS_WIN:
        return False
    import winreg
    try:
        with winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, "origin2"):
            return True
    except OSError:
        return False


def ea_launch_uri(g):
    offer = (g.get("store_id") or "").strip()
    if not offer:
        ids = ea_offer_ids(g.get("install_dir") or os.path.dirname(g.get("path", "")))
        if ids:
            offer = ids[0]
            g["store_id"] = offer  # sonraki sefer için sakla
    if not offer:
        return None
    return "origin2://game/launch/?offerIds=" + urllib.parse.quote(offer, safe=":.-") + "&autoDownload=1"


# ------------------------------------------------- OYUN SÜRECİ TAKİBİ
_PROC_API = None
_INVALID_HANDLE = ctypes.c_void_p(-1).value


def _proc_api():
    global _PROC_API
    if _PROC_API:
        return _PROC_API
    from ctypes import wintypes
    k32 = ctypes.WinDLL("kernel32", use_last_error=True)

    class PE(ctypes.Structure):
        _fields_ = [("dwSize", wintypes.DWORD), ("cntUsage", wintypes.DWORD),
                    ("th32ProcessID", wintypes.DWORD), ("th32DefaultHeapID", ctypes.c_size_t),
                    ("th32ModuleID", wintypes.DWORD), ("cntThreads", wintypes.DWORD),
                    ("th32ParentProcessID", wintypes.DWORD), ("pcPriClassBase", wintypes.LONG),
                    ("dwFlags", wintypes.DWORD), ("szExeFile", ctypes.c_wchar * 260)]

    k32.CreateToolhelp32Snapshot.argtypes = [wintypes.DWORD, wintypes.DWORD]
    k32.CreateToolhelp32Snapshot.restype = wintypes.HANDLE
    k32.Process32FirstW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.Process32FirstW.restype = wintypes.BOOL
    k32.Process32NextW.argtypes = [wintypes.HANDLE, ctypes.POINTER(PE)]
    k32.Process32NextW.restype = wintypes.BOOL
    k32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    k32.OpenProcess.restype = wintypes.HANDLE
    k32.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR,
                                               ctypes.POINTER(wintypes.DWORD)]
    k32.QueryFullProcessImageNameW.restype = wintypes.BOOL
    k32.CloseHandle.argtypes = [wintypes.HANDLE]
    _PROC_API = (k32, PE, wintypes)
    return _PROC_API


def _iter_processes():
    """(pid, tam exe yolu) çiftlerini verir. Yalnızca Windows; bağımlılık gerektirmez."""
    if not IS_WIN:
        return
    k32, PE, wintypes = _proc_api()
    snap = k32.CreateToolhelp32Snapshot(0x2, 0)  # TH32CS_SNAPPROCESS
    if not snap or snap == _INVALID_HANDLE:
        return
    try:
        pe = PE()
        pe.dwSize = ctypes.sizeof(PE)
        ok = k32.Process32FirstW(snap, ctypes.byref(pe))
        buf = ctypes.create_unicode_buffer(1024)
        while ok:
            pid = pe.th32ProcessID
            if pid:
                h = k32.OpenProcess(0x1000, False, pid)  # PROCESS_QUERY_LIMITED_INFORMATION
                if h:
                    try:
                        n = wintypes.DWORD(1024)
                        if k32.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)):
                            yield pid, buf.value
                    finally:
                        k32.CloseHandle(h)
            ok = k32.Process32NextW(snap, ctypes.byref(pe))
    finally:
        k32.CloseHandle(snap)


def running_in_dir(folder):
    """folder altındaki bir exe şu an çalışıyor mu?"""
    prefix = os.path.normcase(os.path.normpath(folder)).rstrip("\\/") + os.sep
    me = os.getpid()
    for pid, path in _iter_processes():
        if pid != me and os.path.normcase(path).startswith(prefix):
            return True
    return False


def watch_game(folder, emit, stop, appear_timeout=150, poll=2.0, gone_polls=5):
    """Oyun klasöründen bir süreç başlayana ve sonra tamamen bitene kadar bekler.
    emit('started' | 'ended' | 'timeout') ile haber verir; stop Event'i ile iptal edilir."""
    t0 = time.time()
    seen, absent = False, 0
    while not stop.is_set():
        try:
            running = running_in_dir(folder)
        except Exception:
            running = False
        if running:
            absent = 0
            if not seen:
                seen = True
                emit("started")
        elif seen:
            absent += 1
            if absent >= gone_polls:  # başlatıcı exe'ler kısa süre kaybolabilir
                emit("ended")
                return
        elif time.time() - t0 > appear_timeout:
            emit("timeout")
            return
        stop.wait(poll)


# ------------------------------------------------- OYUN KUMANDASI (XInput)
class _XPad(ctypes.Structure):
    _fields_ = [("wButtons", ctypes.c_ushort), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class _XState(ctypes.Structure):
    _fields_ = [("dwPacketNumber", ctypes.c_uint32), ("Gamepad", _XPad)]


class Gamepad:
    """Xbox / XInput uyumlu kumandaları okur (PlayStation kumandaları için Steam Input
    ya da DS4Windows gibi bir XInput çevirici gerekir). poll() düğme olaylarının listesini döner:
    up down left right a b x y lb rb lt rt start back. Yön tuşları/sol çubuk basılı tutulunca tekrarlar."""
    BTN = {0x1: "up", 0x2: "down", 0x4: "left", 0x8: "right", 0x10: "start", 0x20: "back",
           0x100: "lb", 0x200: "rb", 0x1000: "a", 0x2000: "b", 0x4000: "x", 0x8000: "y",
           0x10000: "lt", 0x20000: "rt"}  # lt/rt: tetikler (sanal bit)
    DIRS = ("up", "down", "left", "right")
    DEAD = 16000
    FIRST_DELAY, REPEAT = 0.38, 0.11

    def __init__(self):
        self.connected = False
        self.index = None
        self._prev = 0
        self._hold = {}
        self._lib = None
        self._tried = False
        self._last_scan = 0.0
        self.sticks = (0.0, 0.0, 0.0, 0.0)   # sağ x,y  sol x,y  (-1..1; kapak eğimi için)

    def _load(self):
        if self._tried:
            return self._lib
        self._tried = True
        if not IS_WIN:
            return None
        for dll in ("xinput1_4", "xinput1_3", "xinput9_1_0"):
            try:
                lib = ctypes.WinDLL(dll)
                lib.XInputGetState.argtypes = [ctypes.c_uint32, ctypes.POINTER(_XState)]
                lib.XInputGetState.restype = ctypes.c_uint32
                self._lib = lib
                break
            except (OSError, AttributeError):
                continue
        return self._lib

    def _get(self, i):
        st = _XState()
        if self._lib.XInputGetState(i, ctypes.byref(st)) == 0:
            return st.Gamepad
        return None

    def poll(self):
        if not self._load():
            return []
        now = time.time()
        if self.index is None:
            if now - self._last_scan < 2.0:  # bağlı olmayan yuvaları sık sorma
                return []
            self._last_scan = now
            for i in range(4):
                if self._get(i) is not None:
                    self.index, self.connected = i, True
                    break
            return []
        pad = self._get(self.index)
        if pad is None:
            self.index, self.connected = None, False
            self.sticks = (0.0, 0.0, 0.0, 0.0)
            self._prev = 0
            self._hold.clear()
            return []
        btn = pad.wButtons
        self.sticks = (pad.sThumbRX / 32768.0, pad.sThumbRY / 32768.0,
                       pad.sThumbLX / 32768.0, pad.sThumbLY / 32768.0)
        if pad.sThumbLY > self.DEAD:
            btn |= 0x1
        elif pad.sThumbLY < -self.DEAD:
            btn |= 0x2
        if pad.sThumbLX < -self.DEAD:
            btn |= 0x4
        elif pad.sThumbLX > self.DEAD:
            btn |= 0x8
        if pad.bLeftTrigger > 160:
            btn |= 0x10000
        if pad.bRightTrigger > 160:
            btn |= 0x20000
        events = []
        pressed = btn & ~self._prev
        self._prev = btn
        for mask, name in self.BTN.items():
            if name in self.DIRS:
                if btn & mask:
                    h = self._hold.get(name)
                    if h is None:
                        self._hold[name] = [now, now]
                        events.append(name)
                    elif now - h[0] >= self.FIRST_DELAY and now - h[1] >= self.REPEAT:
                        h[1] = now
                        events.append(name)
                else:
                    self._hold.pop(name, None)
            elif pressed & mask:
                events.append(name)
        return events


# ------------------------------------------------- SİSTEM TEPSİSİ
class Tray:
    """pystray ile tepsi simgesi (pip install pystray). Yoksa start() False döner."""

    def __init__(self):
        self.icon = None

    @staticmethod
    def available():
        import importlib.util
        return importlib.util.find_spec("pystray") is not None

    def start(self, image, title, on_show, on_quit):
        try:
            import pystray
        except Exception:
            return False
        self.stop()
        try:
            menu = pystray.Menu(
                pystray.MenuItem("Launcher'ı göster", lambda icon, item: on_show(), default=True),
                pystray.MenuItem("Çıkış", lambda icon, item: on_quit()))
            self.icon = pystray.Icon("OyunLauncher", image, title, menu)
            self.icon.run_detached()
            return True
        except Exception:
            self.icon = None
            return False

    def stop(self):
        if self.icon is not None:
            try:
                self.icon.stop()
            except Exception:
                pass
            self.icon = None



# ===================================================================== OYUN BİLGİSİ
# fetch_game_info(g, name, only=None) -> {"results": [...], "errors": {...}, "tried": [...]}
# Her sonuç: {"source","found","publisher","developer","release","genre","desc","score","art"}
# Kaynaklar: Steam, Epic Games, Microsoft Store (Xbox), GOG, Riot (yerel tablo), Vikipedi/Wikidata.
# EA app ve Riot'un herkese açık bir mağaza API'si yok; bu oyunlar diğer kaynaklarda aranır.
import html as _html
import threading

INFO_SOURCES = ("Steam", "Epic Games", "Microsoft Store", "GOG", "Riot", "Vikipedi")

_MONTHS_TR = ("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz", "Ağustos",
              "Eylül", "Ekim", "Kasım", "Aralık")


def _clean(t):
    t = re.sub(r"<[^>]+>", " ", t or "")
    return re.sub(r"\s+", " ", _html.unescape(t)).strip()


def _date_tr(iso):
    """2020-06-02[T...] -> '2 Haziran 2020'. Çözemezse metni olduğu gibi döner."""
    m = re.match(r"^\+?(\d{4})-(\d{2})-(\d{2})", iso or "")
    if not m:
        return (iso or "").strip()
    y, mo, d = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if not 1 <= mo <= 12:
        return str(y)
    return f"{d} {_MONTHS_TR[mo - 1]} {y}" if d else f"{_MONTHS_TR[mo - 1]} {y}"


def _title_score(want, have):
    """0..1 arası ad benzerliği (1 = aynı)."""
    a, b = _norm(want), _norm(have)
    if not a or not b:
        return 0.0
    if a == b:
        return 1.0
    short, long_ = sorted((a, b), key=len)
    if short in long_:
        return 0.55 + 0.4 * len(short) / len(long_)
    import difflib
    return difflib.SequenceMatcher(None, a, b).ratio() * 0.8


def _best(items, name, key, minimum=0.6):
    """Listeden adı en çok benzeyen öğeyi seçer; yeterince benzemiyorsa None."""
    best, best_s = None, 0.0
    for it in items or []:
        sc = _title_score(name, key(it))
        if sc > best_s:
            best, best_s = it, sc
    return (best, best_s) if best is not None and best_s >= minimum else (None, 0.0)


def _post_json(url, payload, timeout=15):
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"),
                                 headers={**_UA, "Content-Type": "application/json"})
    with urllib.request.urlopen(req, timeout=timeout) as r:
        return json.loads(r.read().decode("utf-8", "replace"))


def _res(source, found, score, **kw):
    r = {"source": source, "found": found, "score": round(score, 2), "publisher": "", "developer": "",
         "release": "", "genre": "", "desc": "", "art": {}}
    r.update({k: v for k, v in kw.items() if v})
    return r


def _info_steam(g, name):
    sid = g.get("store_id") if g.get("source") == "Steam" else None
    score = 1.0
    if not sid:
        items = _http_json("https://store.steampowered.com/api/storesearch/?term="
                           + urllib.parse.quote(name) + "&l=turkish&cc=tr").get("items", [])
        it, score = _best(items, name, lambda x: x.get("name"))
        if not it:
            return None
        sid = it["id"]
    d = _http_json(f"https://store.steampowered.com/api/appdetails?appids={sid}&l=turkish&cc=tr")
    data = (d.get(str(sid)) or {}).get("data") or {}
    if not data:
        return None
    return _res("Steam", data.get("name") or name, score,
                publisher=", ".join(data.get("publishers") or []),
                developer=", ".join(data.get("developers") or []),
                release=(data.get("release_date") or {}).get("date", ""),
                genre=", ".join(x.get("description", "") for x in (data.get("genres") or [])),
                desc=_clean(data.get("short_description")),
                art=_steam_cdn(sid))


_EPIC_QUERY = """query q($keywords:String,$country:String!,$locale:String,$count:Int){
 Catalog{searchStore(keywords:$keywords,country:$country,locale:$locale,count:$count,
  category:"games/edition/base|bundles/games|editors"){
  elements{title description effectiveDate seller{name}
   keyImages{type url} customAttributes{key value}}}}}"""


def _info_epic(g, name):
    data = _post_json("https://store.epicgames.com/graphql",
                      {"query": _EPIC_QUERY, "variables": {"keywords": name, "country": "TR",
                                                           "locale": "tr-TR", "count": 8}})
    els = (((data.get("data") or {}).get("Catalog") or {}).get("searchStore") or {}).get("elements") or []
    it, score = _best(els, name, lambda x: x.get("title"))
    if not it:
        return None
    attrs = {a.get("key"): a.get("value") for a in it.get("customAttributes") or []}
    by = {}
    for im in it.get("keyImages") or []:
        by.setdefault(im.get("type"), im.get("url"))
    pick = lambda *t: [by[x] for x in t if by.get(x)]
    return _res("Epic Games", it.get("title") or name, score,
                publisher=attrs.get("publisherName") or (it.get("seller") or {}).get("name", ""),
                developer=attrs.get("developerName", ""),
                release=_date_tr(it.get("effectiveDate", "")),
                desc=_clean(it.get("description")),
                art={"kapak": pick("DieselGameBoxTall", "OfferImageTall", "DieselStoreFrontTall"),
                     "arkaplan": pick("DieselStoreFrontWide", "DieselGameBox", "OfferImageWide")})


def _ms_product(big_id):
    d = _http_json("https://displaycatalog.mp.microsoft.com/v7.0/products?bigIds="
                   + urllib.parse.quote(big_id) + "&market=TR&languages=tr-TR,en-US")
    return (d.get("Products") or [None])[0]


def _ms_find_id(name):
    """Microsoft Store arama önerileriyle oyunun BigId'sini bulur."""
    u = ("https://www.microsoft.com/services/api/v3/suggest?market=tr-TR&clientId="
         "7F27B536-CF6B-4C65-8638-A0F8CBDFCA65&sources=Microsoft-Terms,Iris-Products,DCatAll-Products"
         "&filter=ExcludeDemos&counts=5,1,8&query=" + urllib.parse.quote(name))
    cands = []
    for rs in _http_json(u).get("ResultSets") or []:
        for sg in rs.get("Suggests") or []:
            bid = next((m.get("Value") for m in sg.get("Metas") or [] if m.get("Key") == "BigCatalogId"), None)
            if bid and sg.get("Title"):
                cands.append({"id": bid, "title": sg["Title"]})
    return _best(cands, name, lambda x: x["title"])


def _info_ms(g, name):
    score = 1.0
    bid = g.get("store_id_ms")
    if not bid and g.get("source") == "Xbox":
        cfg = os.path.join(g.get("install_dir") or "", "MicrosoftGame.Config")
        try:
            bid = (ET.parse(cfg).getroot().findtext(".//StoreId") or "").strip()
        except Exception:
            bid = ""
    if not bid:
        it, score = _ms_find_id(name)
        bid = it["id"] if it else None
    if not bid:
        return None
    p = _ms_product(bid)
    if not p:
        return None
    lp = (p.get("LocalizedProperties") or [{}])[0]
    mp = (p.get("MarketProperties") or [{}])[0]
    cats = (p.get("Properties") or {}).get("Categories") or [(p.get("Properties") or {}).get("Category")]
    imgs = {}
    for im in lp.get("Images") or []:
        u = im.get("Uri") or ""
        imgs.setdefault(im.get("ImagePurpose"), ("https:" + u) if u.startswith("//") else u)
    pick = lambda *t: [imgs[x] for x in t if imgs.get(x)]
    return _res("Microsoft Store", lp.get("ProductTitle") or name, score,
                publisher=lp.get("PublisherName", ""), developer=lp.get("DeveloperName", ""),
                release=_date_tr(mp.get("OriginalReleaseDate", "")),
                genre=", ".join(c for c in cats if c),
                desc=_clean(lp.get("ShortDescription") or lp.get("ProductDescription")),
                art={"kapak": pick("Poster", "BoxArt"), "arkaplan": pick("SuperHeroArt", "TitledHeroArt")})


def _info_gog(g, name):
    d = _http_json("https://catalog.gog.com/v1/catalog?limit=6&order=desc%3Ascore&productType=in%3Agame"
                   "&countryCode=TR&locale=en-US&currencyCode=USD&query=like%3A" + urllib.parse.quote(name))
    it, score = _best(d.get("products"), name, lambda x: x.get("title"))
    if not it:
        return None
    return _res("GOG", it.get("title") or name, score,
                publisher=", ".join(it.get("publishers") or []),
                developer=", ".join(it.get("developers") or []),
                release=_date_tr(it.get("releaseDate", "")),
                genre=", ".join(x.get("name", "") for x in it.get("genres") or []),
                art={"kapak": [it["coverVertical"]] if it.get("coverVertical") else []})


# Riot'un herkese açık katalog API'si yok; bilinen oyunlar için yerel tablo
_RIOT_INFO = {
    "valorant": ("VALORANT", "Riot Games", "Riot Games", "2 Haziran 2020", "Nişancı (FPS), Taktik",
                 "Beş kişilik takımların bomba kurma/etkisizleştirme üzerine oynadığı, yetenekli ajanlara "
                 "sahip taktiksel birinci şahıs nişancı oyunu."),
    "league_of_legends": ("League of Legends", "Riot Games", "Riot Games", "27 Ekim 2009", "MOBA, Strateji",
                          "İki takımın Nexus'u yıkmak için karşı karşıya geldiği, 160'tan fazla şampiyonlu "
                          "çevrimiçi MOBA oyunu."),
    "bacon": ("Legends of Runeterra", "Riot Games", "Riot Games", "30 Nisan 2020", "Kart oyunu, Strateji",
              "League of Legends evreninde geçen, sırayla saldırı ve savunmanın olduğu koleksiyonluk kart oyunu."),
}
_RIOT_INFO["lor"] = _RIOT_INFO["bacon"]


def _info_riot(g, name):
    if g.get("source") != "Riot":
        return None
    pid = (g.get("store_id") or "").split(".")[0].lower()
    row = _RIOT_INFO.get(pid)
    if not row:
        return None
    return _res("Riot", row[0], 1.0, publisher=row[1], developer=row[2], release=row[3],
                genre=row[4], desc=row[5])


_WD_GENRE_BLOCK = ("video game", "video oyunu")


def _info_wiki(g, name):
    """Wikidata (yayıncı, geliştirici, tür, tarih) + Vikipedi özeti (açıklama). Anahtar gerekmez."""
    def wd(params):
        q = urllib.parse.urlencode({**params, "format": "json"})
        return _http_json("https://www.wikidata.org/w/api.php?" + q)

    found = None
    for lang in ("tr", "en"):
        res = wd({"action": "wbsearchentities", "search": name, "language": lang, "type": "item", "limit": 8})
        for it in res.get("search") or []:
            desc = (it.get("description") or "").lower()
            if "video game" in desc or "video oyun" in desc or "oyun" in desc or "game" in desc:
                found = (it, _title_score(name, it.get("label")))
                if found[1] >= 0.6:
                    break
        if found and found[1] >= 0.6:
            break
    if not found or found[1] < 0.6:
        return None
    qid = found[0]["id"]
    ent = wd({"action": "wbgetentities", "ids": qid, "props": "claims|sitelinks|labels",
              "languages": "tr|en", "sitefilter": "trwiki|enwiki"})["entities"][qid]
    claims = ent.get("claims") or {}

    def ids(prop):
        out = []
        for c in claims.get(prop) or []:
            v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value")
            if isinstance(v, dict) and v.get("id"):
                out.append(v["id"])
        return out

    dev, pub, gen = ids("P178"), ids("P123"), ids("P136")
    want = list(dict.fromkeys(dev + pub + gen))[:14]
    labels = {}
    if want:
        le = wd({"action": "wbgetentities", "ids": "|".join(want), "props": "labels",
                 "languages": "tr|en"}).get("entities") or {}
        for k, v in le.items():
            lb = v.get("labels") or {}
            labels[k] = (lb.get("tr") or lb.get("en") or {}).get("value", "")
    names = lambda L, n=3: ", ".join(x for x in dict.fromkeys(labels.get(i, "") for i in L) if x)
    rel = ""
    for c in claims.get("P577") or []:
        v = ((c.get("mainsnak") or {}).get("datavalue") or {}).get("value") or {}
        t = v.get("time", "")
        if t:
            rel = _date_tr(t.lstrip("+")) if v.get("precision", 11) >= 11 else re.sub(r"^\+?(\d{4}).*", r"\1", t)
            break
    desc = ""
    sl = ent.get("sitelinks") or {}
    for wiki, host in (("trwiki", "tr.wikipedia.org"), ("enwiki", "en.wikipedia.org")):
        title = (sl.get(wiki) or {}).get("title")
        if title:
            try:
                sm = _http_json(f"https://{host}/api/rest_v1/page/summary/"
                                + urllib.parse.quote(title.replace(" ", "_"), safe=""))
                desc = _clean(sm.get("extract"))
                if len(desc) > 420:
                    desc = desc[:417].rsplit(" ", 1)[0] + "..."
                if desc:
                    break
            except Exception:
                pass
    label = ((ent.get("labels") or {}).get("tr") or (ent.get("labels") or {}).get("en") or {}).get("value", name)
    return _res("Vikipedi", label, found[1], publisher=names(pub), developer=names(dev),
                release=rel, genre=names(gen), desc=desc)


_PROVIDERS = {"Steam": _info_steam, "Epic Games": _info_epic, "Microsoft Store": _info_ms,
              "GOG": _info_gog, "Riot": _info_riot, "Vikipedi": _info_wiki}
_FIELDS = ("publisher", "developer", "release", "genre", "desc")


def provider_order(g):
    """Oyunun kendi mağazası en önde, sonra diğerleri."""
    own = {"Steam": "Steam", "Epic Games": "Epic Games", "Xbox": "Microsoft Store", "Riot": "Riot"}.get(
        g.get("source", ""))
    order = [own] if own else []
    order += [s for s in ("Steam", "Epic Games", "Microsoft Store", "GOG", "Riot", "Vikipedi") if s != own]
    return order


def merge_results(results, order):
    """Alan alan, öncelik sırasındaki ilk dolu değeri alır (sonuçlar içinde yalnızca eşleşmesi iyi olanlar)."""
    rank = {s: i for i, s in enumerate(order)}
    ranked = sorted(results, key=lambda r: (rank.get(r["source"], 99)))
    out, src = {}, {}
    for f in _FIELDS:
        for r in ranked:
            if r.get(f):
                out[f], src[f] = r[f], r["source"]
                break
    art = {}
    for r in ranked:
        for k, v in (r.get("art") or {}).items():
            art.setdefault(k, []).extend(v)
    return {"source": "Birleşik", "found": "Tüm kaynaklar birleştirildi", "score": 1.0,
            "fields_from": src, "art": art, **{f: out.get(f, "") for f in _FIELDS}}


def fetch_game_info(g, name, only=None, progress=None):
    """Tüm kaynakları paralel sorgular. only: tek bir kaynak adı (None = hepsi)."""
    order = provider_order(g)
    names = [only] if only else order
    results, errors = [], {}
    lock = threading.Lock()

    def run(src):
        if progress:
            progress(src)
        try:
            r = _PROVIDERS[src](g, name)
        except Exception as e:
            with lock:
                errors[src] = f"{type(e).__name__}: {e}"[:160]
            return
        if r and any(r.get(f) for f in _FIELDS):
            with lock:
                results.append(r)

    ths = [threading.Thread(target=run, args=(s,), daemon=True) for s in names]
    for t in ths:
        t.start()
    for t in ths:
        t.join(25)
    results.sort(key=lambda r: (order.index(r["source"]) if r["source"] in order else 99))
    # Kötü eşleşmeleri (adı pek benzemeyen) birleştirmeye katma
    good = [r for r in results if r["score"] >= 0.7]
    return {"results": results, "merged": merge_results(good, order) if len(good) > 1 else None,
            "errors": errors, "tried": names}
