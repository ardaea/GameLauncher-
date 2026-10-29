import sys
import os
import colorsys
import json
import queue
import random
import re
import shutil
import subprocess
import threading
import time
import urllib.request
from datetime import datetime
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, font as tkfont

os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
from PIL import Image, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageTk

import launcher_extras as ex
import launcher_features as fx
import launcher_vfx as vfx

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)   # exe'nin yanı (config/assets/music burada kalır)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FONT = vfx.setup_fonts(BASE_DIR)   # Inter (fonts/ klasörü) > Segoe UI Variable > Segoe UI
ASSETS_DIR = os.path.join(BASE_DIR, "assets")
MUSIC_DIR = os.path.join(BASE_DIR, "music")
CONFIG_FILE = os.path.join(BASE_DIR, "launcher_config.json")
os.makedirs(ASSETS_DIR, exist_ok=True)
os.makedirs(MUSIC_DIR, exist_ok=True)

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".ico")
VIDEO_EXTS = (".mp4", ".webm", ".mkv", ".avi", ".mov")
AUDIO_EXTS = (".mp3", ".ogg", ".wav", ".flac")
ALL_EXTS = EXTS + VIDEO_EXTS + AUDIO_EXTS
KINDS = ("kapak", "arkaplan", "ikon", "video", "muzik")
PALETTE = ["#1d4ed8", "#0e7490", "#4338ca", "#7c3aed", "#0369a1", "#1e40af", "#155e75", "#3730a3"]

# TAM SİYAH TEMA (OLED)
T = {
    "bg": "#000000", "side": "#0a0a0a", "panel": "#111111",
    "row_hover": "#1a1a1a", "row_sel": "#262626",
    "accent": "#6366f1", "accent_hover": "#818cf8", "accent_dim": "#4f46e5", "accent_fg": "#ffffff",
    "chip": "#1c1c1c", "chip_hover": "#2a2a2a",
    "text": "#e2e8f0", "muted": "#737373", "title": "#ffffff",
    "divider": "#1f1f1f",
}

DEFAULT_CFG = {
    "music_folder": MUSIC_DIR,
    "volume": 0.4,
    "shuffle": True,
    "pause_on_launch": True,
    "ui_sounds": True,
    "fullscreen": True,        # açılışta tam ekran
    "tray_on_launch": True,
    "auto_scan": True,
    "dynamic_accent": True,
    "gamepad": True,
    "fx_motion": True,        # kapak eğimi/büyümesi/parıltısı, çapraz solma, hero geçişleri
    "fx_launch": True,        # OYNA basınca kapağın ekranı kaplama geçişi
    "glass_tint": 150,        # cam panel koyu zemin opaklığı (0-255): düşük = daha saydam
    "hero_bright": 0.3,       # detay ekranı arka plan parlaklığı (0.1-1.0)
    "liste": True,            # kütüphane: True = Explorer tarzı liste + ayrıntı paneli, False = kapak ızgarası
    "view_mode": "grid",      # "grid" = büyük kapak ızgarası, "detail" = sol liste + ayrıntı
    "intro": True,            # açılış animasyonu
    "intro_sound": True,      # açılış sesi
    "ignored_scan": [],
    "gcs_key": "",            # Google Görseller API anahtarı (kapak / ikon / arka plan araması için)
    "gcs_cx": "",             # Google arama motoru kimliği (cx)
    "idle_minutes": 3,         # boşta kalma ekranı için bekleme (dk), 0 = kapalı
    "remote_enabled": False,   # telefondan kumanda (yerel web sunucusu)
    "remote_port": 8765,
    "remote_token": "",
    "bg_blur": 4,              # oyun arka planının bulanıklığı (0-12)
    "bg_dim": 0.36,            # oyun arka planının karartılması (0.1-1.0)
    "grid_size": "medium",     # small / medium / large
    "font_scale": 1.0,         # yazı boyutu çarpanı (TV için 1.5)
    "accent_fixed": "#6366f1", # kapaktan renk almayı kapatınca kullanılan renk
    "update_check": True,      # açılışta sürüm kontrolü
    "update_url": "",          # boşsa UPDATE_URL kullanılır
    "onboarding_done": False,  # ilk açılış rehberi
}

# load_data() yapılandırmayı okuyamazsa buraya ipucu bırakır (açılışta yedekten geri yükleme önerilir)
LOAD_STATE = {"error": "", "moved_to": None}

DEFAULT_ACCENT = "#6366f1"

APP_VERSION = "2.0.0"
# Sürüm bilgisi adresi (JSON): {"version": "2.1.0", "url": "https://.../launcher.py",
#                           "notes": "neler değişti", "files": {"launcher_vfx.py": "https://..."}}
UPDATE_URL = ""

THEME_PRESETS = {
    "Mor": "#6366f1", "Mavi": "#3b82f6", "Turkuaz": "#14b8a6", "Yeşil": "#22c55e",
    "Turuncu": "#f97316", "Kırmızı": "#ef4444", "Pembe": "#ec4899", "Altın": "#eab308",
}
GRID_SIZES = {"small": 220, "medium": 260, "large": 330}
FONT_SCALES = {"Normal": 1.0, "Büyük": 1.25, "Çok büyük (TV)": 1.5}


def _today():
    return datetime.now().strftime("%Y-%m-%d")


def _is_new(g, days=7):
    try:
        d = datetime.strptime(g.get("added", ""), "%Y-%m-%d")
        return (datetime.now() - d).days < days
    except Exception:
        return False


def _ver_tuple(text):
    nums = [int(x) for x in re.findall(r"\d+", str(text or ""))[:3]]
    return tuple(nums) or (0,)

EXTRA_KEYS = {"args": "", "admin": False, "direct": False, "install_dir": "", "source": "", "store_id": "", "play_seconds": 0, "added": ""}

def fmt_playtime(sec):
    sec = int(sec or 0)
    if sec < 60:
        return "" if sec <= 0 else "1 dk'dan az"
    m = sec // 60
    if m < 60:
        return f"{m} dk"
    h, m = divmod(m, 60)
    return f"{h} sa {m} dk" if h < 10 else f"{h} saat"

def list_monitors():
    """Windows'ta bağlı monitörleri (x, y, genişlik, yükseklik, birincil_mi) olarak döner."""
    if not ex.IS_WIN:
        return []
    import ctypes
    from ctypes import wintypes

    class _RECT(ctypes.Structure):
        _fields_ = [("left", ctypes.c_long), ("top", ctypes.c_long),
                    ("right", ctypes.c_long), ("bottom", ctypes.c_long)]

    class _MONINFO(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_ulong), ("rcMonitor", _RECT),
                    ("rcWork", _RECT), ("dwFlags", ctypes.c_ulong)]

    user32 = ctypes.windll.user32
    out = []
    PROC = ctypes.WINFUNCTYPE(ctypes.c_int, wintypes.HMONITOR, wintypes.HDC,
                              ctypes.POINTER(_RECT), wintypes.LPARAM)

    def cb(hmon, hdc, lprc, data):
        mi = _MONINFO()
        mi.cbSize = ctypes.sizeof(_MONINFO)
        user32.GetMonitorInfoW(hmon, ctypes.byref(mi))
        r = mi.rcMonitor
        out.append((r.left, r.top, r.right - r.left, r.bottom - r.top, bool(mi.dwFlags & 1)))
        return 1

    try:
        user32.EnumDisplayMonitors(None, None, PROC(cb), 0)
    except Exception:
        return []
    return out


def target_monitor(pref):
    """Açılış monitörünü seçer: "portrait" (dikey monitör, varsayılan), "secondary", "primary" ya da sıra (0, 1, ...)."""
    mons = list_monitors()
    if not mons:
        return None
    if isinstance(pref, int) and 0 <= pref < len(mons):
        return mons[pref][:4]
    if pref in ("portrait", "secondary"):
        port = [m for m in mons if m[3] > m[2]]     # yüksekliği genişliğinden büyük = dikey
        if port:
            return port[0][:4]
    prim = [m for m in mons if m[4]]
    sec = [m for m in mons if not m[4]]
    if pref == "primary":
        pick = prim[0] if prim else mons[0]
    else:
        pick = sec[0] if sec else (prim[0] if prim else mons[0])
    return pick[:4]


def read_pref(key, default):
    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get(key, default)
    except Exception:
        return default


def color_for(game_id):
    return PALETTE[sum(ord(c) for c in game_id) % len(PALETTE)]

def load_data():
    LOAD_STATE.update(error="", moved_to=None)
    cfg = dict(DEFAULT_CFG)
    games = []
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list):
                raw = data
            else:
                raw = data.get("games", [])
                for k in DEFAULT_CFG:
                    if k in data:
                        cfg[k] = data[k]
            for i, g in enumerate(raw):
                gid = g.get("id") or f"oyun{i + 1}"
                games.append({"id": gid, "name": g.get("name", gid), "path": g.get("path", ""),
                              "last_played": g.get("last_played", ""),
                              "publisher": g.get("publisher", ""), "developer": g.get("developer", ""),
                              "release": g.get("release", ""), "genre": g.get("genre", ""),
                              "desc": g.get("desc", ""), "launch_count": g.get("launch_count", 0),
                              **{k: g.get(k, d) for k, d in EXTRA_KEYS.items()}})
        except Exception as e:
            # Okunamayan dosya silinmesin / üstüne boş kütüphane yazılmasın: yanına taşı
            games = []
            cfg = dict(DEFAULT_CFG)
            LOAD_STATE["error"] = f"{type(e).__name__}: {e}"
            LOAD_STATE["moved_to"] = fx.quarantine_corrupt(CONFIG_FILE)
    for g in games:
        g["color"] = color_for(g["id"])
    return cfg, games

def save_data(cfg, games):
    out = dict(cfg)
    out["games"] = [{"id": g["id"], "name": g["name"], "path": g["path"],
                     "last_played": g.get("last_played", ""),
                     "publisher": g.get("publisher", ""), "developer": g.get("developer", ""),
                     "release": g.get("release", ""), "genre": g.get("genre", ""),
                     "desc": g.get("desc", ""), "launch_count": g.get("launch_count", 0),
                     **{k: g.get(k, d) for k, d in EXTRA_KEYS.items()}}
                    for g in games]
    fx.atomic_write(CONFIG_FILE, json.dumps(out, ensure_ascii=False, indent=2).encode("utf-8"))

_source_cache = {}

def find_asset(game_id, kind, exts=EXTS):
    for ext in exts:
        p = os.path.join(ASSETS_DIR, f"{game_id}_{kind}{ext}")
        if os.path.exists(p):
            return p
    return None

def remove_assets(game_id, kind):
    for ext in ALL_EXTS:
        p = os.path.join(ASSETS_DIR, f"{game_id}_{kind}{ext}")
        if os.path.exists(p):
            try:
                os.remove(p)
            except Exception:
                pass
    _source_cache.pop((game_id, kind), None)

def placeholder(kind, game, size=(600, 840)):
    img = Image.new("RGBA", size, game["color"])
    d = ImageDraw.Draw(img)
    font = vfx.pil_font(max(14, size[1] // 8), True)
    text = game["name"][:1].upper() if kind == "ikon" else (game["name"] if kind == "kapak" else "")
    if text:
        d.text((size[0] / 2, size[1] / 2), text, fill="white", font=font, anchor="mm")
    return img

def get_image(game, kind, size):
    key = (game["id"], kind)
    path = find_asset(game["id"], kind)
    stamp = (path, os.path.getmtime(path)) if path else (None, None)
    cached = _source_cache.get(key)
    if cached and cached[0] == stamp:
        src = cached[1]
    else:
        try:
            src = Image.open(path).convert("RGBA") if path else placeholder(kind, game)
            if path and kind in ("kapak", "ikon"):  # dev kaynakları önbellekte şişirme
                src.thumbnail((900, 1260) if kind == "kapak" else (512, 512))
        except Exception:
            src = placeholder(kind, game)
        _source_cache[key] = (stamp, src)
    return ImageOps.fit(src, size, Image.LANCZOS)

def hero_image(game, w, h, bright=0.5):
    """Duvar kağıdı: arka plan tam ekran, sadece sol kenar yazılar okunsun diye hafif koyulaşır."""
    base = ImageEnhance.Brightness(get_image(game, "arkaplan", (w, h))).enhance(bright)
    solid = Image.new("RGBA", (w, h), ImageColor.getrgb(T["bg"]) + (255,))
    horiz = ImageOps.invert(Image.linear_gradient("L").rotate(90)).resize((w, h))
    hmask = horiz.point(lambda p: int(p * 0.35))
    return Image.composite(solid, base.convert("RGBA"), hmask)

def round_corners(img, radius):
    mask = Image.new("L", img.size, 0)
    d = ImageDraw.Draw(mask)
    d.rounded_rectangle([0, 0, img.size[0], img.size[1]], radius=radius, fill=255)
    out = Image.new("RGBA", img.size, (0, 0, 0, 0))
    out.paste(img, (0, 0), mask=mask)
    return out

def ffmpeg_exe():
    try:
        import imageio_ffmpeg
        return imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        return None

def ydl_download(url, out_dir, kind, out_name=None, status=None, allow_playlist=False):
    import yt_dlp

    def hook(d):
        if status is None:
            return
        if d.get("status") == "downloading":
            done = d.get("downloaded_bytes") or 0
            tot = d.get("total_bytes") or d.get("total_bytes_estimate") or 0
            status["text"] = "İndiriliyor " + (f"%{int(done * 100 / tot)}" if tot else "...")
        elif d.get("status") == "finished":
            status["text"] = "İşleniyor..."

    is_playlist = allow_playlist and "playlist?list=" in url
    opts = {
        "outtmpl": os.path.join(out_dir, (out_name or "%(title)s") + ".%(ext)s"),
        "quiet": True,
        "no_warnings": True,
        "noplaylist": not is_playlist,
        "playlistend": 100,
        "progress_hooks": [hook],
    }
    ff = ffmpeg_exe()
    if ff:
        opts["ffmpeg_location"] = ff
    if kind == "audio":
        opts["format"] = "bestaudio/best"
        opts["postprocessors"] = [{"key": "FFmpegExtractAudio",
                                   "preferredcodec": "mp3", "preferredquality": "192"}]
    else:
        opts["format"] = "bestvideo[ext=mp4][height<=720]/bestvideo[ext=mp4]/best[ext=mp4]/best"
    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=True)
    return (info or {}).get("title") or ""

def google_image_urls(query, key, cx, img_size=None, num=5):
    """Google Özel Arama API'sinde görsel arar; sonuçların bağlantılarını döner (liste)."""
    import json
    import urllib.parse
    import urllib.request
    p = {"key": key, "cx": cx, "q": query, "searchType": "image", "num": num, "safe": "active"}
    if img_size:
        p["imgSize"] = img_size
    url = "https://www.googleapis.com/customsearch/v1?" + urllib.parse.urlencode(p)
    with urllib.request.urlopen(url, timeout=20) as r:
        data = json.loads(r.read().decode("utf-8"))
    return [it.get("link") for it in (data.get("items") or []) if it.get("link")]


def art_log(msg):
    """Görsel arama hatalarını launcher klasöründeki gorsel_log.txt dosyasına yazar."""
    try:
        with open(os.path.join(BASE_DIR, "gorsel_log.txt"), "a", encoding="utf-8") as f:
            f.write(datetime.now().strftime("%Y-%m-%d %H:%M:%S") + "  " + msg + "\n")
    except Exception:
        pass


def download_image(url):
    """Bağlantıdan görseli indirir; açılamazsa None."""
    import io
    import urllib.request
    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
    with urllib.request.urlopen(req, timeout=20) as r:
        raw = r.read(15_000_000)
    try:
        return Image.open(io.BytesIO(raw)).convert("RGB")
    except Exception:
        return None


class Music:
    def __init__(self):
        self.ok = False
        self.pg = None
        self._loaded = False
        self.tracks = []
        self.index = -1
        self.mode = "none"
        self.current_file = ""
        self.playing = False
        self.paused = False
        self.volume = 0.4
        self.shuffle = True
        self.paused_at = 0.0
        self.play_start_time = 0.0
        self._lock = threading.Lock()

    def _ensure_loaded(self):
        if self._loaded: return
        with self._lock:  # açılış sesi arka planda hazırlanırken çifte init olmasın
            if self._loaded: return
            try:
                import pygame
                pygame.mixer.init()
                self.pg = pygame
                self.ok = True
            except Exception:
                pass
            self._loaded = True

    def scan(self, folder):
        self._ensure_loaded()
        cur = self.current_file
        tracks = []
        if folder and os.path.isdir(folder):
            for root, _, files in os.walk(folder):
                for f in files:
                    if f.lower().endswith(AUDIO_EXTS):
                        tracks.append(os.path.join(root, f))
        tracks.sort(key=lambda p: os.path.basename(p).lower())
        self.tracks = tracks
        if self.mode == "playlist" and cur in tracks:
            self.index = tracks.index(cur)
        else:
            self.index = -1

    def _play(self, path, loops, start=0.0):
        if not self._loaded: self._ensure_loaded()
        if not self.ok: return
        self.pg.mixer.music.load(path)
        self.pg.mixer.music.set_volume(self.volume)
        self.pg.mixer.music.play(loops=loops, start=start)
        self.current_file = path
        self.playing = True
        self.paused = False
        self.paused_at = start
        self.play_start_time = time.time() - start

    def release(self):
        if self.ok:
            try:
                self.pg.mixer.music.stop()
            except Exception:
                pass
            try:
                self.pg.mixer.music.unload()
            except Exception:
                pass
        self.playing = False
        self.paused = False
        self.mode = "none"
        self.current_file = ""
        self.paused_at = 0.0

    def play_game_file(self, path):
        if not self.ok: return
        if self.mode == "game" and self.current_file == path and self.playing:
            return
        try:
            self._play(path, -1)
            self.mode = "game"
        except Exception:
            self.release()

    def play_playlist(self, i=None):
        if not self.ok: return
        if not self.tracks:
            self.release()
            return
        if i is None:
            if self.shuffle and len(self.tracks) > 1:
                i = random.choice([k for k in range(len(self.tracks)) if k != self.index])
            else:
                i = self.index + 1
        tries = 0
        while self.tracks and tries <= len(self.tracks):
            i %= len(self.tracks)
            try:
                self._play(self.tracks[i], 0)
                self.index = i
                self.mode = "playlist"
                return
            except Exception:
                del self.tracks[i]
                tries += 1
        self.release()

    def next(self):
        self.play_playlist()

    def prev(self):
        self.play_playlist(self.index - 1)

    def toggle(self):
        if not self.ok: return
        if not self.playing:
            self.play_playlist()
        elif self.paused:
            self.pg.mixer.music.unpause()
            self.paused = False
            self.play_start_time = time.time() - self.paused_at
        else:
            self.paused_at = self.get_pos()
            self.pg.mixer.music.pause()
            self.paused = True

    def pause_now(self):
        if self.ok and self.playing and not self.paused:
            self.paused_at = self.get_pos()
            self.pg.mixer.music.pause()
            self.paused = True

    def set_volume(self, v):
        self.volume = v
        if self.ok:
            try:
                self.pg.mixer.music.set_volume(v)
            except Exception:
                pass

    def tick(self):
        if self.ok and self.mode == "playlist" and self.playing and not self.paused:
            try:
                if not self.pg.mixer.music.get_busy():
                    self.play_playlist()
                    return True
            except Exception:
                pass
        return False

    def current_name(self):
        if self.mode == "playlist" and 0 <= self.index < len(self.tracks):
            return os.path.splitext(os.path.basename(self.tracks[self.index]))[0]
        return ""

    def get_pos(self):
        if not self.ok or not self.playing:
            return 0.0
        if self.paused:
            return self.paused_at
        return time.time() - self.play_start_time

def hover(btn, normal, over):
    btn.bind("<Enter>", lambda e: btn.configure(bg=over))
    btn.bind("<Leave>", lambda e: btn.configure(bg=normal))

def styled_menu(parent):
    m = tk.Menu(parent, tearoff=0, bg=T["side"], fg=T["text"], activebackground=T["row_sel"],
                activeforeground="white", bd=0, font=(FONT, 10))
    m.bind("<<MenuSelect>>", lambda e: ui_play("move"))  # menüde gezinirken ses
    return m

# ---- Ada göre sıralama (A-Z, Türkçe harfler dahil, sayılar başta)
_TR_ORDER = "0123456789abcçdefgğhıijklmnoöpqrsştuüvwxyz"

def name_sort_key(name):
    s = (name or "").replace("İ", "i").replace("I", "i").casefold()
    s = re.sub(r"^[^0-9a-zçğıöşü]+", "", s)  # baştaki ™, ®, tırnak vb. sembolleri yok say
    return [(-1 if ch == " " else _TR_ORDER.find(ch) if ch in _TR_ORDER else 100 + ord(ch)) for ch in s]

def synth_intro(rate, length=2.1):
    """Açılış sesini sentezler (dosya gerekmez): alçak bir 'swell', yumuşak bir akor,
    yükselen çan arpejyosu ve sonda süpürme sesi. Dönüş: -1..1 arası float listesi."""
    import math
    n = int(rate * length)
    mix = [0.0] * n
    tau = 2 * math.pi
    sin, exp = math.sin, math.exp

    def voice(freq, start, dur, vol, attack, decay, partials=((1.0, 1.0),)):
        i0 = int(start * rate)
        cnt = min(n - i0, int(dur * rate))
        if cnt <= 0:
            return
        att = max(1, int(attack * rate))
        rel = max(1, int(0.06 * rate))
        w = [(tau * freq * r / rate, a) for r, a in partials]
        for k in range(cnt):
            env = (k / att if k < att else 1.0) * exp(-decay * k / rate)
            if cnt - k < rel:
                env *= (cnt - k) / rel
            sm = 0.0
            for ph, a in w:
                sm += a * sin(ph * k)
            mix[i0 + k] += vol * env * sm

    bell = ((1.0, 1.0), (2.76, 0.25), (5.4, 0.08))
    voice(55.0, 0.0, 2.0, 0.30, 0.70, 1.1, ((1.0, 1.0), (2.0, 0.35)))           # alçak swell
    for f in (220.0, 329.63, 440.0, 554.37, 659.25):                             # A majör add9 akoru
        voice(f, 0.12, 1.9, 0.055, 0.45, 1.5, ((1.0, 1.0), (1.004, 0.7), (2.0, 0.2)))
    for j, f in enumerate((659.25, 880.0, 1108.7, 1318.5)):                      # yükselen çan arpejyosu
        voice(f, 0.55 + 0.14 * j, 0.9, 0.11, 0.004, 4.5, bell)
    voice(1760.0, 1.25, 0.7, 0.07, 0.003, 5.5, bell)                             # son 'ping'
    # süpürme (perde açılırken): alçak geçiren filtreli gürültü
    import random
    i0, i1, lp = int(1.40 * rate), n, 0.0
    span = max(1, i1 - i0)
    for k in range(i0, i1):
        lp += 0.14 * (random.uniform(-1.0, 1.0) - lp)
        x = (k - i0) / span
        mix[k] += 0.16 * lp * sin(math.pi * x) ** 2
    peak = max(abs(v) for v in mix) or 1.0
    scale = 0.8 / peak
    return [v * scale for v in mix]

# ---- Menü sesleri (dosya gerektirmez, kodla üretilir)
class UiSound:
    SPECS = {
        "move":   ([(1180, 0.035)], 0.20),
        "select": ([(660, 0.05), (990, 0.08)], 0.30),
        "menu":   ([(520, 0.04), (780, 0.06)], 0.25),
        "launch": ([(523, 0.07), (659, 0.07), (784, 0.07), (1047, 0.20)], 0.35),
        "page":   (None, 0.30),   # sayfa çevirme: filtrelenmiş gürültü (kağıt hışırtısı)
    }

    def __init__(self, music):
        self.music = music
        self.enabled = True
        self.sounds = {}
        self.last = {}
        self._built = False
        self.intro = None

    def _build(self):
        self._built = True
        m = self.music
        m._ensure_loaded()
        if not m.ok:
            return
        try:
            import math
            from array import array
            init = m.pg.mixer.get_init()
            if not init:
                return
            freq, fmt, ch = init
            if fmt != -16:  # yalnızca 16-bit işaretli çıkışı destekle
                return
            for name, (notes, vol) in self.SPECS.items():
                buf = array("h")
                if notes is None:
                    import random as _rnd
                    n = int(freq * 0.32)
                    y = 0.0
                    for k in range(n):
                        t = k / n
                        y += 0.12 * (_rnd.uniform(-1, 1) - y)      # yumuşatılmış gürültü
                        env = math.sin(math.pi * t) ** 1.6          # yavaşça açılıp kapanan hışırtı
                        v = int(max(-1.0, min(1.0, y * 3.2)) * 32767 * vol * env)
                        for _ in range(ch):
                            buf.append(v)
                    self.sounds[name] = m.pg.mixer.Sound(buffer=buf.tobytes())
                    continue
                for f, dur in notes:
                    n = int(freq * dur)
                    for k in range(n):
                        env = min(1.0, k / (freq * 0.004)) * math.exp(-5.0 * k / n)
                        w = math.sin(2 * math.pi * f * k / freq) + 0.25 * math.sin(4 * math.pi * f * k / freq)
                        v = int(32767 * vol * env * w / 1.25)
                        for _ in range(ch):
                            buf.append(v)
                self.sounds[name] = m.pg.mixer.Sound(buffer=buf.tobytes())
        except Exception:
            self.sounds = {}

    def prepare_intro(self):
        """Açılış sesini arka planda hazırlar (arayüzü bekletmez)."""
        try:
            from array import array
            m = self.music
            m._ensure_loaded()
            if not m.ok:
                return
            init = m.pg.mixer.get_init()
            if not init:
                return
            freq, fmt, ch = init
            if fmt != -16:
                return
            half = max(8000, freq // 2)
            data = synth_intro(half)
            buf = array("h")
            last = len(data) - 1
            ratio = freq / half
            for i in range(int(len(data) * ratio)):
                x = i / ratio
                j = int(x)
                a = data[j]
                b = data[j + 1] if j < last else a
                v = int((a + (b - a) * (x - j)) * 32767)
                for _ in range(ch):
                    buf.append(v)
            self.intro = m.pg.mixer.Sound(buffer=buf.tobytes())
        except Exception:
            self.intro = None

    def play_intro(self):
        """Hazırsa çalar ve True döner."""
        if self.intro is None:
            return False
        try:
            self.intro.set_volume(0.9)
            self.intro.play()
        except Exception:
            pass
        return True

    def stop_intro(self):
        if self.intro is not None:
            try:
                self.intro.fadeout(250)
            except Exception:
                pass

    def play(self, name):
        if not self.enabled:
            return
        if not self._built:
            self._build()
        snd = self.sounds.get(name)
        if not snd:
            return
        now = time.time()
        if now - self.last.get(name, 0) < 0.05:  # arka arkaya yığılmasın
            return
        self.last[name] = now
        try:
            snd.play()
        except Exception:
            pass

_UI_SOUND = None

def set_ui_sound(obj):
    global _UI_SOUND
    _UI_SOUND = obj

def ui_play(name):
    if _UI_SOUND:
        _UI_SOUND.play(name)

def blend(c1, c2, t):
    t = max(0.0, min(1.0, t))
    r1, g1, b1 = ImageColor.getrgb(c1)
    r2, g2, b2 = ImageColor.getrgb(c2)
    return f"#{int(r1+(r2-r1)*t):02x}{int(g1+(g2-g1)*t):02x}{int(b1+(b2-b1)*t):02x}"

def hex_lum(c):
    r, g, b = ImageColor.getrgb(c)
    return (0.299 * r + 0.587 * g + 0.114 * b) / 255

def set_accent_colors(color):
    T["accent"] = color
    T["accent_hover"] = blend(color, "#ffffff", 0.25)
    T["accent_dim"] = blend(color, "#000000", 0.25)
    T["accent_fg"] = "#000000" if hex_lum(color) > 0.62 else "#ffffff"

def dominant_accent(img):
    """Kapaktaki baskın canlı rengi bulur; siyah zeminde okunur olacak şekilde ayarlar."""
    try:
        small = img.convert("RGB").resize((48, 72))
        q = small.quantize(colors=8)
        pal = q.getpalette() or []
        best, best_score = None, 0.0
        for count, idx in (q.getcolors() or []):
            r, g, b = pal[idx * 3: idx * 3 + 3]
            h, s, v = colorsys.rgb_to_hsv(r / 255, g / 255, b / 255)
            if v < 0.16:
                continue
            score = count * (0.1 + s) ** 2 * (0.3 + v)
            if s < 0.12:
                score *= 0.2
            if score > best_score:
                best, best_score = (h, s, v), score
        if best is None or best[1] < 0.14:
            return "#cbd5e1"  # gri tonlu kapak: nötr gümüş
        h, s, v = best
        s = max(s, 0.5)
        v = min(max(v, 0.72), 0.95)
        r, g, b = colorsys.hsv_to_rgb(h, s, v)
        return "#%02x%02x%02x" % (int(r * 255), int(g * 255), int(b * 255))
    except Exception:
        return DEFAULT_ACCENT

_accent_cache = {}

def game_accent(g):
    path = find_asset(g["id"], "kapak")
    stamp = (path, os.path.getmtime(path)) if path else (None, g["color"])
    c = _accent_cache.get(g["id"])
    if c and c[0] == stamp:
        return c[1]
    col = dominant_accent(get_image(g, "kapak", (48, 72)))
    _accent_cache[g["id"]] = (stamp, col)
    return col

def scan_key(f):
    return f"{f.get('source', '')}|{f.get('store_id') or os.path.normcase(f.get('path', ''))}"

def _rr_points(x1, y1, x2, y2, r):
    """smooth=True ile yuvarlak köşeli çokgen noktaları (canvas'ta yalnızca çerçeve için)."""
    return [x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r, x2, y2 - r, x2, y2, x2 - r, y2,
            x1 + r, y2, x1, y2, x1, y2 - r, x1, y1 + r, x1, y1]

class RoundButton(tk.Frame):
    def __init__(self, parent, text, command, primary=False, width=None, height=26,
                 font=(FONT, 9), icon="", radius=8, bg=None, custom_bg=None, custom_fg=None):
        try:
            pbg = parent.cget("bg")
        except Exception:
            pbg = T["panel"]
        self.btn_bg = bg or pbg
        self.primary = primary
        self.font = font
        self.icon = icon
        self.text = text
        self.command = command
        self._hover = False
        self.custom_bg = custom_bg
        self.custom_fg = custom_fg

        if width is None:
            tmp = tkfont.Font(font=font)
            label = f"{icon}  {text}".strip() if icon else text
            width = tmp.measure(label) + 20

        super().__init__(parent, width=width, height=height, bg=self.btn_bg, 
                         highlightthickness=0, bd=0, cursor="hand2")
        self.pack_propagate(False)

        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<Button-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)

        self._lbl = tk.Label(self, text=f"{icon}  {text}".strip() if icon else text,
                             bg=self.btn_bg, fg="#ffffff" if primary else T["text"],
                             font=font, cursor="hand2")
        self._lbl.pack(fill="both", expand=True)
        
        for w in (self._lbl,):
            w.bind("<Enter>", self._on_enter)
            w.bind("<Leave>", self._on_leave)
            w.bind("<Button-1>", self._on_press)
            w.bind("<ButtonRelease-1>", self._on_release)

        self._apply_colors()

    def _apply_colors(self):
        if self.custom_bg:
            bg = self.custom_bg
            fg = self.custom_fg or "#000000"
            if self._hover:
                bg = blend(bg, "#ffffff", 0.2)
        elif self.primary:
            bg = T["accent_hover"] if self._hover else T["accent"]
            fg = T["accent_fg"]
        else:
            bg = T["chip_hover"] if self._hover else T["chip"]
            fg = T["text"]
        self.configure(bg=bg)
        self._lbl.configure(bg=bg, fg=fg)

    def _on_enter(self, e):
        self._hover = True
        self._apply_colors()

    def _on_leave(self, e):
        self._hover = False
        self._apply_colors()

    def _on_press(self, e):
        self._lbl.pack_configure(padx=3, pady=2)      # basınca hafifçe içe çöker

    def _on_release(self, e):
        self._lbl.pack_configure(padx=0, pady=0)
        if self.command:
            self.command()

    def configure_text(self, text):
        self._lbl.configure(text=text)

    def set_enabled(self, val):
        self._lbl.configure(cursor="hand2" if val else "arrow")
        self.configure(cursor="hand2" if val else "arrow")


def chip(parent, text, cmd, primary=False, font=(FONT, 9), padx=10, pady=4, icon=""):
    h = 22 + pady * 2
    return RoundButton(parent, text, cmd, primary=primary, height=h, font=font,
                       icon=icon, radius=6)

class SplitButton(tk.Frame):
    def __init__(self, parent, text, cmd_main, cmd_right, width=120, height=32):
        super().__init__(parent, bg=T["bg"], highlightthickness=0, bd=0)
        self.pack_propagate(False)
        self.config(width=width, height=height)
        
        self.main_btn = tk.Frame(self, bg="#ffffff", cursor="hand2")
        self.main_btn.pack(fill="both", expand=True)
        self.lbl = tk.Label(self.main_btn, text=text, bg="#ffffff", fg="#000000", font=(FONT, 10, "bold"))
        self.lbl.pack(fill="both", expand=True)
        
        self.busy = False   # başlatma sürerken yeşil kalır

        def hover_on(e):
            col = "#16a34a" if self.busy else "#e0e0e0"
            self.main_btn.configure(bg=col)
            self.lbl.configure(bg=col)

        def hover_off(e):
            col = "#22c55e" if self.busy else "#ffffff"
            self.main_btn.configure(bg=col)
            self.lbl.configure(bg=col)

        for w in (self.main_btn, self.lbl):
            w.bind("<Enter>", hover_on)
            w.bind("<Leave>", hover_off)
            w.bind("<Button-1>", lambda e: cmd_main())
            w.bind("<Button-3>", lambda e: cmd_right(e))

vfx.init(T=T, get_image=get_image, find_asset=find_asset, fmt_playtime=fmt_playtime, blend=blend,
         rr_points=_rr_points, RoundButton=RoundButton, round_corners=round_corners, color_for=color_for)


class Launcher(vfx.VisualsMixin, tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Oyun Launcher")
        
        # Xbox ile açılınca her zaman dikey (ikinci) monitör; klavyede ayardaki monitör
        _mon = target_monitor("portrait" if "--kol" in sys.argv else read_pref("monitor", "portrait"))
        if _mon:
            self.geometry(f"{_mon[2]}x{_mon[3]}+{_mon[0]}+{_mon[1]}")
        else:
            self.geometry("1080x1920")
        self._open_geom = self.geometry()   # tam ekrana geçmeden önce hedef monitöre yeniden yerleştirmek için
        self.minsize(800, 1200)
        self.configure(bg=T["bg"])

        fx.make_backup(CONFIG_FILE)   # her açılışta yedek al, son 5 tanesini tut
        self.cfg, self.games = load_data()
        if not self.cfg.get("dynamic_accent", True):
            set_accent_colors(self.cfg.get("accent_fixed", DEFAULT_ACCENT))
        self.games.sort(key=lambda g: name_sort_key(g["name"]))
        self.selected = 0 if self.games else -1
        self.refs = {}
        self.rows = {}
        self.view_game_id = None
        
        self.cap = None
        self.video_job = None
        self.video_delay = 33
        self.bg_item = None
        self.video_item = None
        self.vsize = (0, 0)
        self.redraw_job = None
        self.video_photo = None
        self.vid_w, self.vid_h = 0, 0

        self.busy = False
        self.status = {"text": ""}
        self.job_q = queue.Queue()

        self.music = Music()
        self.ui_sound = UiSound(self.music)
        self.ui_sound.enabled = bool(self.cfg.get("ui_sounds", True))
        set_ui_sound(self.ui_sound)
        self.splash = None
        self._intro_music_block = False
        self._intro_skip = False
        self._intro_snd_done = True
        if self.cfg.get("intro", True) and self.cfg.get("intro_sound", True) \
                and "--minimized" not in sys.argv:
            threading.Thread(target=self.ui_sound.prepare_intro, daemon=True).start()
        self._hover_row = None
        self._hover_leave_job = None
        self._fade_id = 0
        self._sb_busy = False
        self._list_sig = None
        self.music.volume = float(self.cfg["volume"])
        self.music.shuffle = bool(self.cfg["shuffle"])
        self.user_paused = False
        self.pl_win = None
        self.pl_list = None

        self._duration_cache = {}
        self.sidebar_open = True

        self.size_cache = {}
        self.size_busy = set()
        self.info_dirty = False
        self.info_btns = None

        # yeni özellikler: vurgu rengi, tepsi, kumanda, otomatik tarama
        self._primary_btns = []
        self.ui_q = queue.Queue()
        self._hidden = False
        self._acc_token = 0
        self._accent_ready = False
        self.fullscreen = False
        self.game_running = None
        self._watch_stop = threading.Event()
        self._auto_paused = False
        self._auto_scanning = False
        self._menu_vars = []
        # kapak ızgarası durumu
        self.view_mode = "grid" if self.cfg.get("view_mode", "grid") == "grid" else "detail"
        if self.cfg.get("liste", True):      # Explorer listesi ana kütüphane görünümü: her zaman grid
            self.view_mode = "grid"
        self.grid_items = []
        self.grid_tiles = {}
        self.grid_m = None
        self._grid_cur = 0.0
        self._grid_target = 0.0
        self._grid_total = 1
        self._grid_job = None
        self._grid_cfg_job = None
        _fs = float(self.cfg.get("font_scale", 1.0))
        self._gfont = tkfont.Font(family=FONT, size=int(13 * _fs))
        self._gfont_b = tkfont.Font(family=FONT, size=int(13 * _fs), weight="bold")
        self._gfont_s = tkfont.Font(family=FONT, size=int(10 * _fs), weight="bold")
        self._grid_bg_item = None
        self._grid_bg_key = None
        self._play_t0 = {}
        self.tray = ex.Tray()
        self.pad = ex.Gamepad()
        self.pad_menu = None
        self.pad_menu_items = []
        self.pad_menu_labels = []
        self.pad_menu_sel = 0
        self.toast = None
        # boşta ekranı + telefondan kumanda
        self.idle = None
        self._idle_last = time.time()
        self._idle_mouse = (0, 0)
        self.idle_var = None
        self.remote = None
        self.remote_state = {}
        self.remote_games = []
        self.remote_gv = ""

        self.fx_init()
        self.build_sidebar()
        self.build_right()
        self.build_grid()
        self.bind_all("<MouseWheel>", self.on_wheel)
        self.bind_all("<Up>", lambda e: self.key_nav(e, -1))
        self.bind_all("<Down>", lambda e: self.key_nav(e, 1))
        self.bind_all("<Left>", lambda e: self.key_nav_h(e, -1))
        self.bind_all("<Right>", lambda e: self.key_nav_h(e, 1))
        self.bind_all("<Tab>", self.key_tab)
        self.bind("<Key>", self._intro_key)
        self.bind_all("<Return>", self.key_launch)
        self.bind_all("<F11>", self.toggle_fullscreen)
        self.bind_all("<Escape>", self.on_escape)
        self.bind_all("<Motion>", self._idle_motion, add="+")
        self.bind_all("<ButtonPress>", lambda e: self._idle_touch(), add="+")
        self.bind_all("<MouseWheel>", lambda e: self._idle_touch(), add="+")
        self.build_list(animate=True)
        self._list_sig = tuple(g["id"] for g in self.games)

        self.music.scan(self.cfg["music_folder"])
        if "--kol" in sys.argv:          # Xbox düğmesiyle açıldı: tam ekran kapak modu
            self.view_mode = "grid"
        self._apply_view_layout()
        self.select(self.selected, force=True)
        self.after(1000, self.music_tick)
        self.after(1000, self.info_poll)
        self.protocol("WM_DELETE_WINDOW", self.on_close)
        if "--minimized" in sys.argv:
            self.after(200, self.iconify)
        self.after(150, self.ui_poll)
        self.after(300, self.pad_poll)
        if "--kol" in sys.argv:
            self.after(200, self._kol_hedef)
        elif self.cfg.get("fullscreen") or "--fullscreen" in sys.argv:
            self.after(200, self._open_on_target)
        if self.cfg.get("auto_scan", True):
            self.after(2500, self.auto_scan)
        self.after(2000, self._idle_check)
        self.after(1000, self._remote_tick)
        if self.cfg.get("remote_enabled"):
            self.after(2600, self.remote_start)
        if LOAD_STATE["error"]:
            self.after(2800, self._offer_restore)
        self.show_home()
        self.after(1000, self._home_tick)
        self.start_intro()
        self.after(2600, self.maybe_onboard)
        if self.cfg.get("update_check", True):
            self.after(5000, lambda: self.check_update(manual=False))

    def on_close(self):
        for gid in list(self._play_t0):
            self._flush_playtime(gid)
        self._watch_stop.set()
        self.remote_stop(wait=False)
        self.tray.stop()
        self.close_video()
        self._save_music_resume()
        self.music.release()
        try:
            self.save()
        except Exception:
            pass
        self.destroy()

    def toggle_sidebar(self):
        if self._sb_busy:
            return
        self._sb_busy = True
        self.ui_sound.play("menu")
        opening = not self.sidebar_open
        if opening:
            self.sidebar.configure(width=1)
            self.sidebar.pack(side="left", fill="y", before=self.right)
            self.toggle_btn.config(text="✕")
        steps = 10

        def step(k):
            t = k / steps
            e = 1 - (1 - t) ** 3  # yumuşak duruş
            w = max(1, int(200 * (e if opening else 1 - e)))
            self.sidebar.configure(width=w)
            self.toggle_btn.place(x=max(10, w - 40), y=10)
            if k < steps:
                self.after(16, lambda: step(k + 1))
                return
            if not opening:
                self.sidebar.pack_forget()
                self.toggle_btn.config(text="≡")
                self.toggle_btn.place(x=10, y=10)
            self.sidebar.configure(width=200)
            self.sidebar_open = opening
            self._sb_busy = False

        step(1)

    def build_sidebar(self):
        self.sidebar = tk.Frame(self, bg=T["side"], width=200)
        self.sidebar.pack(side="left", fill="y")
        self.sidebar.pack_propagate(False)

        tk.Label(self.sidebar, text="KÜTÜPHANE", bg=T["side"], fg=T["muted"],
                 font=(FONT, 10, "bold")).pack(anchor="w", padx=12, pady=(40, 8))

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *a: self._on_search())

        search_wrap = tk.Frame(self.sidebar, bg=T["panel"])
        search_wrap.pack(fill="x", padx=10, pady=(0, 10))
        tk.Label(search_wrap, text="🔍", bg=T["panel"], fg=T["muted"],
                 font=(FONT, 11)).pack(side="left", padx=(8, 4))
        tk.Entry(search_wrap, textvariable=self.search_var, bg=T["panel"], fg=T["text"],
                 insertbackground=T["text"], relief="flat", font=(FONT, 10),
                 bd=0).pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 6))

        self.settings_btn = chip(self.sidebar, "Ayarlar", self.open_settings_menu, pady=6,
                                 icon="⚙", font=(FONT, 10))
        self.settings_btn.pack(side="bottom", fill="x", padx=10, pady=(0, 0))
        home_b = chip(self.sidebar, "Ana menü", self.show_home, pady=6,
                      icon="⌂", font=(FONT, 10))
        home_b.pack(side="bottom", fill="x", padx=10, pady=(0, 0))
        add = chip(self.sidebar, "Oyun ekle", self.add_game, pady=6, icon="＋", font=(FONT, 10))
        add.pack(side="bottom", fill="x", padx=10, pady=16)
        gbtn = chip(self.sidebar, "Kapak ızgarası", lambda: self.set_view_mode("grid"), pady=6,
                    icon="▦", font=(FONT, 10))
        gbtn.pack(side="bottom", fill="x", padx=10, pady=(0, 0))

        self.list_wrap = tk.Frame(self.sidebar, bg=T["side"])
        self.list_wrap.pack(fill="both", expand=True)
        self.list_canvas = tk.Canvas(self.list_wrap, bg=T["side"], highlightthickness=0)
        self.list_canvas.pack(side="left", fill="both", expand=True)

        self.list_inner = tk.Frame(self.list_canvas, bg=T["side"])
        self.inner_id = self.list_canvas.create_window((0, 0), window=self.list_inner, anchor="nw")
        self.list_inner.bind("<Configure>", lambda e: self.list_canvas.configure(
            scrollregion=self.list_canvas.bbox("all")))
        self.list_canvas.bind("<Configure>", lambda e: self.list_canvas.itemconfigure(
            self.inner_id, width=e.width))

    def on_wheel(self, e):
        if self.splash is not None:
            return
        w = self.winfo_containing(e.x_root, e.y_root)
        while w is not None:
            if self.view_mode == "grid" and w is self.grid_wrap:
                self.grid_wheel(e)
                return
            if w is self.list_wrap:
                step = -e.delta if sys.platform == "darwin" else -int(e.delta / 120)
                self.list_canvas.yview_scroll(step, "units")
                return
            w = w.master

    def build_list(self, animate=False):
        for child in self.list_inner.winfo_children():
            child.destroy()
        self.rows = {}
        q = self.search_var.get().strip().lower()
        for i, g in enumerate(self.games):
            if q and q not in g["name"].lower():
                continue
            self.make_row(i, g)
        self.highlight()
        if animate:
            for n, i in enumerate(list(self.rows)[:30]):
                self._row_intro(i, n * 28)

    def _row_intro(self, i, delay):
        """Satır adı sırayla belirir (kısa fade-in)."""
        r = self.rows.get(i)
        if not r:
            return
        row_ref, name_lbl = r["row"], r["name"]
        try:
            name_lbl.configure(fg=T["side"])
        except tk.TclError:
            return

        def alive():
            cur = self.rows.get(i)
            return cur is not None and cur["row"] is row_ref

        def step(k, total=7):
            if not alive():
                return
            try:
                if k >= total:
                    self.paint_row(i)
                    return
                if i != self.selected:
                    name_lbl.configure(fg=blend(T["side"], T["text"], k / total))
            except tk.TclError:
                return
            self.after(22, lambda: step(k + 1))

        self.after(delay, lambda: step(1))

    def _row_enter(self, i):
        if self._hover_leave_job:
            try:
                self.after_cancel(self._hover_leave_job)
            except Exception:
                pass
            self._hover_leave_job = None
        if self._hover_row != i:
            self._hover_row = i
            if i != self.selected:
                self.ui_sound.play("move")
        self.animate_row(i, 1.0)

    def _row_leave(self, i):
        if self._hover_leave_job:
            try:
                self.after_cancel(self._hover_leave_job)
            except Exception:
                pass
        self._hover_leave_job = self.after(40, self._clear_hover)
        self.animate_row(i, 0.0)

    def _clear_hover(self):
        self._hover_row = None
        self._hover_leave_job = None

    def key_nav(self, e, step):
        """Yukarı/aşağı ok tuşlarıyla listede / ızgarada gezin."""
        if self._home_on:
            self.home_move(step)
            return "break"
        try:
            if e.widget.winfo_toplevel() is not self:
                return
        except Exception:
            return
        if self.splash is not None:
            return "break"
        if self.pad_menu_open():
            self.pad_menu_move(step)
            return "break"
        if self.view_mode == "grid":
            if isinstance(e.widget, tk.Entry):
                self.grid_cv.focus_set()
            self.grid_move(0, step)
            return "break"
        if self.move_selection(step):
            return "break"

    def key_nav_h(self, e, step):
        try:
            if e.widget.winfo_toplevel() is not self:
                return
        except Exception:
            return
        if isinstance(e.widget, (tk.Entry, tk.Text, tk.Listbox, tk.Scale)):
            return
        if self.splash is not None or self.pad_menu_open():
            return "break"
        if self.view_mode == "grid":
            self.grid_move(step, 0)
            return "break"

    def key_tab(self, e):
        try:
            if e.widget.winfo_toplevel() is not self:
                return
        except Exception:
            return
        if isinstance(e.widget, (tk.Entry, tk.Text, tk.Listbox)):
            return
        if self.splash is None and not self.pad_menu_open():
            self.toggle_view()
        return "break"

    def move_selection(self, step):
        """Listede step kadar ilerler (klavye ve kumanda ortak). Seçim değiştiyse True."""
        order = sorted(self.rows)
        if not order:
            return False
        pos = order.index(self.selected) if self.selected in order else (-1 if step > 0 else len(order))
        pos = max(0, min(len(order) - 1, pos + step))
        idx = order[pos]
        if idx == self.selected:
            return False
        self.ui_sound.play("move")
        self.select(idx, sound=None)
        self._scroll_row_into_view(idx)
        return True

    def _scroll_row_into_view(self, idx):
        try:
            self.list_inner.update_idletasks()
            row = self.rows[idx]["row"]
            total = self.list_inner.winfo_height()
            view = self.list_canvas.winfo_height()
            top = self.list_canvas.canvasy(0)
            y, hgt = row.winfo_y(), row.winfo_height()
            if total <= 0:
                return
            if y < top:
                self.list_canvas.yview_moveto(y / total)
            elif y + hgt > top + view:
                self.list_canvas.yview_moveto((y + hgt - view) / total)
        except Exception:
            pass

    def key_launch(self, e):
        if self._home_on:
            self.home_activate()
            return "break"
        if isinstance(e.widget, (tk.Entry, tk.Text, tk.Listbox)):
            return
        try:
            if e.widget.winfo_toplevel() is not self:
                return
        except Exception:
            return
        if self.splash is not None:
            return "break"
        if self.pad_menu_open():
            self.pad_menu_activate()
            return "break"
        self.start_game()

    def make_row(self, i, g):
        row = tk.Frame(self.list_inner, bg=T["side"], cursor="hand2", height=50)
        row.pack(fill="x", pady=1)
        row.pack_propagate(False)

        strip = tk.Frame(row, width=3, bg=T["side"])
        strip.pack(side="left", fill="y")

        icon = ImageTk.PhotoImage(get_image(g, "ikon", (32, 32)))
        self.refs[f"side_{g['id']}"] = icon
        il = tk.Label(row, image=icon, bg=T["side"])
        il.pack(side="left", padx=(10, 8), pady=8)

        nl = tk.Label(row, text=g["name"], bg=T["side"], fg=T["text"], anchor="w",
                      font=(FONT, 11))
        nl.pack(side="left", fill="x", expand=True, padx=(0, 8))

        for w in (row, strip, il, nl):
            w.bind("<Button-1>", lambda e, i=i: self.select(i))
            w.bind("<Double-Button-1>", lambda e, i=i: (self.select(i), self.start_game()))
            w.bind("<Button-3>", self._open_manage)
            
        for w in (row, strip, il, nl):
            w.bind("<Enter>", lambda e, i=i: self._row_enter(i))
            w.bind("<Leave>", lambda e, i=i: self._row_leave(i))

        self.rows[i] = {"row": row, "strip": strip, "icon": il, "name": nl, "anim_pos": 0.0, "anim_job": None}

    def animate_row(self, i, target):
        if i not in self.rows:
            return
        if i == self.selected:
            return

        def step():
            if i not in self.rows:
                return
            cur_pos = self.rows[i].get("anim_pos", 0.0)
            new = cur_pos + (target - cur_pos) * 0.20
            
            if abs(new - target) < 0.02:
                new = target
                
            self.rows[i]["anim_pos"] = new
            self._draw_row_anim(i, new)
            
            if new != target:
                self.rows[i]["anim_job"] = self.after(15, step)
                
        if self.rows[i].get("anim_job"):
            try: self.after_cancel(self.rows[i]["anim_job"])
            except: pass
        self.rows[i]["anim_job"] = None
        step()

    def _draw_row_anim(self, i, pos):
        if i not in self.rows:
            return
        r = self.rows[i]
        bg_color = blend(T["side"], T["row_hover"], pos)
        
        r["row"].configure(bg=bg_color)
        r["icon"].configure(bg=bg_color)
        r["name"].configure(bg=bg_color, fg=blend(T["text"], T["title"], pos))
        
        if pos > 0.1:
            r["strip"].configure(bg=T["accent"])
        else:
            r["strip"].configure(bg=T["side"])

    def paint_row(self, i, hovering=False):
        if i not in self.rows:
            return
        r = self.rows[i]
        
        if i == self.selected:
            for w in (r["row"], r["strip"], r["icon"], r["name"]):
                w.configure(bg=T["row_sel"])
            r["strip"].configure(bg=T["accent"])
            r["name"].configure(fg=T["title"], font=(FONT, 11, "bold"))
        else:
            r["name"].configure(font=(FONT, 11))
            if r.get("anim_pos", 0.0) < 0.02:
                for w in (r["row"], r["strip"], r["icon"], r["name"]):
                    w.configure(bg=T["side"])
                r["name"].configure(fg=T["text"])

    def highlight(self):
        for i in self.rows:
            self.paint_row(i)

    def build_right(self):
        self.right = tk.Frame(self, bg=T["bg"])
        self.right.pack(side="right", fill="both", expand=True)

        self.bar = tk.Frame(self.right, bg=T["panel"], height=80)
        self.bar.pack(side="bottom", fill="x")
        self.bar.pack_propagate(False)
        tk.Frame(self.right, bg=T["divider"], height=1).pack(side="bottom", fill="x")
        self.build_music_bar()

        self.canvas = tk.Canvas(self.right, bg=T["bg"], highlightthickness=0)
        self.canvas.pack(side="top", fill="both", expand=True)

        # Sidebar Aç/Kapat Butonu
        self.toggle_btn = tk.Button(self.right, text="✕", command=self.toggle_sidebar,
                                    bg=T["panel"], fg=T["title"], font=(FONT, 14, "bold"),
                                    relief="flat", bd=0, cursor="hand2", width=3)
        self.toggle_btn.place(x=10, y=10) # Sağ canvas üzerinde başlangıç pozisyonu

        self._manage_menu = styled_menu(self.canvas)
        m = self._manage_menu
        m.add_command(label="Oyun yolunu değiştir", command=self.pick_path)
        m.add_command(label="Adı değiştir", command=self.rename_game)
        m.add_command(label="Oyun bilgilerini düzenle...", command=self.edit_info)
        info_menu = styled_menu(m)
        info_menu.add_command(label="Tüm mağazalardan (otomatik)", command=lambda: self.fetch_info())
        info_menu.add_separator()
        for label, src in (("Steam", "Steam"), ("Epic Games", "Epic Games"),
                           ("Microsoft Store / Xbox", "Microsoft Store"), ("GOG", "GOG"),
                           ("Riot (yerleşik bilgi)", "Riot"), ("Vikipedi / Wikidata", "Vikipedi")):
            info_menu.add_command(label=label, command=lambda s=src: self.fetch_info(s))
        info_menu.add_separator()
        info_menu.add_command(label="Farklı bir adla ara...", command=lambda: self.fetch_info_named())
        m.add_cascade(label="Bilgileri mağazadan getir", menu=info_menu)
        m.add_command(label="Görünümü değiştir: ızgara ⇄ detay (Tab)", command=self.toggle_view)
        m.add_command(label="Oyun klasörünü aç", command=self.open_install_dir)
        m.add_separator()
        
        kapak_menu = styled_menu(m)
        kapak_menu.add_command(label="Dosyadan seç...", command=lambda: self.set_image("kapak"))
        kapak_menu.add_command(label="URL'den indir...", command=lambda: self.set_image_url("kapak"))
        m.add_cascade(label="Kapak seç", menu=kapak_menu)

        ikon_menu = styled_menu(m)
        ikon_menu.add_command(label="Dosyadan seç...", command=lambda: self.set_image("ikon"))
        ikon_menu.add_command(label="URL'den indir...", command=lambda: self.set_image_url("ikon"))
        m.add_cascade(label="İkon seç", menu=ikon_menu)

        arkaplan_menu = styled_menu(m)
        arkaplan_menu.add_command(label="Dosyadan seç...", command=lambda: self.set_image("arkaplan"))
        arkaplan_menu.add_command(label="URL'den indir...", command=lambda: self.set_image_url("arkaplan"))
        m.add_cascade(label="Arka plan resmi seç", menu=arkaplan_menu)

        m.add_separator()

        vid = styled_menu(m)
        vid.add_command(label="Dosyadan seç...", command=lambda: self.set_game_file("video"))
        vid.add_command(label="YouTube linkinden indir...", command=lambda: self.set_game_url("video"))
        vid.add_separator()
        vid.add_command(label="Videoyu kaldır", command=lambda: self.remove_game_asset("video"))
        m.add_cascade(label="Arka plan videosu", menu=vid)

        mus = styled_menu(m)
        mus.add_command(label="Dosyadan seç...", command=lambda: self.set_game_file("muzik"))
        mus.add_command(label="YouTube linkinden indir...", command=lambda: self.set_game_url("muzik"))
        mus.add_separator()
        mus.add_command(label="Müziği kaldır", command=lambda: self.remove_game_asset("muzik"))
        m.add_cascade(label="Oyun müziği", menu=mus)

        m.add_separator()
        m.add_command(label="Tümünü otomatik ayarla (kapak, arka plan, ikon, fragman)",
                      command=lambda: self.auto_setup(self.current()))
        m.add_command(label="Her şeyi otomatik ayarla (tek tuş)", command=lambda: self.auto_setup(self.current()))
        m.add_command(label="Fragmanı otomatik indir", command=lambda: self.auto_trailer(self.current()))
        m.add_command(label="Oyunu kaldır", command=self.uninstall_game)
        m.add_command(label="Oyunu launcher'dan sil", command=self.delete_game)

        self.split_btn = SplitButton(
            self.canvas, "OYNA", self.start_game, self._open_manage, width=140, height=40
        )

        self.canvas.bind("<Configure>", self.on_canvas_configure)

    def _open_manage(self, event=None):
        self.ui_sound.play("menu")
        try:
            if event:
                x = event.x_root
                y = event.y_root
            else:
                x = self.split_btn.winfo_rootx()
                y = self.split_btn.winfo_rooty() + self.split_btn.winfo_height() + 2
            self._manage_menu.tk_popup(x, y)
        finally:
            self._manage_menu.grab_release()

    def on_canvas_configure(self, event=None):
        if self.redraw_job:
            self.after_cancel(self.redraw_job)
        self.redraw_job = self.after(80, self.redraw)

    def build_music_bar(self):
        bar = self.bar

        left = tk.Frame(bar, bg=T["panel"])
        left.pack(side="left", fill="both", expand=True, padx=(30, 10), pady=10)

        self.track_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self.track_var, bg=T["panel"], fg=T["text"],
                 anchor="w", font=(FONT, 12, "bold")).pack(fill="x")

        prog_wrap = tk.Frame(left, bg=T["panel"], height=16)
        prog_wrap.pack(fill="x", pady=(4, 0))
        prog_wrap.pack_propagate(False)

        self.prog_canvas = tk.Canvas(prog_wrap, bg=T["panel"], highlightthickness=0,
                                     height=6, bd=0, cursor="hand2")
        self.prog_canvas.pack(fill="x", side="left", expand=True, pady=6)
        self.prog_canvas.bind("<Configure>", lambda e: self._draw_progress())
        self.prog_canvas.bind("<Button-1>", self._seek_click)

        time_row = tk.Frame(left, bg=T["panel"])
        time_row.pack(fill="x")
        self.time_var = tk.StringVar(value="0:00 / 0:00")
        tk.Label(time_row, textvariable=self.time_var, bg=T["panel"], fg=T["muted"],
                 font=(FONT, 10), anchor="w").pack(side="left")

        ctl = tk.Frame(bar, bg=T["panel"])
        ctl.pack(side="left", padx=10)

        def ctl_btn(text, cmd, size=12):
            b = tk.Button(ctl, text=text, bg=T["panel"], fg=T["text"],
                          activebackground=T["chip_hover"], activeforeground="white",
                          relief="flat", bd=0, font=(FONT, size), width=2,
                          cursor="hand2", command=cmd)
            b.pack(side="left", padx=2)
            b.bind("<Enter>", lambda e: b.configure(bg=T["chip_hover"], fg=T["title"]))
            b.bind("<Leave>", lambda e: b.configure(bg=T["panel"], fg=T["text"]))
            return b

        self.prev_btn = ctl_btn("⏮", self.music_prev, 14)
        self.play_pause_btn = ctl_btn("▶", self.music_toggle, 16)
        self.play_pause_btn.configure(fg=T["accent"], font=(FONT, 16, "bold"))
        self.next_btn = ctl_btn("⏭", self.music_next, 14)

        right = tk.Frame(bar, bg=T["panel"])
        right.pack(side="right", padx=(10, 30))

        tk.Label(right, text="🔊", bg=T["panel"], fg=T["muted"],
                 font=(FONT, 12)).pack(side="left", padx=(0, 6))
        self.vol = tk.Scale(right, from_=0, to=100, orient="horizontal", length=100,
                            width=8, sliderlength=15, showvalue=0, bg=T["panel"],
                            troughcolor=T["chip"], highlightthickness=0, bd=0,
                            activebackground=T["accent"], command=self.on_volume)
        self.vol.set(int(self.music.volume * 100))
        self.vol.pack(side="left", padx=(0, 15))

        self.shuffle_var = tk.BooleanVar(value=bool(self.cfg["shuffle"]))
        self.pause_var = tk.BooleanVar(value=bool(self.cfg["pause_on_launch"]))

        mb = tk.Menubutton(right, text="♫", bg=T["chip"], fg=T["text"],
                           activebackground=T["chip_hover"], activeforeground="white",
                           relief="flat", bd=0, font=(FONT, 12), padx=12, pady=4,
                           cursor="hand2")
        m = styled_menu(mb)
        m.add_command(label="Playlist yöneticisi...", command=self.open_playlist)
        m.add_command(label="YouTube linkinden şarkı ekle...", command=self.add_playlist_url)
        m.add_command(label="Müzik klasörünü seç...", command=self.pick_music_folder)
        m.add_separator()
        m.add_checkbutton(label="Karışık çal", variable=self.shuffle_var, command=self.toggle_shuffle)
        m.add_checkbutton(label="Oyun açılınca müziği duraklat", variable=self.pause_var,
                          command=self.toggle_pause_on_launch)
        mb.configure(menu=m)
        hover(mb, T["chip"], T["chip_hover"])
        mb.pack(side="left")

    def _round_rect(self, c, x1, y1, x2, y2, r, fill):
        if x2 - x1 < 2*r:
            c.create_rectangle(x1, y1, x2, y2, fill=fill, outline="")
            return
        c.create_arc(x1, y1, x1+2*r, y2, start=90, extent=180, fill=fill, outline="")
        c.create_arc(x2-2*r, y1, x2, y2, start=270, extent=180, fill=fill, outline="")
        c.create_rectangle(x1+r, y1, x2-r, y2, fill=fill, outline="")

    def _draw_progress(self):
        if not hasattr(self, "prog_canvas"):
            return
        c = self.prog_canvas
        try:
            c.delete("all")
        except tk.TclError:
            return
        w = c.winfo_width()
        h = c.winfo_height()
        if w < 10 or h < 4:
            return
        self._round_rect(c, 0, h//2-3, w, h//2+3, 3, T["chip"])
        if self.music.ok and self.music.playing and not self.music.paused:
            self._wave_bars(c, w, h)
        pos = self._current_progress()
        if pos > 0:
            fill_x = int(w * pos)
            self._round_rect(c, 0, h//2-3, max(fill_x, 6), h//2+3, 3, T["accent"])
            cx = min(max(fill_x, 5), w-5)
            c.create_oval(cx-5, h//2-5, cx+5, h//2+5, fill=T["accent_hover"], outline="")
        # çalarken çubuklar canlı kalsın diye kısa aralıklarla yeniden çiz
        if self.music.ok and self.music.playing and not self.music.paused and getattr(self, "_wave_job", None) is None:
            self._wave_job = self.after(90, self._wave_tick)

    def _wave_tick(self):
        self._wave_job = None
        self._draw_progress()

    def _wave_bars(self, c, w, h):
        """Müzik çalarken ilerleme çubuğunun arkasında hareket eden ince ses çubukları."""
        import math
        t = time.perf_counter()
        n = max(16, w // 12)
        step = w / n
        for i in range(n):
            a = abs(math.sin(t * 5.0 + i * 0.63) * math.sin(t * 2.1 + i * 1.7))
            hh = max(2, int((h - 4) * (0.25 + 0.75 * a)))
            x = int(i * step + step / 2)
            c.create_line(x, h // 2 - hh // 2, x, h // 2 + hh // 2, fill=T["muted"], width=2)

    def _current_progress(self):
        if not self.music.ok or not self.music.current_file:
            return 0.0
        try:
            dur = self._audio_duration(self.music.current_file)
            if dur <= 0:
                return 0.0
            pos = self.music.get_pos()
            return max(0.0, min(1.0, pos / dur))
        except Exception:
            return 0.0

    def _audio_duration(self, path):
        if not path:
            return 0.0
        if path in self._duration_cache:
            return self._duration_cache[path]
        dur = 0.0
        try:
            from mutagen import File as MFile
            mf = MFile(path)
            if mf and mf.info:
                dur = float(mf.info.length)
        except Exception:
            pass
        if dur <= 0:
            try:
                ff = ffmpeg_exe()
                if ff:
                    ffprobe = ff.replace("ffmpeg", "ffprobe")
                    out = subprocess.check_output(
                        [ffprobe, "-v", "error", "-show_entries", "format=duration",
                         "-of", "default=nw=1:nk=1", path],
                        stderr=subprocess.DEVNULL)
                    dur = float(out.strip() or 0)
            except Exception:
                dur = 0.0
        self._duration_cache[path] = dur
        return dur

    def _seek_click(self, e):
        if not self.music.ok or not self.music.current_file:
            return
        w = self.prog_canvas.winfo_width()
        if w < 10:
            return
        pos = e.x / w
        dur = self._audio_duration(self.music.current_file)
        if dur <= 0:
            return
        target = pos * dur
        
        try:
            self.music.pg.mixer.music.play(start=target)
            self.music.playing = True
            self.music.paused = False
            self.music.paused_at = target
            self.music.play_start_time = time.time() - target
            self.update_music_ui()
        except Exception as ex:
            print("Seek hatası:", ex)

    def update_music_ui(self):
        if self.busy:
            self.track_var.set("⏳ " + (self.status["text"] or "Çalışıyor..."))
        elif not self.music.ok:
            self.track_var.set("Müzik kapalı (pygame kurulu değil)")
        elif self.music.mode == "game":
            self.track_var.set("♪ Oyun müziği")
        elif self.music.mode == "playlist" and self.music.playing:
            self.track_var.set("♪ " + self.music.current_name())
        elif not self.music.tracks:
            self.track_var.set("Playlist boş · ♫ menüsünden şarkı ekle")
        else:
            self.track_var.set("Müzik hazır")

        self.play_pause_btn.configure(
            text="⏸" if (self.music.playing and not self.music.paused) else "▶")

        dur = self._audio_duration(self.music.current_file) if self.music.current_file else 0
        pos = self.music.get_pos() if self.music.ok else 0
        def fmt(s):
            s = int(max(0, s))
            return f"{s//60}:{s%60:02d}"
        self.time_var.set(f"{fmt(pos)} / {fmt(dur)}")
        self._draw_progress()
        self.refresh_playlist_ui()

    def apply_music_for_game(self, g):
        if self._home_on:
            if self.music.ok:
                self.music.pause_now()
            self.update_music_ui()
            return
        if self._intro_music_block:
            self.update_music_ui()
            return
        if not self.music.ok:
            self.update_music_ui()
            return
        f = find_asset(g["id"], "muzik", AUDIO_EXTS) if g else None
        if f:
            self.music.play_game_file(f)
        elif self.music.mode != "playlist" or not self.music.playing:
            self.music.play_playlist()
        if self.user_paused:
            self.music.pause_now()
        self.update_music_ui()

    def music_toggle(self):
        self.music.toggle()
        self.user_paused = self.music.paused
        self.update_music_ui()

    def music_next(self):
        if self.music.tracks:
            self.music.next()
            self.user_paused = False
        self.update_music_ui()

    def music_prev(self):
        if self.music.tracks:
            self.music.prev()
            self.user_paused = False
        self.update_music_ui()

    def music_tick(self):
        if self.music.tick():
            self.update_music_ui()
        elif self.music.playing and not self.music.paused:
            self.update_music_ui()
        self.after(500, self.music_tick)

    def on_volume(self, value):
        v = int(float(value)) / 100
        self.music.set_volume(v)
        self.cfg["volume"] = v

    def pick_music_folder(self):
        folder = filedialog.askdirectory(title="Müzik klasörünü seç",
                                         initialdir=self.cfg["music_folder"])
        if folder:
            self.music.release()
            self.cfg["music_folder"] = folder
            self.save()
            self.music.scan(folder)
            self.apply_music_for_game(self.current())

    def toggle_shuffle(self):
        self.cfg["shuffle"] = self.shuffle_var.get()
        self.music.shuffle = self.cfg["shuffle"]
        self.save()

    def toggle_pause_on_launch(self):
        self.cfg["pause_on_launch"] = self.pause_var.get()
        self.save()

    def open_playlist(self):
        if self.pl_win is not None and self.pl_win.winfo_exists():
            self.pl_win.lift()
            self.refresh_playlist_ui()
            return
        win = tk.Toplevel(self)
        win.title("Playlist")
        win.geometry("600x800")
        win.minsize(500, 600)
        win.configure(bg=T["bg"])
        win.transient(self)
        self.pl_win = win

        tk.Label(win, text="PLAYLIST", bg=T["bg"], fg=T["muted"],
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(20, 10))

        body = tk.Frame(win, bg=T["bg"])
        body.pack(fill="both", expand=True, padx=20)
        sb = tk.Scrollbar(body, orient="vertical")
        self.pl_list = tk.Listbox(body, bg=T["panel"], fg=T["text"], selectbackground=T["row_sel"],
                                  selectforeground="white", relief="flat", highlightthickness=0,
                                  bd=0, font=(FONT, 14), activestyle="none",
                                  yscrollcommand=sb.set)
        sb.configure(command=self.pl_list.yview)
        sb.pack(side="right", fill="y")
        self.pl_list.pack(side="left", fill="both", expand=True)
        self.pl_list.bind("<Double-Button-1>", lambda e: self.play_selected())

        btns = tk.Frame(win, bg=T["bg"])
        btns.pack(fill="x", padx=20, pady=20)
        chip(btns, "YouTube linki ekle", self.add_playlist_url, primary=True, icon="＋", font=(FONT, 12)).pack(side="left")
        chip(btns, "Çal", self.play_selected, icon="▶", font=(FONT, 12)).pack(side="left", padx=10)
        chip(btns, "Sil", self.delete_selected, icon="🗑", font=(FONT, 12)).pack(side="left")
        chip(btns, "Spotify listesi", self.open_spotify_playlist, icon="♫", font=(FONT, 12)).pack(side="left", padx=10)
        self.refresh_playlist_ui()

    def refresh_playlist_ui(self):
        if self.pl_win is None or not self.pl_win.winfo_exists() or self.pl_list is None:
            return
        try:
            sel = self.pl_list.curselection()
            self.pl_list.delete(0, "end")
            for i, t in enumerate(self.music.tracks):
                name = os.path.splitext(os.path.basename(t))[0]
                playing = (self.music.mode == "playlist" and i == self.music.index)
                self.pl_list.insert("end", ("♪ " if playing else "  ") + name)
            if sel and sel[0] < self.pl_list.size():
                self.pl_list.selection_set(sel[0])
        except Exception:
            pass

    def play_selected(self):
        if self.pl_list is None:
            return
        sel = self.pl_list.curselection()
        if not sel:
            return
        self.music.play_playlist(sel[0])
        self.user_paused = False
        self.update_music_ui()

    def delete_selected(self):
        if self.pl_list is None:
            return
        sel = self.pl_list.curselection()
        if not sel:
            return
        path = self.music.tracks[sel[0]]
        name = os.path.splitext(os.path.basename(path))[0]
        if not messagebox.askyesno("Şarkıyı sil", f"\"{name}\" dosyası silinsin mi?",
                                    parent=self.pl_win):
            return
        if self.music.current_file == path:
            self.music.release()
        try:
            os.remove(path)
        except Exception as e:
            messagebox.showerror("Hata", f"Silinemedi:\n{e}", parent=self.pl_win)
        self.music.scan(self.cfg["music_folder"])
        self.apply_music_for_game(self.current())

    def check_idle(self):
        if self.busy:
            messagebox.showinfo("Bekle", "Şu an bir indirme / kopyalama sürüyor, bitmesini bekle.")
            return False
        return True

    def run_bg(self, fn, done=None, text="Çalışıyor...", refresh=True):
        self.busy = True
        self.status["text"] = text
        self.update_music_ui()

        def work():
            try:
                self.job_q.put((done, refresh, fn(), None))
            except Exception as e:
                self.job_q.put((done, refresh, None, e))

        threading.Thread(target=work, daemon=True).start()
        self.after(200, self.poll_jobs)

    def poll_jobs(self):
        try:
            done, refresh, res, err = self.job_q.get_nowait()
        except queue.Empty:
            self.track_var.set(self.status["text"] or "Çalışıyor...")
            self.after(200, self.poll_jobs)
            return
        self.busy = False
        self.status["text"] = ""
        if err:
            msg = re.sub(r"\x1b\[[0-9;]*m", "", str(err))[:400]
            messagebox.showerror(
                "Hata",
                msg + "\n\nİpucu: YouTube sık değişir. Güncellemek için:\npip install -U yt-dlp")
        elif done:
            done(res)
        if refresh:
            self.refresh_all()
        self.apply_music_for_game(self.current())

    def ask_url(self, title):
        url = simpledialog.askstring(title, "URL'yi yapıştır:", parent=self)
        if not url:
            return None
        url = url.strip()
        if not url.lower().startswith("http"):
            messagebox.showerror("Hata", "Geçerli bir link yapıştır (https://...)")
            return None
        return url

    def open_spotify_playlist(self):
        """Kayıtlı Spotify çalma listesini Spotify uygulamasında açar.
        Ses launcher'da çalmaz; launcher müziğini durdurur."""
        url = (self.cfg.get("spotify_playlist") or "").strip()
        if not url:
            url = (self.ask_url("Spotify çalma listesi linki (open.spotify.com/playlist/...)") or "").strip()
            if not url:
                return
            if "spotify" not in url.lower():
                messagebox.showwarning("Geçersiz link", "Lütfen bir Spotify çalma listesi linki girin.")
                return
            self.cfg["spotify_playlist"] = url
            self.save()
        try:
            if self.music.ok and self.music.playing and not self.music.paused:
                self.music.pause_now()
                self.user_paused = True
                self.update_music_ui()
            os.startfile(url)
        except Exception as e:
            messagebox.showerror("Hata", f"Spotify açılamadı:\n{e}")

    def add_playlist_url(self):
        if not self.check_idle():
            return
        url = self.ask_url("Playlist'e şarkı ekle")
        if not url:
            return
        folder = self.cfg["music_folder"]
        os.makedirs(folder, exist_ok=True)

        def done(title):
            self.music.scan(folder)

        self.run_bg(lambda: ydl_download(url, folder, "audio", status=self.status,
                                         allow_playlist=True),
                    done, "İndiriliyor...", refresh=False)

    def current(self):
        if 0 <= self.selected < len(self.games):
            return self.games[self.selected]
        return None

    def save(self):
        save_data(self.cfg, self.games)

    def select(self, i, force=False, sound="select"):
        if self.launching and self.launching.get("covering", True) and not force:
            return          # başlatma geçişi ekranı kaplarken gezinme yok (kapak yerine dönünce serbest)
        self._nav_dir = 0 if (self.selected == i or self.selected < 0) else (1 if i > self.selected else -1)
        self.selected = i
        self.highlight()
        g = self.current()
        gid = g["id"] if g else None
        self._sync_busy()
        if not force and gid is not None and gid == self.view_game_id:
            return
        
        self.view_game_id = gid
        if not force and sound and gid is not None:
            self.ui_sound.play(sound)
        fade = (not force) and gid is not None
        self.close_video()
        self.video_photo = None

        if g:
            self.title(f"Oyun Launcher - {g['name']}")
            icon = ImageTk.PhotoImage(get_image(g, "ikon", (64, 64)))
            self.refs["window_icon"] = icon
            try:
                self.iconphoto(True, icon)
            except Exception:
                pass
        else:
            self.title("Oyun Launcher")

        if self.view_mode == "grid":
            self.grid_on_select()
            self.update_accent(g, animate=self._accent_ready)
            self._accent_ready = True
            self.apply_music_for_game(g)
            return

        if g:
            self.open_video(g)
            
        self._detail_xf_from = self._detail_pil if fade else None   # arka plan çapraz solsun
        self.canvas.update()
        self.redraw()
        if g and fade:
            self._cover_expand(g, getattr(self, "_nav_dir", 0))   # kapak yönden girer, kendi yerine küçülür
        self.update_accent(g, animate=self._accent_ready)
        self._accent_ready = True
        self.apply_music_for_game(g)

    def start_fade(self):
        """Oyun değişince sağ panel siyahtan yumuşakça açılır (stipple ile ucuz fade)."""
        c = self.canvas
        w, h = c.winfo_width(), c.winfo_height()
        if w < 50 or h < 50:
            return
        self._fade_id += 1
        token = self._fade_id
        c.delete("fade")
        c.create_rectangle(0, 0, w, h, fill="#000000", outline="", stipple="gray75", tags="fade")
        stipples = ("gray75", "gray50", "gray25", "gray12")

        def step(k):
            if token != self._fade_id:
                return
            try:
                if not c.find_withtag("fade"):
                    return  # redraw overlay'i silmiş
                if k >= len(stipples):
                    c.delete("fade")
                    return
                c.itemconfigure("fade", stipple=stipples[k])
            except tk.TclError:
                return
            self.after(38, lambda: step(k + 1))

        self.after(38, lambda: step(1))

    def open_video(self, g):
        path = find_asset(g["id"], "video", VIDEO_EXTS)
        if not path:
            return
            
        try:
            import cv2
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                cap.release()
                return
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            self.video_delay = int(1000 / max(10, min(fps, 30)))
            self.cap = cap
        except ImportError:
            pass

    def close_video(self):
        if self.video_job:
            try:
                self.after_cancel(self.video_job)
            except Exception:
                pass
            self.video_job = None
        if self.cap is not None:
            self.cap.release()
            self.cap = None

    def compose_frame(self, frame, target_w, target_h):
        import cv2
        import numpy as np
        
        fh, fw = frame.shape[:2]
        s = max(target_w / fw, target_h / fh)
        nw, nh = max(target_w, int(fw * s + 0.5)), max(target_h, int(fh * s + 0.5))
        interp = cv2.INTER_AREA if s < 1 else cv2.INTER_LINEAR
        frame = cv2.resize(frame, (nw, nh), interpolation=interp)
        x0, y0 = (nw - target_w) // 2, (nh - target_h) // 2
        frame = frame[y0:y0 + target_h, x0:x0 + target_w]
        frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        
        img = Image.fromarray(frame).convert("RGBA")
        return round_corners(img, radius=16)

    def video_tick(self):
        import cv2
        self.video_job = None
        if self.cap is None or self.video_item is None:
            return
        if self._hidden or self.idle is not None or self.state() == "iconic":  # tepsideyken / küçükken / boştayken kare çözme
            self.video_job = self.after(500, self.video_tick)
            return
        t0 = time.perf_counter()
        ok, frame = self.cap.read()
        if not ok:
            self.cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
            ok, frame = self.cap.read()
        if ok:
            try:
                self.video_photo = ImageTk.PhotoImage(self.compose_frame(frame, self.vid_w, self.vid_h))
                self.canvas.itemconfigure(self.video_item, image=self.video_photo)
            except Exception:
                pass
        elapsed = int((time.perf_counter() - t0) * 1000)
        self.video_job = self.after(max(1, self.video_delay - elapsed), self.video_tick)

    def redraw(self):
        self.redraw_job = None
        if self.view_mode == "grid":
            return  # ayrıntı tuvali gizli; ızgarada boşuna çizme / video çözme
        if getattr(self, "_cx_active", False):
            # kapak animasyonu sürerken yeniden çizim (ör. boyut hesabı bitince) onu silmesin
            self.after(90, self.redraw)
            return
        w, h = self.canvas.winfo_width(), self.canvas.winfo_height()
        if w < 50 or h < 50:
            return
        c = self.canvas
        c.delete("all")
        self.bg_item = None
        self.video_item = None
        g = self.current()

        if not g:
            c.create_text(w // 2, h // 2, fill=T["muted"], font=(FONT, 16), justify="center",
                          text="Henüz oyun eklenmedi.\n\nSoldaki \"Oyun ekle\" düğmesiyle başla.")
            return

        self.vsize = (w, h)
        
        # 1. KATMAN: Tam Ekran Arka Plan Resmi
        hero_pil = hero_image(g, w, h, float(self.cfg.get("hero_bright", 0.3))).convert("RGB")
        hero_photo = ImageTk.PhotoImage(hero_pil)
        self.refs["hero"] = hero_photo
        self.bg_item = c.create_image(0, 0, image=hero_photo, anchor="nw")
        xf_from, self._detail_xf_from = self._detail_xf_from, None
        self._xf_tok["detail"] = self._xf_tok.get("detail", 0) + 1
        if xf_from is not None and xf_from.size == hero_pil.size and self._xf_on():
            self.xfade_start("detail", c, self.bg_item, xf_from, hero_pil)
        self._detail_pil = hero_pil

        # --- VİDEO ALANI HESAPLAMA (Sağ üste yakın) ---
        self.vid_w = int(w * 0.55) # Genişlik %55
        self.vid_h = int(self.vid_w * 9 / 16)
        
        # Sağ üst köşeye yerleştir, üstten 50px, sağdan 40px boşluk
        vid_x = w - self.vid_w - 40
        vid_y = 50

        # 2. KATMAN: Video (Eğer varsa)
        if self.cap is not None:
            c.create_rectangle(vid_x-4, vid_y-4, vid_x+self.vid_w+4, vid_y+self.vid_h+4, 
                               fill="#000000", outline=T["accent"], width=2, tags=("acc_line",))
            self.video_item = c.create_image(vid_x, vid_y, anchor="nw")
        elif find_asset(g["id"], "video", VIDEO_EXTS):
            c.create_text(vid_x + self.vid_w/2, vid_y + self.vid_h/2, text="Video Yükleniyor...",
                          fill=T["muted"], font=(FONT, 14))

        # 3. KATMAN: Kapak ve Metinler (Videonun altına, sola hizala)
        cw, ch = 160, 224  # Kapak boyutu
        
        cx = 40 # Soldan boşluk
        cy = vid_y + self.vid_h + 40 # Videonun hemen altı
        
        self._detail_cover_rect = (cx, cy, cw, ch)
        cover_photo = ImageTk.PhotoImage(get_image(g, "kapak", (cw, ch)))
        self.refs["cover"] = cover_photo
        
        c.create_rectangle(cx + 4, cy + 6, cx + cw + 4, cy + ch + 6, fill="#000", outline="", stipple="gray50")
        c.create_image(cx, cy, image=cover_photo, anchor="nw")

        tx = cx + cw + 24
        wrap = max(200, w - tx - 40) 
        
        c.create_text(tx, cy + 10, text=g["name"], anchor="nw", fill=T["title"],
                      font=(FONT, 22, "bold"), width=wrap)
        
        c.create_rectangle(tx, cy + 45, tx + 30, cy + 49, fill=T["accent"], outline="",
                          tags=("acc_fill",))

        # Butonu yerleştir
        self.split_btn.update_idletasks()
        py = cy + 70
        c.create_window(tx, py, window=self.split_btn, anchor="nw")

        self.draw_info_panel(c, g, cx, cy + ch + 36, w, h)

        if self.cap is not None and self.video_job is None:
            self.video_job = self.after(1, self.video_tick)

    # ---------------------------------------------------------- OYUN BİLGİ PANELİ
    def install_dir(self, g):
        d = g.get("install_dir", "")
        if d and os.path.isdir(d):
            return d
        p = g.get("path", "")
        if p and not ex.is_uri(p) and os.path.exists(p):
            return os.path.dirname(p)
        return ""

    def fmt_size(self, n):
        units = ["B", "KB", "MB", "GB", "TB"]
        n = float(n)
        i = 0
        while n >= 1024 and i < len(units) - 1:
            n /= 1024
            i += 1
        return f"{int(n)} {units[i]}" if i < 2 else f"{n:.2f} {units[i]}"

    def request_size(self, g):
        gid = g["id"]
        d = self.install_dir(g)
        if not d or g["path"].lower().endswith(".lnk"):
            self.size_cache[gid] = None
            return
        if gid in self.size_cache or gid in self.size_busy:
            return
        self.size_busy.add(gid)

        def work():
            total = 0
            for root, _, files in os.walk(d):
                for f in files:
                    try:
                        total += os.path.getsize(os.path.join(root, f))
                    except OSError:
                        pass
            self.size_cache[gid] = total
            self.size_busy.discard(gid)
            self.info_dirty = True

        threading.Thread(target=work, daemon=True).start()

    def info_poll(self):
        if self.info_dirty:
            self.info_dirty = False
            self.redraw()
            if self.view_mode == "grid" and self.grid_m and self.grid_m.get("list"):
                self._list_draw()        # boyut hesaplanınca liste/panel güncellensin
        self.after(1000, self.info_poll)

    def draw_info_panel(self, c, g, x, y, w, h):
        pw = w - x - 40
        ph = min(h - y - 30, 480)
        if pw < 360 or ph < 190:
            return

        try:   # cam efekti: arkadaki görsel bulanıklaşır, üstüne yarı saydam koyu zemin biner
            panel = vfx.glass_image(self._backdrop(int(w), int(h)), (x, y, x + pw, y + ph), radius=16,
                                    blur=20, tint=(8, 10, 24), tint_a=int(self.cfg.get("glass_tint", 150)),
                                    border_a=0)
        except Exception:
            panel = Image.new("RGBA", (pw, ph), (0, 0, 0, 0))
            ImageDraw.Draw(panel).rounded_rectangle(
                [0, 0, pw - 1, ph - 1], radius=16, fill=(8, 10, 24, 200))
        self.refs["info_panel"] = ImageTk.PhotoImage(panel)
        c.create_image(x, y, image=self.refs["info_panel"], anchor="nw")
        c.create_polygon(_rr_points(x, y, x + pw - 1, y + ph - 1, 16), smooth=True, fill="",
                         outline=blend("#0b0d1a", T["accent"], 0.45), width=1, tags=("acc_panel",))

        pad = 22
        c.create_text(x + pad, y + 18, text="AYRINTILAR", anchor="nw", fill=T["muted"],
                      font=(FONT, 10, "bold"))
        c.create_rectangle(x + pad, y + 40, x + pad + 26, y + 43, fill=T["accent"], outline="",
                          tags=("acc_fill",))

        gid = g["id"]
        self.request_size(g)
        if gid in self.size_cache:
            v = self.size_cache[gid]
            size_txt = self.fmt_size(v) if v is not None else "Hesaplanamadı"
        else:
            size_txt = "Hesaplanıyor..."

        last = g.get("last_played") or ""
        if last:
            try:
                last = datetime.fromisoformat(last).strftime("%d.%m.%Y %H:%M")
            except Exception:
                pass
        count = int(g.get("launch_count", 0) or 0)
        exe = ex.display_target(g)

        items = [
            ("KURULU BOYUT", size_txt),
            ("YAYINCI", g.get("publisher", "")),
            ("GELİŞTİRİCİ", g.get("developer", "")),
            ("ÇIKIŞ TARİHİ", g.get("release", "")),
            ("TÜR", g.get("genre", "")),
            ("SON OYNANMA", last or "Henüz oynanmadı"),
            ("BAŞLATMA SAYISI", f"{count} kez" if count else "—"),
            ("TOPLAM OYNANMA", fmt_playtime(g.get("play_seconds", 0)) or "—"),
            ("ÇALIŞTIRILAN DOSYA", exe),
        ]

        # Explorer "Ayrıntılar" görünümü: tek sütun, etiket solda, değer sağda, ince ayırıcılar
        label_w = 190
        row_h = 30
        gy = y + 58
        for n, (label, val) in enumerate(items):
            ry = gy + n * row_h
            missing = not str(val).strip()
            c.create_text(x + pad, ry + 6, text=label, anchor="nw", fill=T["muted"], font=(FONT, 9, "bold"))
            c.create_text(x + pad + label_w, ry + 6, text=("Bilinmiyor" if missing else val), anchor="nw",
                          fill=(T["muted"] if missing else T["title"]), font=(FONT, 10),
                          width=pw - 2 * pad - label_w)
            c.create_line(x + pad, ry + row_h - 1, x + pw - pad, ry + row_h - 1, fill="#3a3f5c")
        cur = gy + len(items) * row_h + 12

        loc = self.install_dir(g) or "Oyun yolu seçilmedi"
        c.create_text(x + pad, cur + 6, text="KURULUM KONUMU", anchor="nw", fill=T["muted"],
                      font=(FONT, 9, "bold"))
        c.create_text(x + pad + label_w, cur + 6, text=loc, anchor="nw", fill=T["text"], font=(FONT, 10),
                      width=pw - 2 * pad - label_w)
        cur += 58

        btn_y = y + ph - 54
        desc = (g.get("desc") or "").strip()
        if desc and cur + 70 < btn_y:
            if len(desc) > 320:
                desc = desc[:317].rstrip() + "..."
            c.create_text(x + pad, cur, text="HAKKINDA", anchor="nw", fill=T["muted"],
                          font=(FONT, 8, "bold"))
            c.create_text(x + pad, cur + 16, text=desc, anchor="nw", fill=T["text"],
                          font=(FONT, 10), width=pw - 2 * pad)

        if self.info_btns is None:
            self.info_btns = [
                chip(self.canvas, "Klasörü aç", self.open_install_dir, icon="📁", font=(FONT, 10)),
                chip(self.canvas, "Bilgileri düzenle", self.edit_info, icon="✎", font=(FONT, 10)),
                chip(self.canvas, "Bilgileri getir", self.fetch_info, primary=True, icon="⬇",
                     font=(FONT, 10)),
            ]
            self._primary_btns.append(self.info_btns[2])
        bx = x + pad
        for b in self.info_btns:
            c.create_window(bx, btn_y, window=b, anchor="nw")
            b.update_idletasks()
            bx += b.winfo_reqwidth() + 10

    def open_install_dir(self):
        g = self.current()
        d = self.install_dir(g) if g else ""
        if not d:
            messagebox.showinfo("Klasör", "Önce oyunun yolunu seçmelisin.")
            return
        try:
            if sys.platform.startswith("win"):
                os.startfile(d)
            else:
                subprocess.Popen(["xdg-open", d])
        except Exception as e:
            messagebox.showerror("Hata", f"Klasör açılamadı:\n{e}")

    def edit_info(self):
        g = self.current()
        if not g:
            return
        win = tk.Toplevel(self)
        win.title("Oyun bilgileri")
        win.configure(bg=T["bg"])
        win.transient(self)
        win.resizable(False, False)

        fields = [("publisher", "Yayıncı"), ("developer", "Geliştirici"),
                  ("release", "Çıkış tarihi"), ("genre", "Tür"),
                  ("args", "Başlatma parametreleri")]
        vars_ = {}
        for r, (k, label) in enumerate(fields):
            tk.Label(win, text=label, bg=T["bg"], fg=T["muted"], font=(FONT, 10)
                     ).grid(row=r, column=0, sticky="w", padx=(22, 12), pady=8)
            v = tk.StringVar(value=g.get(k, ""))
            tk.Entry(win, textvariable=v, width=42, bg=T["panel"], fg=T["text"],
                     insertbackground=T["text"], relief="flat", font=(FONT, 11)
                     ).grid(row=r, column=1, padx=(0, 22), pady=8, ipady=5)
            vars_[k] = v

        n = len(fields)
        admin_var = tk.BooleanVar(value=bool(g.get("admin")))
        direct_var = tk.BooleanVar(value=bool(g.get("direct")))
        opts = tk.Frame(win, bg=T["bg"])
        opts.grid(row=n, column=1, sticky="w", pady=(0, 6))

        def _check(text, var):
            return tk.Checkbutton(opts, text=text, variable=var, bg=T["bg"], fg=T["text"],
                                  selectcolor=T["panel"], activebackground=T["bg"],
                                  activeforeground=T["title"], font=(FONT, 10))
        _check("Yönetici olarak çalıştır", admin_var).pack(anchor="w")
        if g.get("source") == "EA app":
            _check("EA app yerine exe'yi doğrudan başlat", direct_var).pack(anchor="w")

        tk.Label(win, text="Açıklama", bg=T["bg"], fg=T["muted"], font=(FONT, 10)
                 ).grid(row=n + 1, column=0, sticky="nw", padx=(22, 12), pady=8)
        txt = tk.Text(win, width=42, height=6, bg=T["panel"], fg=T["text"],
                      insertbackground=T["text"], relief="flat", font=(FONT, 11), wrap="word")
        txt.insert("1.0", g.get("desc", ""))
        txt.grid(row=n + 1, column=1, padx=(0, 22), pady=8)

        def save():
            for k, v in vars_.items():
                g[k] = v.get().strip()
            g["admin"] = admin_var.get()
            g["direct"] = direct_var.get()
            g["desc"] = txt.get("1.0", "end").strip()
            self.save()
            win.destroy()
            self.redraw()

        row = tk.Frame(win, bg=T["bg"])
        row.grid(row=n + 2, column=0, columnspan=2, pady=(6, 18))
        chip(row, "Kaydet", save, primary=True, font=(FONT, 10)).pack(side="left", padx=6)
        chip(row, "Vazgeç", win.destroy, font=(FONT, 10)).pack(side="left", padx=6)

    # ------------------------------------------------------------ OYUN BİLGİSİ (TÜM MAĞAZALAR)
    def fetch_steam_info(self):  # eski ad (uyumluluk)
        self.fetch_info("Steam")

    def fetch_info_named(self, provider=None):
        g = self.current()
        if not g:
            return
        n = simpledialog.askstring("Farklı adla ara", "Aranacak oyun adı:",
                                   initialvalue=g["name"], parent=self)
        if n and n.strip():
            self.fetch_info(provider, n.strip())

    def fetch_info(self, provider=None, name=None):
        """Yayıncı / geliştirici / tarih / tür / açıklamayı mağazalardan getirir.
        provider=None: Steam, Epic, Microsoft Store (Xbox), GOG, Riot ve Vikipedi birlikte aranır."""
        g = self.current()
        if not g or not self.check_idle():
            return
        name = re.sub(r"[™®©]", "", name or g["name"]).strip() or g["name"]
        label = provider or "tüm mağazalar"
        self.run_bg(lambda: ex.fetch_game_info(g, name, only=provider),
                    lambda res: self.show_info_results(g, res, name, provider),
                    f"Bilgiler alınıyor ({label})...", refresh=False)

    def show_info_results(self, g, res, name, provider):
        cands = ([res["merged"]] if res.get("merged") else []) + list(res["results"])
        if not cands:
            lines = [f"\"{name}\" için sonuç bulunamadı.", "",
                     "Denenen kaynaklar: " + ", ".join(res["tried"])]
            if res["errors"]:
                lines += ["", "Ulaşılamayan kaynaklar:"] + [f"• {k}: {v}" for k, v in res["errors"].items()]
            lines += ["", "Farklı bir adla aramak ister misin?"]
            if messagebox.askyesno("Bilgi bulunamadı", "\n".join(lines)):
                self.fetch_info_named(provider)
            return

        win = tk.Toplevel(self)
        win.title("Oyun bilgileri")
        win.configure(bg=T["bg"])
        win.transient(self)
        win.geometry("860x780")
        win.minsize(720, 660)
        tk.Label(win, text=f"\"{name}\" için bulunanlar", bg=T["bg"], fg=T["title"],
                 font=(FONT, 15, "bold")).pack(anchor="w", padx=24, pady=(20, 2))
        tk.Label(win, text="Bir kaynak seç. \"Birleşik\", her alanı en uygun kaynaktan alır.",
                 bg=T["bg"], fg=T["muted"], font=(FONT, 10)).pack(anchor="w", padx=24)

        sel = tk.IntVar(value=0)
        lst = tk.Frame(win, bg=T["bg"])
        lst.pack(fill="x", padx=24, pady=(12, 6))
        prev = tk.Frame(win, bg=T["panel"])
        prev.pack(fill="both", expand=True, padx=24, pady=(6, 8))
        fields = [("publisher", "YAYINCI"), ("developer", "GELİŞTİRİCİ"), ("release", "ÇIKIŞ TARİHİ"),
                  ("genre", "TÜR"), ("desc", "AÇIKLAMA")]
        vars_ = {k: tk.StringVar() for k, _ in fields}
        for k, label in fields:
            tk.Label(prev, text=label, bg=T["panel"], fg=T["muted"], font=(FONT, 8, "bold")
                     ).pack(anchor="w", padx=16, pady=(12, 0))
            tk.Label(prev, textvariable=vars_[k], bg=T["panel"], fg=T["title"], font=(FONT, 11),
                     justify="left", anchor="w", wraplength=740).pack(anchor="w", padx=16)

        def show(*_):
            r = cands[sel.get()]
            src = r.get("fields_from") or {}
            for k, _l in fields:
                v = r.get(k) or "—"
                if src.get(k):
                    v += f"    · {src[k]}"
                vars_[k].set(v)

        for idx, r in enumerate(cands):
            if r["source"] == "Birleşik":
                txt = "★ Birleşik (önerilen): her alan en uygun kaynaktan"
            else:
                low = r["score"] < 0.7
                txt = f"{r['source']}  —  {r['found']}   (%{int(r['score'] * 100)} eşleşme" \
                      + (", düşük" if low else "") + ")"
            tk.Radiobutton(lst, text=txt, variable=sel, value=idx, command=show, anchor="w",
                           bg=T["bg"], fg=T["text"], selectcolor=T["panel"], activebackground=T["bg"],
                           activeforeground=T["title"], font=(FONT, 11)).pack(fill="x", pady=1)
        show()

        over = tk.BooleanVar(value=True)
        missing = [k for k in ("kapak", "arkaplan") if not find_asset(g["id"], k)]
        has_art = any((r.get("art") or {}).get(k) for r in cands for k in ("kapak", "arkaplan"))
        art_var = tk.BooleanVar(value=bool(missing))
        opts = tk.Frame(win, bg=T["bg"])
        opts.pack(fill="x", padx=24)

        def _check(text, var):
            tk.Checkbutton(opts, text=text, variable=var, bg=T["bg"], fg=T["text"],
                           selectcolor=T["panel"], activebackground=T["bg"],
                           activeforeground=T["title"], font=(FONT, 10)).pack(anchor="w")
        _check("Dolu alanların üzerine yaz", over)
        if has_art:
            _check("Eksik kapak / arka plan görsellerini de indir", art_var)

        def apply():
            r = cands[sel.get()]
            for k, _l in fields:
                v = r.get(k)
                if v and (over.get() or not g.get(k)):
                    g[k] = v
            self.save()
            art = r.get("art") if (has_art and art_var.get()) else None
            win.destroy()
            if art:
                self.run_bg(lambda: self._download_art(g, art), None, "Görseller indiriliyor...")
            else:
                self.redraw()

        def again():
            win.destroy()
            self.fetch_info_named(provider)

        row = tk.Frame(win, bg=T["bg"])
        row.pack(fill="x", padx=24, pady=(10, 20))
        chip(row, "Uygula", apply, primary=True, font=(FONT, 11)).pack(side="left")
        chip(row, "Başka adla ara", again, font=(FONT, 11)).pack(side="left", padx=8)
        chip(row, "Vazgeç", win.destroy, font=(FONT, 11)).pack(side="left")
        if res["errors"]:
            tk.Label(win, text="Ulaşılamayan kaynaklar: " + ", ".join(res["errors"]), bg=T["bg"],
                     fg=T["muted"], font=(FONT, 9)).pack(anchor="w", padx=24, pady=(0, 12))

    def _download_art(self, g, art):
        """Yalnızca eksik olan kapak / arka planı indirir (elle koyduklarına dokunmaz)."""
        for kind in ("kapak", "arkaplan", "ikon"):
            if find_asset(g["id"], kind):
                continue
            for url in art.get(kind, []):
                img = ex.load_art(url)
                if img is None:
                    continue
                img.thumbnail((2560, 2560))
                remove_assets(g["id"], kind)
                img.save(os.path.join(ASSETS_DIR, f"{g['id']}_{kind}.png"), "PNG")
                break

    def sort_games(self):
        """Oyunları ada göre sıralar; seçili oyun yerini korur."""
        cur = self.current()
        cid = cur["id"] if cur else None
        self.games.sort(key=lambda g: name_sort_key(g["name"]))
        if cid is not None:
            self.selected = next((i for i, g in enumerate(self.games) if g["id"] == cid), self.selected)

    def refresh_all(self):
        self.sort_games()
        sig = tuple(g["id"] for g in self.games)
        self.build_list(animate=(sig != self._list_sig))
        self._list_sig = sig
        if self.view_mode == "grid":
            self.grid_rebuild()
        self.select(self.selected, force=True)

    def add_game(self):
        path = filedialog.askopenfilename(
            title="Oyunun .exe dosyasını seç",
            filetypes=[("Çalıştırılabilir dosyalar", "*.exe *.lnk *.bat"), ("Tüm dosyalar", "*.*")])
        if not path:
            return
        default = os.path.splitext(os.path.basename(path))[0]
        name = simpledialog.askstring("Oyun adı", "Oyunun adı:", initialvalue=default, parent=self)
        if not name:
            return
        used = {g["id"] for g in self.games}
        n = 1
        while f"oyun{n}" in used:
            n += 1
        gid = f"oyun{n}"
        self.games.append({"id": gid, "name": name.strip(), "path": path,
                           "last_played": "", "added": _today(), "color": color_for(gid)})
        self.save()
        self.search_var.set("")
        self.selected = len(self.games) - 1
        self._notify("info", "Oyun eklendi", name.strip())
        self.refresh_all()

    def pick_path(self):
        g = self.current()
        if not g:
            return False
        path = filedialog.askopenfilename(
            title=f"{g['name']} için oyunun .exe dosyasını seç",
            filetypes=[("Çalıştırılabilir dosyalar", "*.exe *.lnk *.bat"), ("Tüm dosyalar", "*.*")])
        if path:
            g["path"] = path
            self.size_cache.pop(g["id"], None)
            self.save()
            self.redraw()
            return True
        return False

    def rename_game(self):
        g = self.current()
        if not g:
            return
        name = simpledialog.askstring("Adı değiştir", "Yeni ad:", initialvalue=g["name"], parent=self)
        if name and name.strip():
            g["name"] = name.strip()
            self.save()
            self.refresh_all()

    def set_image(self, kind):
        g = self.current()
        if not g:
            return
        labels = {"kapak": "kapak", "arkaplan": "arka plan resmi", "ikon": "ikon"}
        src = filedialog.askopenfilename(
            title=f"{g['name']} için {labels[kind]} seç",
            filetypes=[("Görseller", "*.png *.jpg *.jpeg *.webp *.ico"), ("Tüm dosyalar", "*.*")])
        if not src:
            return
        ext = os.path.splitext(src)[1].lower()
        if ext not in EXTS:
            messagebox.showerror("Hata", "Desteklenen uzantılar: png, jpg, jpeg, webp, ico")
            return
        remove_assets(g["id"], kind)
        shutil.copy(src, os.path.join(ASSETS_DIR, f"{g['id']}_{kind}{ext}"))
        self.refresh_all()

    def set_image_url(self, kind):
        g = self.current()
        if not g or not self.check_idle():
            return
        url = simpledialog.askstring("Görsel İndir", f"{kind.capitalize()} için URL'yi yapıştır:", parent=self)
        if not url:
            return
        url = url.strip()
        
        def download():
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            try:
                with urllib.request.urlopen(req, timeout=10) as response:
                    data = response.read()
                import io
                img = Image.open(io.BytesIO(data)).convert("RGBA")
                remove_assets(g["id"], kind)
                dst = os.path.join(ASSETS_DIR, f"{g['id']}_{kind}.png")
                img.save(dst, "PNG")
            except Exception as e:
                raise Exception(f"Resim indirilemedi. Hata: {e}")

        self.run_bg(download, None, "İndiriliyor...")
        self.apply_music_for_game(self.current())

    def need_video(self):
        messagebox.showerror("Eksik paket",
                             "Video arka plan için şu paket gerekli:\n\npip install opencv-python")

    def set_game_file(self, kind):
        g = self.current()
        if not g or not self.check_idle():
            return
        if kind == "video":
            path = find_asset(g["id"], "video", VIDEO_EXTS)
            if not path:
                try:
                    import cv2
                except ImportError:
                    self.need_video()
                    return
            exts, label, ftypes = VIDEO_EXTS, "arka plan videosu", [
                ("Videolar", "*.mp4 *.webm *.mkv *.avi *.mov"), ("Tüm dosyalar", "*.*")]
        else:
            exts, label, ftypes = AUDIO_EXTS, "oyun müziği", [
                ("Ses dosyaları", "*.mp3 *.ogg *.wav *.flac"), ("Tüm dosyalar", "*.*")]
        src = filedialog.askopenfilename(title=f"{g['name']} için {label} seç", filetypes=ftypes)
        if not src:
            return
        ext = os.path.splitext(src)[1].lower()
        if ext not in exts:
            messagebox.showerror("Hata", "Desteklenen uzantılar: " + ", ".join(exts))
            return
        if kind == "video":
            self.close_video()
            self.video_photo = None
        else:
            self.music.release()
        remove_assets(g["id"], kind)
        dst = os.path.join(ASSETS_DIR, f"{g['id']}_{kind}{ext}")
        self.run_bg(lambda: shutil.copy(src, dst), None, "Kopyalanıyor...")

    def set_game_url(self, kind):
        g = self.current()
        if not g or not self.check_idle():
            return
        if kind == "video":
            try:
                import cv2
            except ImportError:
                self.need_video()
                return
        url = self.ask_url("Arka plan videosu" if kind == "video" else "Oyun müziği")
        if not url:
            return
        if kind == "video":
            self.close_video()
            self.video_photo = None
        else:
            self.music.release()
        remove_assets(g["id"], kind)
        name = f"{g['id']}_{kind}"
        ykind = "video" if kind == "video" else "audio"
        self.run_bg(lambda: ydl_download(url, ASSETS_DIR, ykind, out_name=name,
                                         status=self.status),
                    None, "İndiriliyor...")

    def auto_trailer(self, g=None):
        """Oyun adıyla YouTube'da resmi fragmanı arar ve arka plan videosu olarak indirir.
        g verilirse yalnızca o oyun, verilmezse videosu olmayan tüm oyunlar sırayla işlenir."""
        if not self.check_idle():
            return
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.need_video()
            return
        if g:
            targets = [g]
        else:
            targets = [x for x in self.games if not find_asset(x["id"], "video", VIDEO_EXTS)]
        if not targets:
            self.show_toast("Tüm oyunların arka plan videosu zaten var.", timeout=4000)
            return
        if g and find_asset(g["id"], "video", VIDEO_EXTS):
            self.close_video()
            self.video_photo = None
            remove_assets(g["id"], "video")
        self.close_video()
        self.video_photo = None
        ids = [(x["id"], x["name"]) for x in targets]

        def work():
            ok = 0
            for gid, name in ids:
                self.status["text"] = f"Fragman aranıyor: {name}"
                try:
                    ydl_download(f"ytsearch1:{name} official trailer", ASSETS_DIR, "video",
                                 out_name=f"{gid}_video", status=self.status)
                    ok += 1
                except Exception:
                    pass   # bulunamayan ya da indirilemeyen oyun atlanır
            return ok

        def done(n):
            self.refresh_all()
            self.apply_music_for_game(self.current())
            self.show_toast(f"{n}/{len(ids)} oyuna fragman indirildi. (Yanlış video çıkarsa Arka plan videosu menüsünden değiştir.)",
                            timeout=7000)

        self.run_bg(work, done, f"Fragman indiriliyor ({len(ids)} oyun)...")

    def set_image_keys(self):
        k = simpledialog.askstring("Google Görseller API", "API anahtarı (key):",
                                   initialvalue=self.cfg.get("gcs_key", ""), parent=self)
        if k is None:
            return
        cx = simpledialog.askstring("Google Görseller API", "Arama motoru kimliği (cx):",
                                    initialvalue=self.cfg.get("gcs_cx", ""), parent=self)
        if cx is None:
            return
        self.cfg["gcs_key"] = k.strip()
        self.cfg["gcs_cx"] = cx.strip()
        self.save()
        messagebox.showinfo("Kaydedildi", "Görsel arama anahtarı kaydedildi.")

    def _fetch_google_art(self, gid, name):
        """Eksik kapak, ikon ve arka planı Google'da 'oyun adı + cover art / icon / wallpaper' ile arayıp
        ilk sonucu indirir. Elle koyulmuş dosyalara dokunmaz."""
        key, cx = self.cfg.get("gcs_key", ""), self.cfg.get("gcs_cx", "")
        if not key or not cx:
            return
        jobs = (("kapak", f"{name} cover art", None),
                ("ikon", f"{name} icon", None),
                ("arkaplan", f"{name} wallpaper", "large"))
        for kind, q, size in jobs:
            if find_asset(gid, kind):
                continue
            try:
                urls = google_image_urls(q, key, cx, size)
            except Exception as e:
                art_log(f"[{name}] {kind} arama hatası: {e}")
                continue
            if not urls:
                art_log(f"[{name}] {kind}: sonuç yok (sorgu: {q})")
                continue
            for url in urls:           # bir bağlantı açılmazsa sıradakini dene
                try:
                    img = download_image(url)
                except Exception as e:
                    art_log(f"[{name}] {kind} indirilemedi: {url} ({e})")
                    continue
                if img is None:
                    continue
                img.thumbnail((2560, 2560))
                remove_assets(gid, kind)
                img.save(os.path.join(ASSETS_DIR, f"{gid}_{kind}.png"), "PNG")
                break
            else:
                art_log(f"[{name}] {kind}: hiçbir sonuç indirilemedi (sorgu: {q})")

    def auto_setup(self, g=None):
        """Tek tuşla: mağaza bilgileri (yayıncı, tarih, tür, açıklama), kapak, arka plan, ikon,
        fragman (arka plan videosu) ve oyunun ana menü müziği otomatik ayarlanır.
        g verilirse yalnızca o oyun, verilmezse tüm oyunlar sırayla işlenir.
        Dolu alanlara ve elle koyulmuş dosyalara dokunmaz; yalnızca eksikleri doldurur."""
        if not self.check_idle():
            return
        try:
            import cv2  # noqa: F401
        except ImportError:
            self.need_video()
            return
        targets = [g] if g else list(self.games)
        if not targets:
            return
        if not self.cfg.get("gcs_key") or not self.cfg.get("gcs_cx"):
            self.show_toast("Kapak ve ikon için önce Ayarlar > Görsel arama anahtarını ayarla.", timeout=6000)
        snap = [dict(x) for x in targets]          # iş parçacığı kendi kopyasıyla çalışır
        self.close_video()
        self.video_photo = None
        self.music.release()

        def work():
            out = {}
            for x in snap:
                gid, name = x["id"], x["name"]
                self.status["text"] = f"Otomatik ayar: {name}"
                info = {}
                try:
                    self._fetch_google_art(gid, name)     # önce Google: kapak, ikon, arka plan
                except Exception:
                    pass
                try:
                    res = ex.fetch_game_info(dict(x), re.sub(r"[™®©]", "", name).strip() or name)
                    cands = ([res["merged"]] if res and res.get("merged") else []) + list((res or {}).get("results", []))
                    if cands:
                        c = cands[0]
                        info = {k: c[k] for k in ("publisher", "developer", "release", "genre", "desc") if c.get(k)}
                        self._download_art(dict(x), c.get("art") or {})
                except Exception:
                    pass
                if not find_asset(gid, "video", VIDEO_EXTS):
                    self.status["text"] = f"Fragman indiriliyor: {name}"
                    try:
                        ydl_download(f"ytsearch1:{name} official trailer", ASSETS_DIR, "video",
                                     out_name=f"{gid}_video", status=self.status)
                    except Exception:
                        pass
                if not find_asset(gid, "muzik", AUDIO_EXTS):
                    self.status["text"] = f"Menü müziği indiriliyor: {name}"
                    try:
                        ydl_download(f"ytsearch1:{name} main menu theme", ASSETS_DIR, "audio",
                                     out_name=f"{gid}_muzik", status=self.status)
                    except Exception:
                        pass
                out[gid] = info
            return out

        def done(out):
            for x in targets:
                for k, v in (out.get(x["id"]) or {}).items():
                    if not x.get(k):              # yalnızca boş alanları doldur
                        x[k] = v
            self.save()
            self.refresh_all()
            self.apply_music_for_game(self.current())
            self.redraw()
            self.show_toast(f"{len(snap)} oyun otomatik ayarlandı. Yanlış çıkan öğeleri elle değiştirebilirsin.",
                            timeout=7000)

        self.run_bg(work, done, f"Otomatik ayar ({len(snap)} oyun)...")

    def auto_setup_all(self):
        if messagebox.askyesno("Tümünü otomatik ayarla",
                               f"{len(self.games)} oyunun eksik bilgi, görsel, fragman ve müziği indirilecek.\n"
                               "Bu uzun sürebilir. Devam edilsin mi?"):
            self.auto_setup(None)

    def remove_game_asset(self, kind):
        g = self.current()
        if not g or not self.check_idle():
            return
        if kind == "video":
            self.close_video()
            self.video_photo = None
        else:
            self.music.release()
        remove_assets(g["id"], kind)
        self.refresh_all()
        self.apply_music_for_game(self.current())

    # ------------------------------------------------------------ GÖRÜNÜM (IZGARA / DETAY)
    GRID_M, GRID_GAP, GRID_NAME_H, GRID_PAD_TOP = 40, 28, 62, 24

    def _on_search(self):
        self.build_list()
        if self.view_mode == "grid":
            self.grid_rebuild()
            if self.grid_items and self.selected not in self.grid_items:
                self.select(self.grid_items[0], sound=None)

    def toggle_view(self):
        self.ui_sound.play("menu")
        self.set_view_mode("detail" if self.view_mode == "grid" else "grid")

    def set_view_mode(self, mode):
        if mode == self.view_mode:
            return
        self.view_mode = mode
        self.cfg["view_mode"] = mode
        try:
            self.save()
        except Exception:
            pass
        self._apply_view_layout()
        self.view_game_id = None
        self.select(self.selected, force=True)

    def _apply_view_layout(self):
        if self.view_mode == "grid":
            self.close_video()
            self.video_photo = None
            self.toggle_btn.place_forget()
            self.sidebar.pack_forget()
            self.grid_wrap.place(x=0, y=0, relwidth=1, relheight=1)
            self.grid_wrap.lift()
            self.grid_cv.focus_set()
            self._grid_configure()
        else:
            self.grid_wrap.place_forget()
            if self.sidebar_open:
                self.sidebar.pack(side="left", fill="y", before=self.right)
            self.toggle_btn.config(text="✕" if self.sidebar_open else "≡")
            self.toggle_btn.place(x=10, y=10)
            self.toggle_btn.lift()

    # ------------------------------------------------------------ KAPAK IZGARASI
    def build_grid(self):
        self.grid_wrap = tk.Frame(self.canvas, bg=T["bg"])
        head = tk.Frame(self.grid_wrap, bg=T["bg"], height=86)
        head.pack(side="top", fill="x")
        head.pack_propagate(False)

        left = tk.Frame(head, bg=T["bg"])
        left.pack(side="left", padx=(30, 10))
        tk.Label(left, text="KÜTÜPHANE", bg=T["bg"], fg=T["title"], font=(FONT, 14, "bold")).pack(anchor="w")
        self.grid_count_var = tk.StringVar(value="")
        tk.Label(left, textvariable=self.grid_count_var, bg=T["bg"], fg=T["muted"],
                 font=(FONT, 10)).pack(anchor="w")

        right = tk.Frame(head, bg=T["bg"])
        right.pack(side="right", padx=(10, 30))
        sb = chip(right, "Ayarlar", None, icon="⚙", font=(FONT, 12), pady=6)
        sb.command = lambda: self.open_settings_menu(anchor=sb)
        sb.pack(side="right", padx=(8, 0))
        chip(right, "Oyun ekle", self.add_game, icon="＋", font=(FONT, 12), pady=6).pack(side="right", padx=(8, 0))
        chip(right, "Ana menü", self.show_home, icon="⌂", font=(FONT, 12), pady=6).pack(side="right", padx=(8, 0))
        chip(right, "Detay", lambda: self.set_view_mode("detail"), icon="☰", font=(FONT, 12),
             pady=6).pack(side="right", padx=(8, 0))

        mid = tk.Frame(head, bg=T["panel"])
        mid.pack(side="left", fill="x", expand=True, padx=10, pady=22)
        tk.Label(mid, text="🔍", bg=T["panel"], fg=T["muted"], font=(FONT, 12)).pack(side="left", padx=(10, 4))
        ent = tk.Entry(mid, textvariable=self.search_var, bg=T["panel"], fg=T["text"],
                       insertbackground=T["text"], relief="flat", font=(FONT, 13), bd=0)
        ent.pack(side="left", fill="x", expand=True, ipady=6, padx=(0, 8))
        ent.bind("<Return>", lambda e: (self.grid_cv.focus_set(), "break")[1])

        tk.Frame(self.grid_wrap, bg=T["divider"], height=1).pack(side="top", fill="x")
        tk.Label(self.grid_wrap, justify="center", bg=T["bg"], fg=T["muted"], font=(FONT, 10),
                 text="◀ ▶ ▲ ▼  Gezin      A / Enter  Oyna      Y / Start  Menü      X  Müzik"
                      "      LB·RB  Şarkı      LT·RT  Ses      Tab  Detay").pack(side="bottom", fill="x", pady=(2, 10))
        self.hero_build(self.grid_wrap)   # üstteki hero şeridi (yüksekliği pencereye göre ayarlanır)
        gc = tk.Canvas(self.grid_wrap, bg=T["bg"], highlightthickness=0)
        gc.pack(side="top", fill="both", expand=True)
        self.grid_cv = gc
        gc.bind("<Configure>", self._grid_configure)
        gc.bind("<Button-1>", self._grid_click)
        gc.bind("<Double-Button-1>", self._grid_double)
        gc.bind("<Button-3>", self._grid_right)
        gc.bind("<Motion>", self._grid_motion)
        gc.bind("<Leave>", self._grid_leave)

    def _grid_configure(self, e=None):
        if self._grid_cfg_job:
            try:
                self.after_cancel(self._grid_cfg_job)
            except Exception:
                pass
        self._grid_cfg_job = self.after(60, self.grid_rebuild)

    def _fit_text(self, font, text, maxw):
        if font.measure(text) <= maxw:
            return text
        while text and font.measure(text + "…") > maxw:
            text = text[:-1]
        return text.rstrip() + "…"

    def grid_rebuild(self):
        self._grid_cfg_job = None
        gc = self.grid_cv
        if self.view_mode != "grid":
            return
        gc.delete("all")
        self.fx_clear()
        self.grid_tiles = {}
        self._grid_bg_item = self._grid_bg_key = None
        w, h = gc.winfo_width(), gc.winfo_height()
        if w < 120 or h < 120:
            self.grid_m = None
            return
        q = self.search_var.get().strip().lower()
        self.grid_items = [i for i, g in enumerate(self.games) if not q or q in g["name"].lower()]
        n = len(self.grid_items)
        self.grid_count_var.set(f"{n} oyun" + (f"  ·  \"{q}\" araması" if q else ""))
        if not n:
            self.grid_m = None
            gc.configure(scrollregion=(0, 0, w, h))
            gc.create_text(w // 2, h // 2, fill=T["muted"], font=(FONT, 16), justify="center",
                           text=("Sonuç yok." if q else
                                 "Henüz oyun eklenmedi.\n\nSağ üstteki \"Oyun ekle\" ya da\n"
                                 "Ayarlar > \"Mağaza oyunlarını tara\" ile başla."))
            self.hero_draw_later()
            return
        if self.cfg.get("liste", True):          # Explorer tarzı liste
            self._list_draw()
            self.grid_update_bg()
            self.hero_draw_later()
            return
        M, GAP = self.GRID_M, self.GRID_GAP
        base = int(GRID_SIZES.get(self.cfg.get("grid_size", "medium"), 260) * 0.8)   # kapaklar biraz küçük
        cols = max(2, (w - 2 * M + GAP) // (base + GAP))
        tw = (w - 2 * M - (cols - 1) * GAP) // cols
        th = int(tw * 1.4)
        rowh = th + self.GRID_NAME_H + GAP
        rows = (n + cols - 1) // cols
        total = max(h, self.GRID_PAD_TOP + rows * rowh + 30)
        x0 = (w - (cols * tw + (cols - 1) * GAP)) // 2
        self.grid_m = {"cols": cols, "tw": tw, "th": th, "rowh": rowh, "x0": x0}
        self._grid_total = total
        gc.configure(scrollregion=(0, 0, w, total))
        self._grid_cur = self._grid_target = max(0, min(self._grid_cur, total - h))
        self.grid_ensure_visible(self.selected, animate=False, center=True)
        self._grid_apply()
        self.grid_update_bg()
        self.hero_draw_later()

    def _grid_make_tile(self, k, i):
        gc, m, g = self.grid_cv, self.grid_m, self.games[i]
        tw, th = m["tw"], m["th"]
        x = m["x0"] + (k % m["cols"]) * (tw + self.GRID_GAP)
        y = self.GRID_PAD_TOP + (k // m["cols"]) * m["rowh"]
        base = get_image(g, "kapak", (tw, th)).convert("RGB")
        pn = ImageTk.PhotoImage(round_corners(ImageEnhance.Brightness(base).enhance(0.62).convert("RGBA"), 18))
        ps = ImageTk.PhotoImage(round_corners(base.convert("RGBA"), 18))
        border = gc.create_polygon(_rr_points(x - 7, y - 7, x + tw + 7, y + th + 7, 20), smooth=True,
                                   fill="", outline=T["accent"], width=4, state="hidden", tags=("gborder",))
        img = gc.create_image(x, y, image=pn, anchor="nw")
        name = gc.create_text(x + 6, y + th + 12, anchor="nw", fill=T["muted"], font=self._gfont,
                              text=self._fit_text(self._gfont_b, g["name"], tw - 12))
        pt = fmt_playtime(g.get("play_seconds", 0))
        bw = self._gfont_s.measure(pt) + 20 if pt else 0
        bst = "normal" if pt else "hidden"
        bbg = gc.create_polygon(_rr_points(x + 10, y + th - 38, x + 10 + max(bw, 24), y + th - 12, 10),
                                smooth=True, fill="#0b0b0b", outline="", state=bst)
        btx = gc.create_text(x + 20, y + th - 25, anchor="w", text=pt, fill="#ffffff",
                             font=self._gfont_s, state=bst)
        src = g.get("source", "")
        sub = gc.create_text(x + 6, y + th + 38, anchor="nw", fill=T["muted"], font=(FONT, 10), text=src)
        extra = []
        src_txt = {"Steam": "STEAM", "Epic Games": "EPIC", "EA app": "EA", "Xbox": "XBOX", "Riot": "RIOT"}.get(src, "")
        bx = x + tw - 10
        if src_txt:
            sw_ = self._gfont_s.measure(src_txt) + 16
            extra.append(gc.create_polygon(_rr_points(bx - sw_, y + 10, bx, y + 34, 8), smooth=True,
                                           fill="#0b0b0b", outline=""))
            extra.append(gc.create_text(bx - sw_ / 2.0, y + 22, text=src_txt, fill="#e5e7eb",
                                        font=self._gfont_s))
            bx -= sw_ + 6
        if _is_new(g):
            nw_ = self._gfont_s.measure("YENİ") + 16
            extra.append(gc.create_polygon(_rr_points(bx - nw_, y + 10, bx, y + 34, 8), smooth=True,
                                           fill=T["accent"], outline=""))
            extra.append(gc.create_text(bx - nw_ / 2.0, y + 22, text="YENİ", fill=T["accent_fg"],
                                        font=self._gfont_s))
        self.grid_tiles[i] = {"k": k, "pn": pn, "ps": ps, "border": border, "img": img,
                              "name": name, "sub": sub, "src": src, "badge": (bbg, btx),
                              "x": x, "y": y, "extra": extra}
        self._fx_snap = True      # ilk çizimde animasyon yok: seçili karo doğrudan 1.06 ölçeğinde
        try:
            self._grid_style(i)
        finally:
            self._fx_snap = False

    def _grid_style(self, i):
        t = self.grid_tiles.get(i)
        if not t:
            return
        gc, sel = self.grid_cv, (i == self.selected)
        fxon = self.fx_on()
        try:
            # animasyon açıksa çerçeveyi kapağın kendisi taşır (eğimle birlikte döner)
            gc.itemconfigure(t["border"], state="normal" if (sel and not fxon) else "hidden",
                             outline=T["accent"])
            if fxon:
                self.fx_select(i, sel)
            else:
                gc.itemconfigure(t["img"], image=t["ps"] if sel else t["pn"])
            gc.itemconfigure(t["name"], fill=T["title"] if sel else T["muted"],
                             font=self._gfont_b if sel else self._gfont)
            gc.itemconfigure(t["sub"], text="▶  OYNA" if sel else t["src"],
                             fill=T["accent"] if sel else T["muted"],
                             font=(FONT, 10, "bold") if sel else (FONT, 10))
        except tk.TclError:
            pass

    def grid_update_bg(self):
        """Seçili oyunun arka planı (yoksa kapağı): bulanık + karartılmış, ekrana sabit.
        Oyun değişince eski görselden yenisine çapraz solar. Video bilerek kullanılmaz:
        ızgarada sürekli kare çözmek kumandada takılma yapar."""
        gc, g = self.grid_cv, self.current()
        self._gs_finish(gc)          # varsa biten kaymayı tamamla
        d = getattr(self, "_slide_dir", 0)
        self._slide_dir = 0
        w, h = gc.winfo_width(), gc.winfo_height()
        kind = None
        if g and self.grid_items and w > 50:
            kind = next((k for k in ("arkaplan", "kapak") if find_asset(g["id"], k)), None)
        if kind is None:
            if self._grid_bg_item is not None:
                gc.delete(self._grid_bg_item)
            self._grid_bg_item = self._grid_bg_key = None
            self._xf_cur.pop("gridbg", None)
            return
        path = find_asset(g["id"], kind)
        try:
            key = (g["id"], kind, path, os.path.getmtime(path), w, h)
        except OSError:
            return
        if key == self._grid_bg_key and self._grid_bg_item is not None:
            return
        small = get_image(g, kind, (max(8, w // 6), max(8, h // 6))).convert("RGB")
        small = ImageEnhance.Brightness(small.filter(ImageFilter.GaussianBlur(float(self.cfg.get("bg_blur", 4))))).enhance(float(self.cfg.get("bg_dim", 0.36)))

        def post(im):
            return im.resize((w, h), Image.BICUBIC)

        prev = self._xf_cur.get("gridbg")
        self._xf_tok["gridbg"] = self._xf_tok.get("gridbg", 0) + 1
        if self._grid_bg_item is None:
            self.refs["gridbg"] = ImageTk.PhotoImage(post(small))
            self._grid_bg_item = gc.create_image(0, self._grid_cur, image=self.refs["gridbg"], anchor="nw")
            gc.tag_lower(self._grid_bg_item)
            self._xf_cur["gridbg"] = small
        elif prev is not None and prev.size == small.size and self._xf_on():
            if d:
                self._grid_slide(gc, self._grid_bg_item, prev, small, post, d)
                self._grid_flash(gc, g, d)
            else:
                self.xfade_start("gridbg", gc, self._grid_bg_item, prev, small, post=post)
        else:
            self.refs["gridbg"] = ImageTk.PhotoImage(post(small))
            gc.itemconfigure(self._grid_bg_item, image=self.refs["gridbg"])
            self._xf_cur["gridbg"] = small
        self._grid_bg_key = key

    def _cover_expand(self, g, d=0):
        """Detay görünümünde seçilen oyunun kapağı yön tarafından ekrana girer, ortada durur,
        sonra arka plandaki kendi kapak alanına kayarak küçülüp yerine oturur.
        Kapak her zaman en önde, düğmelerin üstünde kalır."""
        c = self.canvas
        if not self._xf_on() or not hasattr(self, "_detail_cover_rect"):
            return
        w, h = c.winfo_width(), c.winfo_height()
        if w < 200 or h < 200:
            return
        cx0, cy0, cw, ch = self._detail_cover_rect
        old = getattr(self, "_cx_item", None)
        if old is not None:
            try:
                c.delete(old)
            except tk.TclError:
                pass
        oh = int(h * 0.55)
        ow = int(oh * cw / ch)                    # kapak alanıyla aynı oran: küçülünce birebir oturur
        mx = (w - ow) // 2                        # ortadaki büyük kapağın konumu
        my = max(0, (h - oh) // 2 - 40)
        src = get_image(g, "kapak", (ow, oh)).convert("RGB")
        self._cx_restore_windows()                # önceki animasyondan kalan gizlemeyi geri al
        self._cx_active = True                    # animasyon sürerken ekran yeniden çizilmesin
        item = c.create_image(mx, my, anchor="nw")
        self._cx_item = item
        # Düğmeler (OYNA, klasörü aç, bilgileri düzenle...) gömülü pencere olduğu için
        # canvas öğelerinin üstünde çizilir. Animasyon boyunca gizlenir ki kapak en önde görünsün.
        self._cx_hidden = []
        for it in c.find_all():
            if c.type(it) == "window":
                try:
                    c.itemconfigure(it, state="hidden")
                    self._cx_hidden.append(it)
                except tk.TclError:
                    pass
        try:
            c.tag_raise(item)
        except tk.TclError:
            pass
        tok = self._xf_tok.get("cexp", 0) + 1
        self._xf_tok["cexp"] = tok
        t0 = time.perf_counter()
        t_in, t_hold, t_back = 0.32, 0.14, 0.46
        start_x = (d * w) if d else mx            # yön yoksa yerinde belirir

        # Arka plan öğeleri (bilgiler, arka plan resmi, video) küçük bir kayma ile yerine oturur
        st = {"others": None, "ax": 0, "ay": 0}
        ox, oy = 0, -int(h * 0.3)                # sayfa yukarıdan kayarak gelir

        def mv(dx, dy):
            st["ax"] += dx
            st["ay"] += dy
            for i in st["others"] or []:
                try:
                    c.move(i, dx, dy)
                except tk.TclError:
                    pass

        def offset_to(tx, ty):
            if st["others"] is None:
                st["others"] = [i for i in c.find_all() if i != item]
            mv(int(round(tx)) - st["ax"], int(round(ty)) - st["ay"])

        def show(x, y, sw, sh):
            photo = ImageTk.PhotoImage(src.resize((max(2, int(sw)), max(2, int(sh))), Image.BILINEAR))
            self.refs["cexp"] = photo
            c.itemconfigure(item, image=photo)
            c.coords(item, round(x), round(y))

        def step():
            if self._xf_tok.get("cexp") != tok:
                return
            t = time.perf_counter() - t0
            t_end = t_in + t_hold + t_back
            try:
                # arka plan sayfası (bilgiler, arka plan resmi, video) yukarıdan iner; kapak yerine
                # oturduğu anda sayfa da tam yerinde olur
                p = min(1.0, t / t_end)
                offset_to(ox, oy * (1 - (1 - (1 - p) ** 3)))
                if t < t_in:                      # 1) yönden ekrana girer, ortada büyük durur
                    k = t / t_in
                    e = 1 - (1 - k) ** 3
                    show(start_x + (mx - start_x) * e, my, ow, oh)
                elif t < t_in + t_hold:           # 2) kısa süre ortada
                    show(mx, my, ow, oh)
                elif t < t_end:                   # 3) kapak kendi yerine kayar
                    k = (t - t_in - t_hold) / t_back
                    e = k * k * (3 - 2 * k)
                    show(mx + (cx0 - mx) * e, my + (cy0 - my) * e,
                         ow + (cw - ow) * e, oh + (ch - oh) * e)
                else:
                    offset_to(0, 0)
                    c.delete(item)
                    if self._cx_item == item:
                        self._cx_item = None
                    self._cx_restore_windows()
                    self._cx_active = False
                    return
            except tk.TclError:
                self._cx_active = False
                return
            self.after(16, step)

        step()

    def _cx_restore_windows(self):
        c = self.canvas
        for it in getattr(self, "_cx_hidden", None) or []:
            try:
                c.itemconfigure(it, state="normal")
            except tk.TclError:
                pass
        self._cx_hidden = []

    def _grid_flash(self, gc, g, d):
        """Seçilen oyunun kapağı yön tarafından ekrana girer, ortada durur, karşı tarafa çıkar.
        Arka plan kaymasından ayrı olarak geçişi net gösterir."""
        w, h = gc.winfo_width(), gc.winfo_height()
        oh = int(h * 0.55)
        ow = int(oh * 2 / 3)
        if ow < 40 or w < 200:
            return
        gf = getattr(self, "_gf", None)
        if gf is None:
            gf = self._gf = {}
        key = str(gc)
        old = gf.get(key)
        if old is not None:
            try:
                gc.delete(old)
            except tk.TclError:
                pass
        img = round_corners(get_image(g, "kapak", (ow, oh)).convert("RGBA"), 18)
        self.refs["gs_flash"] = ImageTk.PhotoImage(img)
        y = max(0, (h - oh) // 2 - 40)
        cx = (w - ow) // 2
        item = gc.create_image(d * w, y, image=self.refs["gs_flash"], anchor="nw")
        try:
            gc.tag_raise(item)                       # kapak en üstte geçsin
            for it in gc.find_all():                 # ama düğmeler (gömülü pencereler) kapağın üstünde kalsın
                if gc.type(it) == "window":
                    gc.tag_raise(it)
        except tk.TclError:
            pass
        gf[key] = item
        tok = self._xf_tok.get("gflash", 0) + 1
        self._xf_tok["gflash"] = tok
        t0 = time.perf_counter()
        t_in, t_hold, t_out = 0.30, 0.16, 0.30

        def step():
            if self._xf_tok.get("gflash") != tok:
                return
            t = time.perf_counter() - t0
            try:
                if t < t_in:
                    k = t / t_in
                    e = 1 - (1 - k) ** 3
                    x = d * w + (cx - d * w) * e
                elif t < t_in + t_hold:
                    x = cx
                else:
                    k = min(1.0, (t - t_in - t_hold) / t_out)
                    e = k * k * k
                    x = cx + (-d * w - cx) * e
                gc.coords(item, round(x), y)
            except tk.TclError:
                return
            if t < t_in + t_hold + t_out:
                self.after(16, step)
            else:
                try:
                    gc.delete(item)
                except tk.TclError:
                    pass
                if gf.get(key) == item:
                    gf[key] = None

        step()

    def _gs_finish(self, gc):
        """Devam eden kaymayı son karede bitirir (yeni kayma başlamadan ya da ızgara yenilenmeden)."""
        p = getattr(self, "_gs_pending", None)
        if not p:
            return
        self._gs_pending = None
        old, nb, small = p
        try:
            gc.delete(old)
            gc.coords(nb, 0, self._gs_y)
        except tk.TclError:
            pass
        self._grid_bg_item = nb
        self._xf_cur["gridbg"] = small
        self.refs["gridbg"] = self.refs.get("gs_new")
        self._xf_tok["gridslide"] = self._xf_tok.get("gridslide", 0) + 1

    def _grid_slide(self, gc, old_item, prev, new_small, post, d):
        """Arka plan görseli seçim yönünde kayar: ileri geçişte yeni görsel sağdan gelir,
        geri geçişte soldan. Eski görsel ters yöne doğru çıkar."""
        w = gc.winfo_width()
        try:
            y0 = int(gc.coords(old_item)[1])
        except (tk.TclError, IndexError):
            y0 = 0
        self._gs_y = y0
        self.refs["gs_new"] = ImageTk.PhotoImage(post(new_small))
        nb = gc.create_image(d * w, y0, image=self.refs["gs_new"], anchor="nw")
        gc.tag_raise(nb, old_item)                  # yeni görsel eskinin üstüne gelir, kartların altında kalır
        self._gs_pending = (old_item, nb, new_small)
        tok = self._xf_tok.get("gridslide", 0) + 1
        self._xf_tok["gridslide"] = tok
        t0 = time.perf_counter()
        dur = 0.36

        def step():
            if self._xf_tok.get("gridslide") != tok:
                return
            k = min(1.0, (time.perf_counter() - t0) / dur)
            e = 1 - (1 - k) ** 3
            try:
                gc.coords(nb, round((1 - e) * d * w), y0)
                gc.coords(old_item, round(-e * d * w), y0)
            except tk.TclError:
                return
            if k < 1.0:
                self.after(16, step)
            else:
                self._gs_finish(gc)

        step()

    # ------------------------------------------------------------ LİSTE (EXPLORER) GÖRÜNÜMÜ
    def _list_draw(self):
        """Dosya gezgini gibi: solda oyun satırları (Ad, Tarih, Tür, Boyut), sağda ayrıntı paneli
        (kapak + bilgiler). Arka plan olarak seçili oyunun duvar kağıdı kullanılır."""
        gc = self.grid_cv
        gc.delete("list", "pane", "hdr")
        w, h = gc.winfo_width(), gc.winfo_height()
        if w < 300 or h < 150 or not self.grid_items:
            return
        y0 = self.GRID_PAD_TOP + 34          # ilk satırın y'si
        rowh = 52
        LW = int(w * 0.60)                   # sol liste genişliği
        n = len(self.grid_items)
        total = max(h, y0 + n * rowh + 30)
        self.grid_m = {"cols": 1, "tw": LW, "th": 40, "rowh": rowh, "x0": 0, "y0": y0, "list": True}
        self._grid_total = total
        gc.configure(scrollregion=(0, 0, w, total))
        self._grid_cur = self._grid_target = max(0, min(self._grid_cur, total - h))
        oy = self._grid_cur
        self._pane_y = oy

        pad = 36
        hy = oy + self.GRID_PAD_TOP
        hdr_font = (FONT, 9, "bold")
        gc.create_text(pad, hy, text="Ad", anchor="nw", fill=T["muted"], font=hdr_font, tags=("hdr",))
        gc.create_text(LW * 0.50, hy, text="Değiştirme tarihi", anchor="nw", fill=T["muted"],
                       font=hdr_font, tags=("hdr",))
        gc.create_text(LW * 0.72, hy, text="Tür", anchor="nw", fill=T["muted"], font=hdr_font, tags=("hdr",))
        gc.create_text(LW * 0.87, hy, text="Boyut", anchor="nw", fill=T["muted"], font=hdr_font, tags=("hdr",))
        gc.create_line(pad - 10, hy + 24, LW - 10, hy + 24, fill="#3a3f5c", tags=("hdr",))

        sel_row = self.selected
        for k, i in enumerate(self.grid_items):
            g = self.games[i]
            y = y0 + k * rowh
            sel = (i == sel_row)
            if sel:
                gc.create_polygon(_rr_points(pad - 12, y + 3, LW - 10, y + rowh - 3, 10), smooth=True,
                                  fill=blend(T["panel"], T["accent"], 0.35), outline="", tags=("list",))
            thumb = ImageTk.PhotoImage(get_image(g, "kapak", (34, 44)).convert("RGB"))
            self.refs["lst_%d" % i] = thumb
            gc.create_image(pad, y + 4, image=thumb, anchor="nw", tags=("list",))
            name_w = int(LW * 0.48) - 60
            gc.create_text(pad + 46, y + rowh / 2.0, anchor="w", tags=("list",),
                           text=self._fit_text(self._gfont_b if sel else self._gfont, g["name"], name_w),
                           fill=T["title"] if sel else T["text"],
                           font=(FONT, 12, "bold") if sel else (FONT, 12))
            last = g.get("last_played") or ""
            if last:
                try:
                    last = datetime.fromisoformat(last).strftime("%d.%m.%Y %H:%M")
                except Exception:
                    pass
            gc.create_text(LW * 0.50, y + rowh / 2.0, anchor="w", text=last or "—", fill=T["muted"],
                           font=(FONT, 10), tags=("list",))
            gc.create_text(LW * 0.72, y + rowh / 2.0, anchor="w", text=g.get("genre", "") or "—",
                           fill=T["muted"], font=(FONT, 10), tags=("list",), width=int(LW * 0.13))
            sz = self.size_cache.get(g["id"])
            gc.create_text(LW * 0.87, y + rowh / 2.0, anchor="w",
                           text=(self.fmt_size(sz) if sz else "—"), fill=T["muted"], font=(FONT, 10),
                           tags=("list",))

        # ayrıntı paneli (sağ)
        g = self.current()
        px = LW + 24
        pw = w - px - 24
        py = oy + self.GRID_PAD_TOP
        ph = h - self.GRID_PAD_TOP * 2
        if g and pw >= 260 and ph >= 300:
            panel = vfx.glass_image(self._backdrop(int(w), int(h)), (px, py, px + pw, py + ph), radius=16,
                                    blur=20, tint=(8, 10, 24), tint_a=int(self.cfg.get("glass_tint", 150)),
                                    border_a=0)
            self.refs["lst_panel"] = ImageTk.PhotoImage(panel)
            gc.create_image(px, py, image=self.refs["lst_panel"], anchor="nw", tags=("pane",))

            cw = min(pw - 60, int(ph * 0.42 / 1.4 * 1.4))
            ch = int(cw * 1.4)
            if ch > ph * 0.5:
                ch = int(ph * 0.5)
                cw = int(ch / 1.4)
            cover = ImageTk.PhotoImage(get_image(g, "kapak", (cw, ch)))
            self.refs["lst_cover"] = cover
            cx = px + (pw - cw) // 2
            gc.create_image(cx, py + 24, image=cover, anchor="nw", tags=("pane",))

            ty = py + 24 + ch + 18
            gc.create_text(px + 22, ty, text=g["name"], anchor="nw", fill=T["title"], width=pw - 44,
                           font=(FONT, 15, "bold"), tags=("pane",))
            ty += 44
            gid = g["id"]
            self.request_size(g)
            sz = self.size_cache.get(gid)
            count = int(g.get("launch_count", 0) or 0)
            last = g.get("last_played") or ""
            if last:
                try:
                    last = datetime.fromisoformat(last).strftime("%d.%m.%Y %H:%M")
                except Exception:
                    pass
            rows = [
                ("Tür", g.get("genre", "")),
                ("Yayıncı", g.get("publisher", "")),
                ("Geliştirici", g.get("developer", "")),
                ("Boyut", self.fmt_size(sz) if sz else ("Hesaplanıyor..." if gid not in self.size_cache else "—")),
                ("Son oynanma", last or "Henüz oynanmadı"),
                ("Başlatma", f"{count} kez" if count else "—"),
                ("Toplam oynanma", fmt_playtime(g.get("play_seconds", 0)) or "—"),
            ]
            for label, val in rows:
                gc.create_text(px + 22, ty, text=label, anchor="nw", fill=T["muted"], font=(FONT, 9, "bold"),
                               tags=("pane",))
                gc.create_text(px + 150, ty - 1, text=(val or "—"), anchor="nw", fill=T["text"],
                               font=(FONT, 10), width=pw - 170, tags=("pane",))
                ty += 28
            if ty < py + ph - 30:
                gc.create_text(px + 22, ty + 6, text="KONUM", anchor="nw", fill=T["muted"],
                               font=(FONT, 9, "bold"), tags=("pane",))
                gc.create_text(px + 150, ty + 5, text=(self.install_dir(g) or "—"), anchor="nw",
                               fill=T["text"], font=(FONT, 9), width=pw - 170, tags=("pane",))

    def _list_follow(self):
        """Kaydırmada başlık ve ayrıntı paneli ekranda sabit kalsın."""
        gc = self.grid_cv
        dy = self._grid_cur - getattr(self, "_pane_y", 0)
        if dy:
            try:
                gc.move("pane", 0, dy)
                gc.move("hdr", 0, dy)
            except tk.TclError:
                return
            self._pane_y = self._grid_cur

    def toggle_list_style(self):
        self.cfg["liste"] = not self.cfg.get("liste", True)
        self.save()
        self._grid_cur = self._grid_target = 0.0
        self.grid_rebuild()

    def grid_populate(self):
        m = self.grid_m
        if not m or not self.grid_items or m.get("list"):
            return
        gc = self.grid_cv
        H = max(1, gc.winfo_height())
        cols, rowh, P = m["cols"], m["rowh"], self.GRID_PAD_TOP
        top = self._grid_cur
        r0 = max(0, int((top - P) // rowh) - 1)
        r1 = int((top + H - P) // rowh) + 1
        n = len(self.grid_items)
        for k in range(r0 * cols, min(n, (r1 + 1) * cols)):
            i = self.grid_items[k]
            if i not in self.grid_tiles:
                self._grid_make_tile(k, i)
        lo, hi = max(0, (r0 - 2) * cols), (r1 + 3) * cols
        for i, t in list(self.grid_tiles.items()):
            if not lo <= t["k"] < hi:
                gc.delete(t["border"], t["img"], t["name"], t["sub"], *t["badge"], *t.get("extra", ()))
                self._tfx.pop(i, None)
                del self.grid_tiles[i]

    def _grid_apply(self):
        try:
            self.grid_cv.yview_moveto(self._grid_cur / max(1, self._grid_total))
            if self._grid_bg_item is not None:  # arka plan ekrana sabit kalsın
                self.grid_cv.coords(self._grid_bg_item, 0, self._grid_cur)
        except tk.TclError:
            return
        if self.grid_m and self.grid_m.get("list"):
            self._list_follow()
        self.grid_populate()

    def grid_scroll_to(self, y, animate=True):
        H = max(1, self.grid_cv.winfo_height())
        y = max(0, min(max(0, self._grid_total - H), y))
        self._grid_target = y
        if not animate:
            self._grid_cur = y
            self._grid_apply()
        elif self._grid_job is None:
            self._grid_anim()

    def _grid_anim(self):
        self._grid_job = None
        d = self._grid_target - self._grid_cur
        self._grid_cur = self._grid_target if abs(d) < 1 else self._grid_cur + d * 0.30
        self._grid_apply()
        if self._grid_cur != self._grid_target:
            self._grid_job = self.after(15, self._grid_anim)

    def grid_ensure_visible(self, i, animate=True, center=False):
        m = self.grid_m
        if not m or i not in self.grid_items:
            return
        k = self.grid_items.index(i)
        ry = m.get("y0", self.GRID_PAD_TOP) + (k // m["cols"]) * m["rowh"]
        bottom = ry + m["th"] + self.GRID_NAME_H
        H = max(1, self.grid_cv.winfo_height())
        tgt = self._grid_target
        if ry - 24 < tgt or bottom + 30 > tgt + H:
            if center:
                new = ry - max(24, (H - m["th"] - self.GRID_NAME_H) // 3)
            elif ry - 24 < tgt:
                new = ry - 60
            else:
                new = bottom + 30 - H
            self.grid_scroll_to(new, animate=animate)

    def grid_on_select(self):
        if not self.grid_m:
            return
        old = getattr(self, "_grid_sel_idx", None)
        self._grid_sel_idx = self.selected
        if self.grid_m.get("list"):           # liste: satır vurgusu ve ayrıntı paneli yeniden çizilir
            self._list_draw()
            self.grid_update_bg()
            self.hero_draw_later()
            self.grid_ensure_visible(self.selected)
            return
        # yön: ileri oyuna geçişte arka plan sağdan gelir, geri geçişte soldan
        self._slide_dir = 0 if old is None or old == self.selected else (1 if self.selected > old else -1)
        for i in {old, self.selected}:
            self._grid_style(i)
        self.grid_update_bg()
        self.hero_draw_later()
        self.grid_ensure_visible(self.selected)

    def grid_move(self, dx, dy):
        items, m = self.grid_items, self.grid_m
        if not items or not m:
            return
        try:
            k = items.index(self.selected)
        except ValueError:
            self.select(items[0], sound=None)
            return
        cols, n = m["cols"], len(items)
        nk = k
        if dx:
            nk = max(0, min(n - 1, k + dx))
        if dy:
            nk = k + dy * cols
            if nk >= n:
                nk = n - 1 if (n - 1) // cols > k // cols else k
            elif nk < 0:
                nk = k
        if nk != k:
            self.ui_sound.play("move")
            self.select(items[nk], sound=None)

    def grid_wheel(self, e):
        if not self.grid_m:
            return
        d = -(e.delta if sys.platform == "darwin" else e.delta / 120.0)
        self.grid_scroll_to(self._grid_target + d * self.grid_m["rowh"] * 0.6)

    def _grid_hit(self, e):
        m = self.grid_m
        if not m:
            return None
        gc = self.grid_cv
        x, y = gc.canvasx(e.x) - m["x0"], gc.canvasy(e.y) - m.get("y0", self.GRID_PAD_TOP)
        step = m["tw"] + self.GRID_GAP
        col, row = int(x // step), int(y // m["rowh"])
        if x < 0 or y < 0 or col >= m["cols"]:
            return None
        if x - col * step > m["tw"] or y - row * m["rowh"] > m["th"] + self.GRID_NAME_H - 6:
            return None
        k = row * m["cols"] + col
        return self.grid_items[k] if k < len(self.grid_items) else None

    def _grid_click(self, e):
        self.grid_cv.focus_set()
        i = self._grid_hit(e)
        if i is not None:
            self.select(i)

    def _grid_double(self, e):
        i = self._grid_hit(e)
        if i is not None:
            self.select(i, sound=None)
            self.start_game()

    def _grid_right(self, e):
        i = self._grid_hit(e)
        if i is not None:
            self.select(i, sound=None)
            self._open_manage(e)

    # ------------------------------------------------------------ AÇILIŞ ANİMASYONU
    def _intro_key(self, e):
        if self._idle_touch():   # boşta ekranını kapatan tuş başka iş yapmasın
            return "break"
        if self.splash is not None:
            self._intro_skip_now()
            return "break"

    def _intro_skip_now(self):
        if self.splash is not None and not self._intro_skip:
            self._intro_skip = True
            self._intro_snd_done = True
            self.ui_sound.stop_intro()

    def start_intro(self):
        if "--minimized" in sys.argv or not self.cfg.get("intro", True):
            return
        sp = tk.Canvas(self, bg="#000000", highlightthickness=0, bd=0)
        sp.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(sp)  # Canvas.lift() öğe yükseltir; pencereyi yükseltmek için Misc.lift
        sp.bind("<Button-1>", lambda e: self._intro_skip_now())
        self.splash = sp
        self._intro_music_block = True
        self._intro_skip = False
        self._intro_snd_done = not self.cfg.get("intro_sound", True)
        blk = "#000000"
        self._intro_title_font = tkfont.Font(family=FONT, size=36, weight="bold")
        word, gap = "MULTI LIBRARY", 12
        self._intro_xoff, x = [], 0
        for ch in word:
            wch = self._intro_title_font.measure(ch)
            self._intro_xoff.append(x + wch / 2)
            x += wch + gap
        half = (x - gap) / 2
        self._intro_xoff = [v - half for v in self._intro_xoff]
        it = {"ring": sp.create_arc(0, 0, 1, 1, start=90, extent=0, style="arc", outline=blk, width=5),
              "tri": sp.create_polygon(0, 0, 0, 0, 0, 0, fill=blk, outline=""),
              "letters": [sp.create_text(0, 0, text=ch, font=self._intro_title_font, fill=blk)
                          for ch in word],
              "line": sp.create_line(0, 0, 0, 0, fill=blk, width=2),
              "sub": sp.create_text(0, 0, text=f"KÜTÜPHANE   ·   {len(self.games)} OYUN", fill=blk,
                                    font=(FONT, 12)),
              "edge": [sp.create_rectangle(0, 0, 1, 1, fill=blk, outline="", state="hidden")
                       for _ in range(3)]}
        self._intro = it
        self._intro_t0 = time.perf_counter()
        self.after(10, self._intro_frame)

    def _intro_finish(self):
        sp, self.splash = self.splash, None
        try:
            sp.destroy()
        except tk.TclError:
            pass
        if self._intro_music_block:
            self._intro_music_block = False
            self.apply_music_for_game(self.current())
        if self.view_mode == "grid":
            self.grid_cv.focus_set()

    def _intro_frame(self):
        sp = self.splash
        if sp is None:
            return
        try:
            now = time.perf_counter()
            if self._intro_skip and now - self._intro_t0 < 1.4:
                self._intro_t0 = now - 1.4
            t = now - self._intro_t0
            if not self._intro_snd_done:
                if t >= 0.8 or self.ui_sound.play_intro():  # geç kalırsa sesi çalma
                    self._intro_snd_done = True
            W, H = max(2, sp.winfo_width()), max(2, sp.winfo_height())
            acc, blk = T["accent"], "#000000"
            cx, cy, R = W / 2, H * 0.40, 96
            clamp = lambda v: max(0.0, min(1.0, v))
            eo = lambda v: 1 - (1 - clamp(v)) ** 3
            fo = clamp((t - 1.35) / 0.25)              # çıkışta her şey siyaha solar
            col = lambda c, a: blend(blk, c, a * (1 - fo))
            it = self._intro
            sp.coords(it["ring"], cx - R, cy - R, cx + R, cy + R)
            sp.itemconfigure(it["ring"], extent=-360 * eo(t / 0.9), outline=col(acc, clamp(t / 0.3)))
            sp.coords(it["tri"], cx - 14, cy - 24, cx - 14, cy + 24, cx + 26, cy)
            sp.itemconfigure(it["tri"], fill=col(acc, eo((t - 0.25) / 0.35)))
            ty = cy + R + 70
            for n, lid in enumerate(it["letters"]):
                p = eo((t - (0.30 + n * 0.045)) / 0.28)
                sp.coords(lid, cx + self._intro_xoff[n], ty + (1 - p) * 14)
                sp.itemconfigure(lid, fill=col("#ffffff", p))
            hw = 150 * eo((t - 0.70) / 0.45)
            sp.coords(it["line"], cx - hw, ty + 40, cx + hw, ty + 40)
            sp.itemconfigure(it["line"], fill=col(acc, 1.0))
            sp.coords(it["sub"], cx, ty + 68)
            sp.itemconfigure(it["sub"], fill=col(T["muted"], clamp((t - 0.80) / 0.4)))
            if t >= 1.4 and self._intro_music_block:
                self._intro_music_block = False
                self.apply_music_for_game(self.current())
            if t >= 1.5:                                  # perde yukarı süpürülür
                p = clamp((t - 1.5) / 0.5)
                e = p * p * (3 - 2 * p)
                for n, rid in enumerate(it["edge"]):  # perdenin ön kenarında parlayan çizgi
                    a, b = ((3, 0), (9, 3), (20, 9))[n]
                    sp.coords(rid, 0, H - a, W, H - b)
                    sp.itemconfigure(rid, state="normal", fill=blend(blk, acc, (1.0, 0.45, 0.18)[n]))
                sp.place_configure(y=-int(H * e))
            if t >= 2.0:
                self._intro_finish()
                return
        except tk.TclError:
            self.splash = None
            return
        self.after(15, self._intro_frame)

    # ------------------------------------------------------------ AYARLAR / TARAMA
    def open_settings_menu(self, anchor=None):
        self.ui_sound.play("menu")
        m = styled_menu(self)
        self.autostart_var = tk.BooleanVar(value=ex.is_autostart())
        self.ui_var = tk.BooleanVar(value=self.ui_sound.enabled)
        m.add_command(label="Mağaza oyunlarını tara...", command=self.open_store_scan)
        m.add_command(label="Klasörden oyun tara...", command=self.open_folder_scan)
        m.add_command(label="Yeni oyunları şimdi ara (hızlı)", command=lambda: self.auto_scan(manual=True))
        m.add_command(label="Videosu olmayan oyunlara fragman indir", command=lambda: self.auto_trailer())
        m.add_command(label="Tüm oyunları otomatik ayarla", command=self.auto_setup_all)
        m.add_command(label="Görsel arama anahtarını ayarla...", command=self.set_image_keys)
        m.add_command(label="Eksik görselleri mağazadan indir", command=self.refresh_store_art)
        m.add_command(label="Son tarama raporunu aç", command=self.open_scan_report)
        m.add_separator()
        m.add_command(label="Yedekten geri yükle...", command=self.open_backup_window)
        m.add_command(label="Şimdi yedek al", command=self.backup_now)
        m.add_command(label="Telefon kumandası bağlantısı / QR...", command=self.show_remote_info)
        m.add_separator()
        self._menu_vars = []
        self.grid_size_var = tk.StringVar(value=self.cfg.get("grid_size", "medium"))
        self.font_var = tk.DoubleVar(value=float(self.cfg.get("font_scale", 1.0)))
        self.bgdim_var = tk.DoubleVar(value=float(self.cfg.get("bg_dim", 0.36)))
        self.bgblur_var = tk.IntVar(value=int(self.cfg.get("bg_blur", 4)))
        look = styled_menu(m)
        theme_m = styled_menu(look)
        for name, col in THEME_PRESETS.items():
            theme_m.add_command(label=name, command=lambda c=col: self.apply_accent_preset(c))
        look.add_cascade(label="Vurgu rengi (tema)", menu=theme_m)
        size_m = styled_menu(look)
        for key, lab in (("small", "Küçük kapaklar"), ("medium", "Orta kapaklar"), ("large", "Büyük kapaklar")):
            size_m.add_radiobutton(label=lab, variable=self.grid_size_var, value=key, command=self.apply_grid_size)
        look.add_cascade(label="Izgara boyutu", menu=size_m)
        font_m = styled_menu(look)
        for lab, sc in FONT_SCALES.items():
            font_m.add_radiobutton(label=lab, variable=self.font_var, value=sc, command=self.apply_font_scale)
        look.add_cascade(label="Yazı boyutu (TV için büyük)", menu=font_m)
        bg_m = styled_menu(look)
        for lab, dim in (("Parlak", 0.6), ("Normal", 0.36), ("Koyu", 0.2)):
            bg_m.add_radiobutton(label="Arka plan " + lab.lower(), variable=self.bgdim_var, value=dim,
                                 command=self.apply_bg)
        bg_m.add_separator()
        for lab, bl in (("Bulanıklık yok", 0), ("Hafif bulanıklık", 4), ("Orta bulanıklık", 8),
                        ("Güçlü bulanıklık", 12)):
            bg_m.add_radiobutton(label=lab, variable=self.bgblur_var, value=bl, command=self.apply_bg)
        look.add_cascade(label="Arka plan (bulanıklık / karartma)", menu=bg_m)
        glass_m = styled_menu(look)
        self.glass_var = tk.IntVar(value=int(self.cfg.get("glass_tint", 150)))
        for lab, tv in (("Çok saydam", 90), ("Saydam (önerilen)", 120), ("Normal", 150), ("Koyu", 200)):
            glass_m.add_radiobutton(label=lab, variable=self.glass_var, value=tv, command=self.apply_glass)
        look.add_cascade(label="Cam paneller (saydamlık)", menu=glass_m)
        # tek ayar: arka plan + cam panelleri birlikte karartır/aydınlatır
        self.bright_var = tk.StringVar(value=self._brightness_key())
        bright_m = styled_menu(look)
        for key, lab in (("parlak", "Parlak"), ("normal", "Normal"), ("koyu", "Koyu"), ("cok_koyu", "Çok koyu")):
            bright_m.add_radiobutton(label=lab, variable=self.bright_var, value=key, command=self.apply_brightness)
        look.add_cascade(label="Genel parlaklık", menu=bright_m)
        look.add_command(label=("Kapak ızgarasına geç" if self.cfg.get("liste", True) else "Liste (Explorer) görünümüne geç"),
                         command=self.toggle_list_style)
        mon_m = styled_menu(look)
        self.monitor_var = tk.StringVar(value=str(self.cfg.get("monitor", "secondary")))
        mon_opts = [("Dikey monitör (otomatik)", "portrait"), ("İkinci monitör", "secondary"),
                    ("Birincil monitör", "primary")]
        mon_opts += [(f"Monitör {k + 1}", str(k)) for k in range(len(list_monitors()))]
        for lab, val in mon_opts:
            mon_m.add_radiobutton(label=lab, variable=self.monitor_var, value=val, command=self.apply_monitor)
        look.add_cascade(label="Açılış monitörü", menu=mon_m)
        m.add_cascade(label="Görünüm ve okunabilirlik", menu=look)
        m.add_command(label="Güncellemeleri kontrol et", command=lambda: self.check_update(manual=True))
        m.add_separator()

        def toggle(label, key, default=True, after=None):
            var = tk.BooleanVar(value=bool(self.cfg.get(key, default)))
            self._menu_vars.append(var)

            def cb():
                self.cfg[key] = var.get()
                self.save()
                if after:
                    after()
            m.add_checkbutton(label=label, variable=var, command=cb)

        view_var = tk.BooleanVar(value=(self.view_mode == "grid"))
        self._menu_vars.append(view_var)
        m.add_checkbutton(label="Kapak ızgarası görünümü (Tab)", variable=view_var,
                          command=lambda: self.set_view_mode("grid" if view_var.get() else "detail"))
        fs_var = tk.BooleanVar(value=self.fullscreen)
        self._menu_vars.append(fs_var)
        m.add_checkbutton(label="Tam ekran (F11)", variable=fs_var,
                          command=lambda: self.set_fullscreen(fs_var.get()))
        toggle("Oyun açılınca tepsiye in" if ex.Tray.available()
               else "Oyun açılınca küçült (tepsi için: pip install pystray)", "tray_on_launch")
        toggle("Açılışta yeni oyunları tara", "auto_scan")
        toggle("Kapaktan vurgu rengi", "dynamic_accent",
               after=lambda: self.update_accent(self.current(), True))
        toggle("Kumanda desteği", "gamepad")
        toggle("Kapak animasyonları (eğim, büyüme, parıltı, çapraz solma)", "fx_motion", after=self.fx_reload)
        toggle("Başlatma geçişi (kapak ekranı kaplar)", "fx_launch")
        toggle("Açılış animasyonu", "intro")
        toggle("Açılış sesi", "intro_sound")
        toggle("Telefondan kumanda (aynı Wi-Fi)", "remote_enabled", False, after=self._remote_sync)
        idle_menu = styled_menu(m)
        self.idle_var = tk.IntVar(value=int(self.cfg.get("idle_minutes", 3) or 0))
        for mins, lab in ((0, "Kapalı"), (1, "1 dakika"), (2, "2 dakika"), (3, "3 dakika"),
                          (5, "5 dakika"), (10, "10 dakika"), (15, "15 dakika")):
            idle_menu.add_radiobutton(label=lab, variable=self.idle_var, value=mins,
                                      command=self._idle_set)
        idle_menu.add_separator()
        idle_menu.add_command(label="Şimdi göster (önizleme)", command=lambda: self._idle_start(True))
        m.add_cascade(label="Boşta kalma ekranı", menu=idle_menu)
        m.add_separator()
        m.add_checkbutton(label="Windows ile başlat", variable=self.autostart_var,
                          command=self.toggle_autostart)
        m.add_checkbutton(label="Menü sesleri", variable=self.ui_var,
                          command=self.toggle_ui_sounds)
        a = anchor or self.settings_btn
        x = a.winfo_rootx()
        if anchor is None:
            y = max(0, a.winfo_rooty() - (m.index("end") + 1) * 26)
        else:
            y = a.winfo_rooty() + a.winfo_height() + 2
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def toggle_ui_sounds(self):
        self.ui_sound.enabled = self.ui_var.get()
        self.cfg["ui_sounds"] = self.ui_sound.enabled
        self.save()
        if self.ui_sound.enabled:
            self.ui_sound.play("select")

    def toggle_autostart(self):
        try:
            ex.set_autostart(self.autostart_var.get())
        except Exception as e:
            messagebox.showerror("Hata", f"Ayar değiştirilemedi:\n{e}")
            self.autostart_var.set(ex.is_autostart())

    # ------------------------------------------------------------ ANA MENÜ + BİLDİRİMLER
    _home_on = False
    _home_sel = 0
    _home_panel = "menu"
    _home_hits = []
    _home_bgkey = None
    _home_anim = None
    _home_anim_p = 1.0
    _home_anim_mode = "in"
    _home_fly = None                 # Kütüphane kartının büyüme animasyonu: (zaman, x1, y1, x2, y2)
    _par = (0, 0)                    # arka plan paralaks kayması (px)
    _home_bg_id = None
    home_cv = None

    def _home_at_start(self):
        if self.splash is not None or self.launching:
            self.after(500, self._home_at_start)
            return
        self.show_home()
        self.after(1000, self._home_tick)

    def _home_tick(self):
        if self._home_on and self._home_anim is None:
            self.home_redraw()          # saat her saniye güncellenir
        self.after(1000, self._home_tick)

    def show_home(self):
        if self.home_cv is None:
            self.home_cv = tk.Canvas(self, bg=T["bg"], highlightthickness=0, bd=0)
            self.home_cv.bind("<Configure>", lambda e: self.home_redraw())
            self.home_cv.bind("<Button-1>", self._home_click)
            self.home_cv.bind("<Motion>", self._home_motion)
        self._home_on = True
        self._home_panel = "menu"
        self.home_cv.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(self.home_cv)   # Canvas.lift() öğe yükseltir, pencere için Misc.lift
        self.close_video()
        self.video_photo = None
        self._save_music_resume()
        if self.music.ok and self.music.playing and not self.music.paused:
            self.music.pause_now()
        self.update_music_ui()
        try:
            self.ui_sound.play("menu")   # ana menüye geçiş sesi
        except Exception:
            pass
        self._home_start_anim("in", 0.7)

    def _save_music_resume(self):
        """Playlist'te çalan şarkıyı ve konumunu kaydeder; launcher kapanınca/menüye girince kullanılır."""
        m = self.music
        if not m.ok or m.mode != "playlist" or not m.current_file:
            return
        try:
            pos = m.paused_at if m.paused else m.get_pos()
            self.cfg["music_resume"] = {"file": m.current_file, "pos": round(float(pos), 1)}
        except Exception:
            pass

    def _resume_playlist(self):
        """Kayıtlı şarkıyı kaldığı yerden çalar. Oyun müziği çalıyorsa dokunmaz."""
        rs = self.cfg.get("music_resume")
        m = self.music
        if not rs or not m.ok or m.playing or m.mode == "game":
            return
        f = rs.get("file", "")
        if not f or not os.path.exists(f):
            self.cfg.pop("music_resume", None)
            return
        try:
            m._play(f, 0, start=float(rs.get("pos", 0)))
            m.mode = "playlist"
            if f in m.tracks:
                m.index = m.tracks.index(f)
            self.cfg.pop("music_resume", None)
            self.update_music_ui()
        except Exception:
            self.cfg.pop("music_resume", None)

    def hide_home(self):
        """Kütüphaneye geçiş: kartlar sola doğru kayarak kaybolur, sonra ızgara görünür."""
        if not self._home_on:
            return
        if self._home_anim is not None and self._home_anim_mode == "out":
            return
        self._home_start_anim("out", 0.75)

    def _home_finish_hide(self):
        self._home_on = False
        self._home_fly = None
        if self.home_cv is not None:
            self.home_cv.place_forget()
        self._resume_playlist()                      # önce kaldığı şarkıya dön (select bunu ezmesin)
        try:
            self.select(self.selected, force=True)   # kapak videosunu ve oyun müziğini yeniden kur
        except Exception:
            pass
        if self.music.ok and self.music.paused and not self.user_paused:
            self.music.toggle()
        self.update_music_ui()
        try:
            self.grid_cv.focus_set()
        except Exception:
            pass

    def _home_start_anim(self, mode, dur):
        self._home_anim = (time.perf_counter(), dur, mode)
        self._home_anim_p = 0.0
        self._home_anim_mode = mode
        self._home_anim_step()

    def _home_anim_step(self):
        if self._home_anim is None:
            return
        t0, dur, mode = self._home_anim
        p = min(1.0, (time.perf_counter() - t0) / dur)
        self._home_anim_p = p
        self._home_anim_mode = mode
        if self._home_on:
            self.home_redraw()
        if p < 1.0:
            self.after(16, self._home_anim_step)
            return
        self._home_anim = None
        if mode == "out":
            self._home_finish_hide()
        elif self._home_on:
            self.home_redraw()

    def _home_card_dx(self, n, w):
        """Yatay kayma (px): ana menüye girerken yok (kartlar yukarıdan iner), çıkarken sola gider."""
        if self._home_anim is None or self._home_anim_mode == "in":
            return 0
        local = max(0.0, min(1.0, (self._home_anim_p - n * 0.07) / 0.6))
        e = 1 - (1 - local) ** 3
        return int(-e * w * 0.7)                 # sola gider

    def _home_card_dy(self, n, h):
        """Girişte kartlar sırayla yukarıdan yerine iner. Animasyon yoksa 0."""
        if self._home_anim is None or self._home_anim_mode != "in":
            return 0
        local = max(0.0, min(1.0, (self._home_anim_p - n * 0.09) / 0.6))
        e = 1 - (1 - local) ** 3
        return int(-(1 - e) * h * 0.22)

    def _home_fly_start(self):
        """Ana menüde 'Kütüphane' kartı büyüyüp ekranı kaplar, sonra kütüphane açılır."""
        if self._home_fly is not None:
            return
        hit = next((x for x in self._home_hits if x[4] == ("menu", "kutuphane")), None)
        if hit is None:
            self.hide_home()
            return
        self._home_fly = (time.perf_counter(), hit[0], hit[1], hit[2], hit[3])
        self._home_fly_step()

    def _home_fly_step(self):
        if self._home_fly is None:
            return
        p = min(1.0, (time.perf_counter() - self._home_fly[0]) / 0.36)
        self.home_redraw()
        if p < 1.0:
            self.after(16, self._home_fly_step)
        else:
            self.hide_home()                     # kart tam ekranı kapladı; kütüphane ızgarası bundan sonra gelir

    def _unread_count(self):
        return sum(1 for n in self.cfg.get("notifications", []) if not n.get("read"))

    def _notify(self, kind, title, text=""):
        lst = self.cfg.setdefault("notifications", [])
        lst.insert(0, {"kind": kind, "title": title, "text": text,
                       "time": datetime.now().strftime("%d.%m %H:%M"), "read": False})
        del lst[60:]
        try:
            self.save()
        except Exception:
            pass
        if self._home_on:
            self.home_redraw()

    def _home_items(self):
        unread = self._unread_count()
        return [
            ("kutuphane", "Kütüphane", f"{len(self.games)} oyun", "▦"),
            ("playlist", "Playlist", f"{len(self.music.tracks)} şarkı", "♫"),
            ("bildirim", "Bildirimler", (f"{unread} yeni bildirim" if unread else "Yeni bildirim yok"), "🔔"),
            ("ayarlar", "Ayarlar", "Görünüm, ses, monitör ve güncelleme", "⚙"),
            ("cikis", "Çıkış", "Launcher'ı kapat", "⏻"),
        ]

    def home_redraw(self):
        if not self._home_on or self.home_cv is None:
            return
        c = self.home_cv
        w, h = c.winfo_width(), c.winfo_height()
        if w < 100 or h < 100:
            return
        g = self.current()
        kind = next((k for k in ("arkaplan", "kapak") if g and find_asset(g["id"], k)), None)
        dim = float(self.cfg.get("bg_dim", 0.36))
        blur = int(self.cfg.get("bg_blur", 4))
        key = (g["id"] if g else None, kind, w, h, dim, blur)
        if key != self._home_bgkey or "home_bg" not in self.refs:
            self._home_bgkey = key
            if kind:
                # küçük boyutta bulanıklaştır, sonra büyüt: tam çözünürlükte bulanıklaştırmaktan çok daha hızlı
                small = get_image(g, kind, (max(8, w // 4), max(8, h // 4))).convert("RGB")
                small = small.filter(ImageFilter.GaussianBlur(max(1, blur // 2)))
                small = ImageEnhance.Brightness(small).enhance(dim * 0.9)
                bg = small.resize((w, h), Image.BILINEAR)
            else:
                bg = Image.new("RGB", (w, h), (8, 10, 20))
            self.refs["home_bg"] = ImageTk.PhotoImage(bg)
        c.delete("all")
        self._home_hits = []
        px, py = self._par
        self._home_bg_id = c.create_image(px, py, image=self.refs["home_bg"], anchor="nw")

        pad = max(40, int(w * 0.08))
        top = int(h * 0.10)
        now = datetime.now()
        days = ("Pazartesi", "Salı", "Çarşamba", "Perşembe", "Cuma", "Cumartesi", "Pazar")
        c.create_text(pad, top, text="Multi Library", anchor="nw", fill=T["title"],
                      font=(FONT, int(max(28, w * 0.05)), "bold"))
        sub_y = top + int(w * 0.07)
        c.create_text(pad, sub_y, text="Hoş geldin", anchor="nw", fill=T["muted"], font=(FONT, 13))
        c.create_rectangle(pad, sub_y + 34, pad + 64, sub_y + 37, fill=T["accent"], outline="")
        # saat ve tarih (sağ üst)
        c.create_text(w - pad, top - 8, text=now.strftime("%H:%M"), anchor="ne", fill=T["title"],
                      font=(FONT, int(max(26, min(48, w * 0.035))), "bold"))
        c.create_text(w - pad, top + int(w * 0.035) + 16,
                      text=f"{now:%d.%m.%Y}  ·  {days[now.weekday()]}", anchor="ne",
                      fill=T["muted"], font=(FONT, 14))

        if self._home_panel == "notif":
            self._home_draw_notif(c, w, h, pad)
        else:
            self._home_draw_menu(c, w, h, pad)
        c.create_text(pad, h - 36, text="↑ ↓  Gezin      Enter  Seç      Esc  Geri", anchor="sw",
                      fill=T["muted"], font=(FONT, 11))

    def _home_draw_menu(self, c, w, h, pad):
        items = self._home_items()
        self._home_sel = max(0, min(self._home_sel, len(items) - 1))
        y0 = int(h * 0.38)
        card_h = int(min(150, h * 0.105))
        gap = 18
        fly = self._home_fly
        if fly is not None:                      # Kütüphane kartı büyüyüp ekranı kaplıyor
            t0, fx1, fy1, fx2, fy2 = fly
            p = min(1.0, (time.perf_counter() - t0) / 0.36)
            e = 1 - (1 - p) ** 3
            c.create_polygon(_rr_points(fx1 * (1 - e), fy1 * (1 - e), fx2 + (w - fx2) * e, fy2 + (h - fy2) * e,
                                        22 * (1 - e) + 2), smooth=True,
                             fill="#0c0f18", outline=T["accent"], width=2)
        for n, (key, title, sub, icon) in enumerate(items):
            dx = self._home_card_dx(n, w)
            dy = self._home_card_dy(n, h)
            y = y0 + n * (card_h + gap) + dy
            x1, x2 = pad + dx, w - pad + dx
            sel = n == self._home_sel
            c.create_polygon(_rr_points(x1, y, x2, y + card_h, 22), smooth=True,
                             fill=(T["row_sel"] if sel else "#0c0f18"),
                             outline=(T["accent"] if sel else "#1f2937"), width=(2 if sel else 1))
            c.create_text(x1 + 34, y + card_h / 2, text=icon, anchor="w", font=(FONT, 28), fill=T["title"])
            c.create_text(x1 + 110, y + card_h * 0.36, text=title, anchor="w", fill=T["title"],
                          font=(FONT, 22, "bold"))
            c.create_text(x1 + 110, y + card_h * 0.70, text=sub, anchor="w", fill=T["muted"],
                          font=(FONT, 12))
            if key == "bildirim":
                u = self._unread_count()
                if u:
                    bx, by = x2 - 60, y + card_h / 2
                    c.create_oval(bx - 18, by - 18, bx + 18, by + 18, fill=T["accent"], outline="")
                    c.create_text(bx, by, text=str(min(u, 99)), fill=T["accent_fg"], font=(FONT, 12, "bold"))
            if sel:
                c.create_text(x2 - 24, y + card_h / 2, text="▶", anchor="e", fill=T["accent"],
                              font=(FONT, 18, "bold"))
            self._home_hits.append((x1, y, x2, y + card_h, ("menu", key)))

    def _home_draw_notif(self, c, w, h, pad):
        c.create_text(pad, int(h * 0.32), text="BİLDİRİMLER", anchor="nw", fill=T["muted"],
                      font=(FONT, 12, "bold"))
        lst = self.cfg.get("notifications", [])[:6]
        y0 = int(h * 0.37)
        card_h = int(min(130, h * 0.09))
        gap = 12
        if not lst:
            c.create_text(pad, y0, text="Henüz bildirim yok.\nYeni oyun ve güncellemeler burada görünür.",
                          anchor="nw", fill=T["muted"], font=(FONT, 14))
        icons = {"new_game": "🎮", "update": "⬆", "info": "ℹ"}
        tw_text = w - 2 * pad - 200
        for n, b in enumerate(lst):
            yy = y0 + n * (card_h + gap)
            unread = not b.get("read")
            c.create_polygon(_rr_points(pad, yy, w - pad, yy + card_h, 18), smooth=True,
                             fill="#0c0f18", outline=(T["accent"] if unread else "#1f2937"),
                             width=(2 if unread else 1))
            c.create_text(pad + 26, yy + card_h / 2, text=icons.get(b.get("kind"), "•"), anchor="w",
                          font=(FONT, 22), fill=T["title"])
            c.create_text(pad + 80, yy + 16, text=b.get("title", ""), anchor="nw", fill=T["title"],
                          font=(FONT, 15, "bold"), width=tw_text)
            c.create_text(pad + 80, yy + 46, text=b.get("text", ""), anchor="nw", fill=T["text"],
                          font=(FONT, 11), width=tw_text)
            c.create_text(w - pad - 20, yy + 16, text=b.get("time", ""), anchor="ne", fill=T["muted"],
                          font=(FONT, 10))
            if b.get("kind") in ("new_game", "update"):
                c.create_text(w - pad - 20, yy + card_h - 18, text="Aç ›", anchor="se",
                              fill=T["accent"], font=(FONT, 10, "bold"))
            self._home_hits.append((pad, yy, w - pad, yy + card_h, ("notif_item", n)))
        btn_y = h - 170
        x = pad
        for label, action in (("← Geri", "back"), ("Okundu say", "read"), ("Temizle", "clear")):
            bw = 170
            c.create_polygon(_rr_points(x, btn_y, x + bw, btn_y + 46, 12), smooth=True,
                             fill="#1c2230", outline="")
            c.create_text(x + bw / 2, btn_y + 23, text=label, fill=T["title"], font=(FONT, 12, "bold"))
            self._home_hits.append((x, btn_y, x + bw, btn_y + 46, ("notif", action)))
            x += bw + 14

    def _home_click(self, e):
        for x1, y1, x2, y2, act in self._home_hits:
            if x1 <= e.x <= x2 and y1 <= e.y <= y2:
                self._home_do(act)
                return

    def _home_motion(self, e):
        # paralaks: fare konumuna göre arka plan çok az kayar (derinlik hissi)
        c = self.home_cv
        cw, ch = max(1, c.winfo_width()), max(1, c.winfo_height())
        self._par = (int((e.x - cw / 2) / cw * -14), int((e.y - ch / 2) / ch * -10))
        if self._home_bg_id is not None:
            try:
                c.coords(self._home_bg_id, *self._par)
            except tk.TclError:
                pass
        keys = [k for k, *_ in self._home_items()]
        for x1, y1, x2, y2, act in self._home_hits:
            if act[0] == "menu" and x1 <= e.x <= x2 and y1 <= e.y <= y2:
                idx = keys.index(act[1])
                if idx != self._home_sel:
                    self._home_sel = idx
                    self.home_redraw()
                return

    def _home_do(self, act):
        kind, key = act
        if kind == "menu":
            self.ui_sound.play("page")     # menüden seçenek açılırken sayfa çevirme sesi
            if key == "kutuphane":
                self._home_fly_start()
            elif key == "playlist":
                self.open_playlist()
            elif key == "bildirim":
                self._home_panel = "notif"
                self.home_redraw()
            elif key == "ayarlar":
                self.open_settings_menu(anchor=self.home_cv)
            elif key == "cikis":
                self.on_close()
            return
        if kind == "notif_item":
            lst = self.cfg.get("notifications", [])
            if 0 <= key < len(lst):
                b = lst[key]
                b["read"] = True
                self.save()
                if b.get("kind") == "new_game":
                    self.open_store_scan()
                elif b.get("kind") == "update":
                    self.check_update(manual=True)
            self.home_redraw()
            return
        if key == "back":
            self._home_panel = "menu"
        elif key == "read":
            for n in self.cfg.get("notifications", []):
                n["read"] = True
            self.save()
        elif key == "clear":
            self.cfg["notifications"] = []
            self.save()
        self.home_redraw()

    def home_move(self, step):
        if self._home_panel != "menu":
            return
        n = len(self._home_items())
        self._home_sel = (self._home_sel + step) % n
        self.home_redraw()

    def home_activate(self):
        if self._home_panel != "menu":
            return
        key = self._home_items()[self._home_sel][0]
        self._home_do(("menu", key))

    def apply_monitor(self):
        v = self.monitor_var.get()
        self.cfg["monitor"] = int(v) if v.isdigit() else v
        self.save()
        messagebox.showinfo("Açılış monitörü",
                            "Seçim kaydedildi. Bir sonraki açılışta launcher seçilen monitörde açılır.")

    # ------------------------------------------------------------ GÖRÜNÜM AYARLARI
    def apply_accent_preset(self, color):
        self.cfg["dynamic_accent"] = False
        self.cfg["accent_fixed"] = color
        self.save()
        self.apply_accent(color)      # tüm arayüzü (kenar çubuğu, liste, butonlar, ızgara) yeni renge boyar
        self.grid_rebuild()
        self.highlight()
        self.select(self.selected, force=True)

    def apply_grid_size(self):
        self.cfg["grid_size"] = self.grid_size_var.get()
        self.save()
        self.grid_rebuild()

    def apply_font_scale(self):
        sc = float(self.font_var.get())
        self.cfg["font_scale"] = sc
        self.save()
        self._gfont.configure(size=int(13 * sc))
        self._gfont_b.configure(size=int(13 * sc))
        self._gfont_s.configure(size=int(10 * sc))
        self.grid_rebuild()

    BRIGHTNESS_PRESETS = {       # (ızgara arka planı karartma, cam panel koyuluğu, detay arka planı parlaklığı)
        "parlak": (0.6, 110, 0.5),
        "normal": (0.36, 150, 0.3),
        "koyu": (0.2, 190, 0.2),
        "cok_koyu": (0.12, 225, 0.12),
    }

    def _brightness_key(self):
        dim = float(self.cfg.get("bg_dim", 0.36))
        return min(self.BRIGHTNESS_PRESETS,
                   key=lambda k: abs(self.BRIGHTNESS_PRESETS[k][0] - dim))

    def apply_brightness(self):
        dim, glass, hero = self.BRIGHTNESS_PRESETS.get(self.bright_var.get(), (0.36, 150, 0.3))
        self.cfg["bg_dim"] = dim
        self.cfg["glass_tint"] = glass
        self.cfg["hero_bright"] = hero
        self.glass_var.set(glass)
        self.bgdim_var.set(dim)
        self.save()
        self._grid_bg_key = None
        try:
            self.grid_update_bg()
            if self.view_mode == "detail" and self.selected is not None:
                self.select(self.selected, force=True, sound=None)
        except Exception:
            pass

    def apply_glass(self):
        self.cfg["glass_tint"] = int(self.glass_var.get())
        self.save()
        try:
            if self.view_mode == "detail" and self.selected is not None:
                self.select(self.selected, force=True, sound=None)
        except Exception:
            pass

    def apply_bg(self):
        self.cfg["bg_dim"] = float(self.bgdim_var.get())
        self.cfg["bg_blur"] = int(self.bgblur_var.get())
        self.save()
        self._grid_bg_key = None
        self.grid_update_bg()

    def show_theme_picker(self):
        win = tk.Toplevel(self)
        win.title("Tema seç")
        win.configure(bg=T["bg"])
        win.transient(self)
        win.resizable(False, False)
        tk.Label(win, text="Vurgu rengi", bg=T["bg"], fg=T["title"],
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=24, pady=(20, 10))
        grid = tk.Frame(win, bg=T["bg"])
        grid.pack(padx=24, pady=(0, 10))
        for n, (name, col) in enumerate(THEME_PRESETS.items()):
            cell = tk.Frame(grid, bg=T["bg"])
            cell.grid(row=n // 4, column=n % 4, padx=10, pady=10)
            swatch = tk.Frame(cell, bg=col, width=64, height=64, cursor="hand2")
            swatch.pack()
            swatch.pack_propagate(False)
            lbl = tk.Label(cell, text=name, bg=T["bg"], fg=T["text"], font=(FONT, 9), cursor="hand2")
            lbl.pack(pady=(4, 0))
            for w in (swatch, lbl):
                w.bind("<Button-1>", lambda e, c=col: self.apply_accent_preset(c))
        chip(win, "Tamam", win.destroy, primary=True, font=(FONT, 11)).pack(pady=(6, 20))

    # ------------------------------------------------------------ İLK AÇILIŞ REHBERİ
    def maybe_onboard(self):
        if self.splash is not None:
            self.after(800, self.maybe_onboard)
            return
        if self.games or self.cfg.get("onboarding_done"):
            return
        self.show_onboarding()

    def show_onboarding(self):
        win = tk.Toplevel(self)
        win.title("Hoş geldin")
        win.configure(bg=T["bg"])
        win.transient(self)
        win.resizable(False, False)
        tk.Label(win, text="Hoş geldin!", bg=T["bg"], fg=T["title"],
                 font=(FONT, 20, "bold")).pack(anchor="w", padx=28, pady=(24, 4))
        tk.Label(win, text="Kütüphaneni hazırlamak için üç adım:", bg=T["bg"], fg=T["muted"],
                 font=(FONT, 11)).pack(anchor="w", padx=28, pady=(0, 14))

        def step(num, title, desc, cmd, label):
            row = tk.Frame(win, bg=T["panel"])
            row.pack(fill="x", padx=28, pady=6)
            tk.Label(row, text=str(num), bg=T["accent"], fg=T["accent_fg"],
                     font=(FONT, 14, "bold"), width=3).pack(side="left", padx=(14, 12), pady=14)
            txt = tk.Frame(row, bg=T["panel"])
            txt.pack(side="left", fill="x", expand=True)
            tk.Label(txt, text=title, bg=T["panel"], fg=T["title"], font=(FONT, 12, "bold"),
                     anchor="w").pack(anchor="w")
            tk.Label(txt, text=desc, bg=T["panel"], fg=T["muted"], font=(FONT, 10),
                     anchor="w").pack(anchor="w")
            chip(row, label, cmd, primary=True, font=(FONT, 10)).pack(side="right", padx=14)

        step(1, "Oyunlarını tara", "Steam, Epic, EA ya da bir klasörden otomatik bul.",
             self.open_store_scan, "Tara")
        step(2, "Müzik klasörü seç", "Menüde arka planda çalacak şarkıların olduğu klasör.",
             self.pick_music_folder, "Seç")
        step(3, "Tema seç", "Vurgu rengini şimdi belirle, sonra Ayarlar'dan değiştirebilirsin.",
             self.show_theme_picker, "Seç")

        def done():
            self.cfg["onboarding_done"] = True
            self.save()
            win.destroy()

        chip(win, "Başla", done, primary=True, font=(FONT, 12)).pack(pady=(18, 22))
        win.protocol("WM_DELETE_WINDOW", done)

    # ------------------------------------------------------------ GÜNCELLEME KONTROLÜ
    _upd_busy = False
    _upd_result = None

    def check_update(self, manual=False):
        url = (self.cfg.get("update_url") or UPDATE_URL or "").strip()
        if not url:
            if manual:
                messagebox.showinfo("Güncelleme", "Güncelleme adresi ayarlı değil.\n\n"
                                    "launcher.py içindeki UPDATE_URL alanına sürüm bilgisi adresini yaz.")
            return
        if self._upd_busy:
            return
        self._upd_busy = True
        self._upd_result = None

        def work():
            try:
                req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=10) as r:
                    data = json.loads(r.read().decode("utf-8"))
                self._upd_result = ("ok", data)
            except Exception as e:
                self._upd_result = ("err", str(e))

        threading.Thread(target=work, daemon=True).start()
        self.after(400, lambda: self._upd_poll(manual))

    def _upd_poll(self, manual):
        if self._upd_result is None:
            self.after(400, lambda: self._upd_poll(manual))
            return
        self._upd_busy = False
        kind, data = self._upd_result
        self._upd_result = None
        if kind == "err":
            if manual:
                messagebox.showerror("Güncelleme", f"Sürüm bilgisi alınamadı:\n{data}")
            return
        remote = str(data.get("version", "")).strip()
        if remote and _ver_tuple(remote) > _ver_tuple(APP_VERSION):
            notes = data.get("notes", "")
            msg = f"Yeni sürüm var: {remote} (sen {APP_VERSION} kullanıyorsun)."
            if notes:
                msg += f"\n\n{notes}"
            self._notify("update", f"Yeni sürüm: {remote}", notes or "Güncelleme hazır.")
            if messagebox.askyesno("Güncelleme var", msg + "\n\nŞimdi güncellensin mi?"):
                self.do_update(data)
        elif manual:
            messagebox.showinfo("Güncelleme", f"Güncelsin. Sürüm {APP_VERSION}.")

    def do_update(self, data):
        url = str(data.get("url", "")).strip()
        if not url:
            return
        if getattr(sys, "frozen", False) or not url.lower().endswith(".py"):
            import webbrowser
            webbrowser.open(url)
            messagebox.showinfo("Güncelleme", "Yeni sürümü indirme sayfasından alıp üzerine kopyala.")
            return
        here = os.path.dirname(os.path.abspath(__file__))
        try:
            files = {"launcher.py": url}
            files.update(data.get("files") or {})
            blobs = {}
            for name, src in files.items():  # hepsi indirilip doğrulanmadan hiçbir dosya değişmez
                req = urllib.request.Request(src, headers={"User-Agent": "Mozilla/5.0"})
                with urllib.request.urlopen(req, timeout=20) as r:
                    blob = r.read()
                if name.endswith(".py"):
                    compile(blob.decode("utf-8"), name, "exec")
                blobs[name] = blob
            bdir = os.path.join(here, "backups")
            os.makedirs(bdir, exist_ok=True)
            stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            for name, blob in blobs.items():
                dst = os.path.join(here, name)
                if os.path.exists(dst):
                    shutil.copy2(dst, os.path.join(bdir, f"{stamp}_{name}.bak"))
                fx.atomic_write(dst, blob)
        except Exception as e:
            messagebox.showerror("Güncelleme başarısız",
                                 f"Güncelleme uygulanamadı, mevcut sürüm değişmedi:\n{e}")
            return
        messagebox.showinfo("Güncellendi", "Güncelleme kuruldu. Launcher'ı yeniden aç.")
        self.on_close()

    def open_store_scan(self):
        if not self.check_idle():
            return
        if self._auto_scanning:
            messagebox.showinfo("Tarama", "Otomatik tarama sürüyor, birkaç saniye sonra tekrar dene.")
            return
        self.run_bg(ex.scan_all, self.show_scan_results,
                    "Mağaza oyunları taranıyor...", refresh=False)

    def open_folder_scan(self):
        if not self.check_idle():
            return
        d = filedialog.askdirectory(parent=self,
                                    title="Oyunların kurulu olduğu klasörü seç (ör. EA Games klasörü)")
        if not d:
            return
        self.run_bg(lambda: ex.scan_folder(d), self.show_scan_results,
                    "Klasör taranıyor...", refresh=False)

    def open_scan_report(self):
        p = ex.REPORT_FILE
        if not os.path.exists(p):
            messagebox.showinfo("Rapor", "Henüz bir tarama raporu yok. Önce \"Mağaza oyunlarını tara\" çalıştır.")
            return
        try:
            os.startfile(p)
        except Exception as e:
            messagebox.showerror("Hata", f"Rapor açılamadı:\n{e}\n\nDosya: {p}")

    def _new_games(self, found):
        have = {(g.get("source", ""), g.get("store_id", "")) for g in self.games if g.get("store_id")}
        paths = {os.path.normcase(g["path"]) for g in self.games if g.get("path")}
        return [f for f in found
                if (f["source"], f["store_id"]) not in have
                and os.path.normcase(f["path"]) not in paths]

    def show_scan_results(self, found):
        new = self._new_games(found)
        if not new:
            messagebox.showinfo("Tarama bitti",
                                ("Yeni oyun bulunamadı.\n\nEksik oyun varsa Ayarlar > \"Klasörden oyun tara...\" "
                                 "ile oyunun klasörünü göster." if not found else
                                 f"{len(found)} oyun bulundu, hepsi zaten listende."))
            return
        self.scan_window(new)

    def scan_window(self, new):
        win = tk.Toplevel(self)
        win.title("Bulunan oyunlar")
        win.geometry("560x720")
        win.configure(bg=T["bg"])
        win.transient(self)
        tk.Label(win, text=f"{len(new)} yeni oyun bulundu", bg=T["bg"], fg=T["title"],
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(18, 8))

        wrap = tk.Frame(win, bg=T["bg"])
        wrap.pack(fill="both", expand=True, padx=20)
        cv = tk.Canvas(wrap, bg=T["panel"], highlightthickness=0)
        sb = tk.Scrollbar(wrap, orient="vertical", command=cv.yview)
        cv.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        cv.pack(side="left", fill="both", expand=True)
        inner = tk.Frame(cv, bg=T["panel"])
        cv.create_window((0, 0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: cv.configure(scrollregion=cv.bbox("all")))
        cv.bind("<Enter>", lambda e: cv.bind_all(
            "<MouseWheel>", lambda ev: cv.yview_scroll(-int(ev.delta / 120), "units")))
        cv.bind("<Leave>", lambda e: (cv.unbind_all("<MouseWheel>"),
                                      self.bind_all("<MouseWheel>", self.on_wheel)))

        vars_ = []
        for f in new:
            v = tk.BooleanVar(value=True)
            vars_.append(v)
            tk.Checkbutton(inner, text=f"{f['name']}   ·   {f['source']}", variable=v,
                           bg=T["panel"], fg=T["text"], selectcolor=T["bg"],
                           activebackground=T["panel"], activeforeground=T["title"],
                           anchor="w", font=(FONT, 11)).pack(fill="x", padx=10, pady=2)

        def set_all(val):
            for v in vars_:
                v.set(val)

        def add_selected():
            chosen = [f for f, v in zip(new, vars_) if v.get()]
            win.destroy()
            if chosen:
                self.add_scanned(chosen)

        btns = tk.Frame(win, bg=T["bg"])
        btns.pack(fill="x", padx=20, pady=16)
        chip(btns, "Seçilenleri ekle", add_selected, primary=True, font=(FONT, 11)).pack(side="left")
        chip(btns, "Tümünü seç", lambda: set_all(True), font=(FONT, 11)).pack(side="left", padx=8)
        chip(btns, "Hiçbiri", lambda: set_all(False), font=(FONT, 11)).pack(side="left")

    def add_scanned(self, items):
        used = {g["id"] for g in self.games}
        n, added = 1, []
        for it in items:
            while f"oyun{n}" in used:
                n += 1
            gid = f"oyun{n}"
            used.add(gid)
            g = {"id": gid, "name": it["name"], "path": it["path"], "args": it.get("args", ""),
                 "admin": False, "install_dir": it.get("install_dir", ""),
                 "source": it["source"], "store_id": it.get("store_id", ""),
                 "last_played": "", "added": _today(), "color": color_for(gid)}
            self.games.append(g)
            added.append(g)
        self.save()
        self.search_var.set("")
        self.selected = len(self.games) - len(added)
        self.refresh_all()
        if added:
            self.run_bg(lambda: self._fetch_store_art(added), None, "Mağaza görselleri indiriliyor...")

    def _fetch_store_art(self, games, only_missing=False):
        """Kapak, arka plan ve ikonu oyunun mağazasından indirir.
        only_missing=True ise kullanıcının elle koyduğu / zaten var olan görsellere dokunmaz."""
        for g in games:
            self.status["text"] = f"Görseller indiriliyor: {g['name']}"
            try:
                cands = ex.art_candidates(g)
            except Exception:
                continue
            for kind in ("kapak", "arkaplan", "ikon"):
                if only_missing and find_asset(g["id"], kind):
                    continue
                saved = False
                for c in cands.get(kind, []):
                    img = ex.load_art(c)
                    if img is None:
                        continue
                    img.thumbnail((2560, 2560))
                    remove_assets(g["id"], kind)
                    img.save(os.path.join(ASSETS_DIR, f"{g['id']}_{kind}.png"), "PNG")
                    saved = True
                    break
                if kind == "ikon" and not saved and not find_asset(g["id"], "ikon"):
                    # Hiçbir kaynaktan ikon alınamadıysa kapaktan kare ikon üret
                    cover = find_asset(g["id"], "kapak")
                    if cover:
                        try:
                            img = Image.open(cover).convert("RGBA")
                            img = ImageOps.fit(img, (256, 256), Image.LANCZOS, centering=(0.5, 0.3))
                            img.save(os.path.join(ASSETS_DIR, f"{g['id']}_ikon.png"), "PNG")
                        except Exception:
                            pass

    def refresh_store_art(self):
        if not self.check_idle():
            return
        games = [g for g in self.games if g.get("source")]
        if not games:
            messagebox.showinfo("Görseller", "Mağazadan eklenmiş oyun yok.")
            return
        self.run_bg(lambda: self._fetch_store_art(games, only_missing=True),
                    None, "Eksik görseller indiriliyor...")

    def delete_game(self):
        g = self.current()
        if not g or not self.check_idle():
            return
        if not messagebox.askyesno("Oyunu sil",
                                   f"\"{g['name']}\" launcher'dan kaldırılsın mı?\n(Oyunun kendisi silinmez.)"):
            return
        self._remove_entry(g)

    def _remove_entry(self, g):
        self.close_video()
        self.video_photo = None
        self.music.release()
        for kind in KINDS:
            remove_assets(g["id"], kind)
        del self.games[self.selected]
        self.save()
        self.selected = min(self.selected, len(self.games) - 1)
        self.refresh_all()
        self.apply_music_for_game(self.current())

    def _find_uninstall_string(self, g, d):
        """Windows kayıt defterinden (Uninstall anahtarları) kaldırıcı komutunu bulur."""
        if not ex.IS_WIN:
            return ""
        import winreg

        def val(k, n):
            try:
                return str(winreg.QueryValueEx(k, n)[0] or "")
            except OSError:
                return ""

        name = (g.get("name") or "").strip().lower()
        norm_d = os.path.normcase(d.rstrip("\\/")) if d else ""
        subs = (r"Software\Microsoft\Windows\CurrentVersion\Uninstall",
                r"Software\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall")
        for hive in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for sub in subs:
                try:
                    root = winreg.OpenKey(hive, sub, 0, winreg.KEY_READ)
                except OSError:
                    continue
                with root:
                    i = 0
                    while True:
                        try:
                            kn = winreg.EnumKey(root, i)
                        except OSError:
                            break
                        i += 1
                        try:
                            with winreg.OpenKey(root, kn) as k:
                                dn = val(k, "DisplayName").strip().lower()
                                us = val(k, "UninstallString")
                                loc = os.path.normcase(val(k, "InstallLocation").rstrip("\\/"))
                        except OSError:
                            continue
                        if not us:
                            continue
                        if (norm_d and loc == norm_d) or (name and dn == name):
                            return us
        return ""

    def _find_uninstaller_file(self, d):
        """Oyun klasöründe (en fazla 1 alt klasör derinliğinde) unins*.exe arar."""
        if not d or not os.path.isdir(d):
            return ""
        cands = []
        base_depth = d.rstrip("\\/").count(os.sep)
        for root, dirs, files in os.walk(d):
            if root.rstrip("\\/").count(os.sep) - base_depth >= 1:
                dirs[:] = []
            for f in files:
                fl = f.lower()
                if fl.endswith(".exe") and ("unins" in fl or "uninstall" in fl):
                    cands.append(os.path.join(root, f))
        cands.sort(key=len)
        return cands[0] if cands else ""

    def uninstall_game(self):
        g = self.current()
        if not g or not self.check_idle():
            return
        d = self.install_dir(g)
        # 1) Steam oyunlarında Steam'in kendi kaldırma penceresi
        if g.get("source") == "Steam" and g.get("appid"):
            action = ("uri", f"steam://uninstall/{g['appid']}")
        else:
            # 2) Oyun klasöründeki kaldırıcı
            exe = self._find_uninstaller_file(d)
            if exe:
                action = ("file", exe)
            else:
                # 3) Windows kayıt defterindeki kaldırıcı
                cmd = self._find_uninstall_string(g, d)
                action = ("cmd", cmd) if cmd else None

        if action is None:
            if messagebox.askyesno("Kaldırıcı bulunamadı",
                                   f"\"{g['name']}\" için kaldırıcı bulunamadı.\n"
                                   "Oyun sadece launcher listesinden silinsin mi?\n"
                                   "(Oyunun dosyaları silinmez.)"):
                self._remove_entry(g)
            return

        kind, target = action
        try:
            if kind == "file" or kind == "uri":
                os.startfile(target)
            else:
                subprocess.Popen(target, shell=True)
        except Exception as e:
            messagebox.showerror("Hata", f"Kaldırıcı açılamadı:\n{e}")
            return

        if messagebox.askyesno("Launcher listesi",
                               f"Kaldırıcı açıldı.\n\"{g['name']}\" launcher listesinden de silinsin mi?"):
            self._remove_entry(g)

    def _play_busy(self, on):
        """Başlatılan oyunun OYNA düğmesi yeşile döner; yalnızca o oyun seçiliyken görünür."""
        g = self.current()
        self._busy_gid = (g["id"] if g else None) if on else None
        self._play_busy_visual(on)

    def _sync_busy(self):
        g = self.current()
        bg = getattr(self, "_busy_gid", None)
        self._play_busy_visual(bool(bg and g and g["id"] == bg))

    def _play_busy_visual(self, on):
        """OYNA düğmelerinin rengini ve yazısını ayarlar."""
        green = "#22c55e"
        try:
            sb = self.split_btn
            sb.busy = on
            sb.main_btn.configure(bg=green if on else "#ffffff")
            sb.lbl.configure(bg=green if on else "#ffffff", fg="#000000",
                             text="✓  ÇALIŞIYOR" if on else "OYNA")
        except (tk.TclError, AttributeError):
            pass
        for b in list(getattr(self, "_primary_btns", [])):
            try:
                b.custom_bg = green if on else None
                b.custom_fg = "#000000" if on else None
                b._lbl.configure(text="✓  ÇALIŞIYOR" if on else f"{b.icon}  {b.text}".strip())
                b._apply_colors()
            except (tk.TclError, AttributeError):
                pass

    def start_game(self):
        g = self.current()
        if not g or self.launching:
            return
        if not ex.is_launchable(g):
            if not self.pick_path():
                return
        try:
            mode = ex.launch_game(g)
        except Exception as e:
            messagebox.showerror("Hata", f"Oyun başlatılamadı:\n{e}")
            return
        self.ui_sound.play("launch")
        g["last_played"] = datetime.now().isoformat(timespec="minutes")
        g["launch_count"] = int(g.get("launch_count", 0) or 0) + 1
        self.save()
        if self.cfg["pause_on_launch"]:
            self._auto_paused = bool(self.music.ok and self.music.playing and not self.music.paused)
            self.music.pause_now()
            self.user_paused = True
            self.update_music_ui()
        self._start_watch(g, mode)
        self.redraw()
        self.launch_transition(g)
        if self.launching:
            self._play_busy(True)

    # ------------------------------------------------------------ VURGU RENGİ
    def accent_target(self, g):
        if not self.cfg.get("dynamic_accent", True):
            return self.cfg.get("accent_fixed", DEFAULT_ACCENT)
        if not g:
            return DEFAULT_ACCENT
        return game_accent(g)

    def apply_accent(self, color):
        set_accent_colors(color)
        try:
            c = self.canvas
            c.itemconfigure("acc_fill", fill=T["accent"])
            c.itemconfigure("acc_line", outline=T["accent"])
            c.itemconfigure("acc_panel", outline=blend("#0b0d1a", T["accent"], 0.45))
            self.play_pause_btn.configure(fg=T["accent"])
            self.vol.configure(activebackground=T["accent"])
            if self.view_mode == "grid":
                self.grid_cv.itemconfigure("gborder", outline=T["accent"])
                self._grid_style(self.selected)
                self.fx_accent()
            alive = []
            for b in self._primary_btns:
                try:
                    b._apply_colors()
                    alive.append(b)
                except tk.TclError:
                    pass
            self._primary_btns = alive
            if self.selected in self.rows:
                self.paint_row(self.selected)
            if self.pad_menu is not None:
                self.pad_menu.configure(highlightbackground=T["accent"])
                self.pad_menu_paint()
            self._draw_progress()
        except tk.TclError:
            pass

    def update_accent(self, g, animate=True):
        """Arayüzün vurgu rengini oyunun kapağındaki baskın renge yumuşakça geçirir."""
        target = self.accent_target(g)
        start = T["accent"]
        self._acc_token += 1
        token = self._acc_token
        if start.lower() == target.lower():
            return
        if not animate:
            self.apply_accent(target)
            return
        steps = 14

        def step(k):
            if token != self._acc_token:
                return
            e = 1 - (1 - k / steps) ** 3
            self.apply_accent(target if k >= steps else blend(start, target, e))
            if k < steps:
                self.after(24, lambda: step(k + 1))
        step(1)

    # ------------------------------------------------------------ TAM EKRAN
    def _win_move(self, x, y, w, h):
        """Pencereyi Windows API ile doğrudan hedef monitöre taşır (Tk geometry'si bazen yok sayılıyor)."""
        if not ex.IS_WIN:
            return
        import ctypes
        try:
            hwnd = int(self.wm_frame(), 16)
            ctypes.windll.user32.SetWindowPos(hwnd, None, int(x), int(y), int(w), int(h), 0x0040 | 0x0004)
        except Exception:
            pass

    def _kol_hedef(self):
        """Xbox ile açılış: kapak modu, dikey monitör, tam ekran (açıksa önce tam ekrandan çıkarır)."""
        m = target_monitor("portrait")
        if m:
            self._open_geom = f"{m[2]}x{m[3]}+{m[0]}+{m[1]}"
            self._kol_rect = m
        if self.view_mode != "grid":
            self.set_view_mode("grid")
        # Tam ekran kapalı: pencere doğrudan dikey monitörün koordinatına taşınır.
        self.set_fullscreen(False)
        try:
            self.update()
            self.wm_state("normal")
            if m:
                self.update()
                self._win_move(m[0], m[1], m[2], m[3])
            self.update()
        except tk.TclError:
            pass
        self.after(300, self._kol_tam_ekran)

    def _kol_tam_ekran(self):
        """Kumandayla açılışta tam ekran (-fullscreen) kullanılmaz: pencere dikey monitörün
        tüm alanına yerleştirilir (kenarlıklı ama monitöre tam oturur)."""
        r = getattr(self, "_kol_rect", None)
        try:
            if r:
                self._win_move(r[0], r[1], r[2], r[3])
            self.update_idletasks()
        except tk.TclError:
            return

    def _open_on_target(self):
        """Açılışta pencereyi önce seçilen monitöre yerleştirir, sonra tam ekran yapar.
        Windows pencereyi bazen birincil monitöre açıp tam ekranı oraya alabiliyor."""
        g = getattr(self, "_open_geom", None)
        if g:
            try:
                self.geometry(g)
                self.update_idletasks()
            except tk.TclError:
                pass
        self.set_fullscreen(True)

    def set_fullscreen(self, on):
        self.fullscreen = bool(on)
        try:
            self.attributes("-fullscreen", self.fullscreen)
        except tk.TclError:
            pass
        self.cfg["fullscreen"] = self.fullscreen
        try:
            self.save()
        except Exception:
            pass

    def toggle_fullscreen(self, e=None):
        self.ui_sound.play("menu")
        self.set_fullscreen(not self.fullscreen)
        return "break"

    def on_escape(self, e):
        try:
            if e.widget.winfo_toplevel() is not self:
                return
        except Exception:
            return
        if self.launching:
            self.launch_finish(force=True)
            return "break"
        if self.pad_menu_open():
            self.pad_menu_close()
            return "break"
        if self._home_on:
            if self._home_panel == "notif":
                self._home_panel = "menu"
                self.home_redraw()
            elif self.games:
                self.hide_home()
            return "break"
        if self.toast:
            self.toast_dismiss()
            return "break"
        if self.fullscreen:
            self.set_fullscreen(False)
            return "break"
        if self.view_mode == "grid" and self.games:
            self.show_home()
            return "break"

    # ------------------------------------------------------------ OYUN TAKİBİ / TEPSİ
    def _track_dir(self, g):
        d = self.install_dir(g)
        if not d:
            return ""
        d = os.path.normpath(d)
        if not os.path.splitdrive(d)[1].strip("\\/"):
            return ""  # sürücü kökünü izleme
        return d

    def _start_watch(self, g, mode):
        """Oyun süreci başlayınca launcher tepsiye iner, oyun kapanınca geri gelir."""
        self._watch_stop.set()
        d = self._track_dir(g)
        if not d or not ex.IS_WIN:
            return
        stop = threading.Event()
        self._watch_stop = stop
        gid = g["id"]
        threading.Thread(target=ex.watch_game, daemon=True,
                         args=(d, lambda ev: self.ui_q.put(("game", ev, gid, mode)), stop)).start()

    def ui_poll(self):
        # kısayol dinleyicisi için durum bildirimi: açık mı, tepside mi
        now = time.time()
        if now - getattr(self, "_hb_t", 0) > 1.0:
            self._hb_t = now
            try:
                with open(os.path.join(BASE_DIR, "calisiyor.txt"), "w", encoding="utf-8") as f:
                    f.write("tepsi" if self._hidden else "acik")
            except OSError:
                pass
        # kapat sinyali (F7'ye ikinci kez basılınca) gelirse launcher'ı kapat
        kapat = os.path.join(BASE_DIR, "kapat.flag")
        if os.path.exists(kapat):
            try:
                os.remove(kapat)
            except OSError:
                pass
            self.on_close()
            return
        # kısayol dinleyicisi (F7 / Xbox düğmesi) "göster" dosyası bırakırsa pencereyi öne getir
        flag = os.path.join(BASE_DIR, "goster.flag")
        if os.path.exists(flag):
            try:
                with open(flag, encoding="utf-8") as f:
                    kol = f.read().strip() == "kol"
                os.remove(flag)
                if self._hidden:
                    self._leave_tray()
                if kol:                      # Xbox düğmesi: dikey monitörde tam ekran kapak modu
                    self._kol_hedef()
                self.deiconify()
                self.lift()
                self.focus_force()
            except Exception:
                pass
        try:
            while True:
                msg = self.ui_q.get_nowait()
                try:
                    self._handle_ui(msg)
                except Exception:
                    import traceback
                    traceback.print_exc()
        except queue.Empty:
            pass
        self.after(150, self.ui_poll)

    def _handle_ui(self, msg):
        kind = msg[0]
        if kind == "tray_show":
            self._leave_tray()
        elif kind == "tray_quit":
            self.on_close()
        elif kind == "game":
            self._on_game_event(*msg[1:])
        elif kind == "scan":
            self._on_auto_scan(msg[1], msg[2])
        elif kind == "remote":
            self._remote_exec(msg[1], msg[2])

    def _on_game_event(self, ev, gid, mode):
        g = next((x for x in self.games if x["id"] == gid), None)
        if ev in ("started", "ended", "timeout"):
            self._launch_close()      # oyun açıldı / kapandı / zaman aşımı: başlatma ekranını hemen kaldır
        if ev == "started":
            self._play_t0.setdefault(gid, time.time())
            self.game_running = gid
            if g and self.cfg.get("tray_on_launch", True):
                self._enter_tray(g)
        elif ev == "ended":
            if self._flush_playtime(gid) and self.view_mode == "grid":
                self.grid_rebuild()
            if self.game_running == gid:
                self.game_running = None
            self._leave_tray()
            if self._auto_paused:
                self._auto_paused = False
                if self.music.ok and self.music.paused:
                    self.music.toggle()
                    self.user_paused = False
                    self.update_music_ui()
        elif ev == "timeout" and g and mode == "store" and g.get("source") == "EA app":
            messagebox.showinfo(
                "EA app",
                f"\"{g['name']}\" EA app üzerinden başlatılmış görünmüyor.\n\n"
                "Oyunun menüsünden \"Bilgileri düzenle\" > \"EA app yerine exe'yi doğrudan başlat\" "
                "seçeneğini deneyebilirsin.")

    def _flush_playtime(self, gid):
        """Çalışan oyunun geçen süresini toplam süreye ekler. Eklediyse True."""
        t0 = self._play_t0.pop(gid, None)
        g = next((x for x in self.games if x["id"] == gid), None)
        if t0 is None or g is None:
            return False
        g["play_seconds"] = int(g.get("play_seconds", 0) or 0) + max(0, int(time.time() - t0))
        try:
            self.save()
        except Exception:
            pass
        return True

    def _enter_tray(self, g):
        if self._hidden:
            return
        self._hidden = True
        try:
            img = get_image(g, "ikon", (64, 64)).convert("RGBA")
        except Exception:
            img = Image.new("RGBA", (64, 64), T["accent"])
        ok = self.tray.start(img, f"Oyun Launcher - {g['name']} açık",
                             lambda: self.ui_q.put(("tray_show",)),
                             lambda: self.ui_q.put(("tray_quit",)))
        if ok:
            self.withdraw()
        else:
            self.iconify()  # pystray yoksa görev çubuğuna küçült

    def _leave_tray(self):
        self.tray.stop()
        self._hidden = False
        try:
            self.deiconify()
            if self.fullscreen:
                self.attributes("-fullscreen", True)
            self.lift()
            self.attributes("-topmost", True)  # Windows'un odak engelini aşmak için kısa süre üstte tut
            self.after(400, lambda: self.attributes("-topmost", False))
            self.focus_force()
        except tk.TclError:
            pass

    # ------------------------------------------------------------ KUMANDA
    def _pad_volume(self, delta):
        v = max(0, min(100, int(self.vol.get()) + delta))
        self.vol.set(v)
        self.on_volume(v)

    def _pad_can_act(self):
        """Yalnızca launcher görünür ve odaktaysa kumandayı dinle (oyun açıkken karışmasın)."""
        if self.splash is not None:
            self._intro_skip_now()  # herhangi bir tuş açılışı atlar
            return False
        if self._hidden:
            return False
        try:
            if self.state() != "normal":
                return False
            w = self.focus_displayof()
            return w is not None and w.winfo_toplevel() is self
        except Exception:
            return False

    def pad_poll(self):
        delay = 500
        try:
            if self.cfg.get("gamepad", True):
                events = self.pad.poll()
                delay = 250 if self._hidden else (33 if self.pad.connected else 500)
                if self.pad.connected and not self._hidden:
                    self.fx_pad_tilt()
                if events and self._idle_touch():
                    events = []   # boşta ekranından uyandıran tuş başka iş yapmasın
                if events and self._pad_can_act():
                    for ev in events:
                        self.pad_event(ev)
        except Exception:
            delay = 1000
        self.after(delay, self.pad_poll)

    def pad_event(self, ev):
        if self.pad_menu_open():
            if ev == "up":
                self.pad_menu_move(-1)
            elif ev == "down":
                self.pad_menu_move(1)
            elif ev == "a":
                self.pad_menu_activate()
            elif ev in ("b", "y", "start"):
                self.pad_menu_close()
            return
        if self.toast and ev in ("a", "b"):
            if ev == "a" and self.toast.get("primary"):
                self.toast["primary"]()
            else:
                self.toast_dismiss()
            return
        if ev in ("lt", "rt"):
            self._pad_volume(5 if ev == "rt" else -5)
            return
        if self._home_on:                       # ana menü kumanda ile gezilir
            if ev in ("up", "down"):
                self.home_move(-1 if ev == "up" else 1)
            elif ev == "a":
                self.home_activate()
            elif ev == "b" and self._home_panel != "menu":
                self._home_do(("nav", "back"))
            return
        if self.view_mode == "grid" and ev in ("up", "down", "left", "right"):
            self.grid_move({"left": -1, "right": 1}.get(ev, 0), {"up": -1, "down": 1}.get(ev, 0))
            return
        if ev == "up":
            self.move_selection(-1)
        elif ev == "down":
            self.move_selection(1)
        elif ev in ("left", "right"):
            self._pad_volume(5 if ev == "right" else -5)
        elif ev == "a":
            self.start_game()
        elif ev == "b":
            if self.view_mode == "detail":
                self.set_view_mode("grid")
        elif ev == "x":
            self.music_toggle()
        elif ev == "lb":
            self.music_prev()
        elif ev == "rb":
            self.music_next()
        elif ev == "back":
            self.toggle_fullscreen()
        elif ev in ("start", "y"):
            self.pad_menu_show()

    def pad_menu_open(self):
        return self.pad_menu is not None

    def pad_menu_show(self):
        if self.pad_menu is not None:
            return
        self.ui_sound.play("menu")
        g = self.current()
        items = []
        if g:
            items.append((f"▶  Oyna: {g['name']}", self.start_game))
        items += [
            ("⛶  Tam ekrandan çık" if self.fullscreen else "⛶  Tam ekran", self.toggle_fullscreen),
            ("▦  Detay görünümüne geç" if self.view_mode == "grid" else "▦  Kapak ızgarasına dön",
             self.toggle_view),
        ]
        if g:
            items.append(("⬇  Oyun bilgilerini getir", self.fetch_info))
        items += [
            ("⟳  Yeni oyunları tara", lambda: self.auto_scan(manual=True)),
            ("♫  Müziği oynat / duraklat", self.music_toggle),
            ("⏭  Sonraki şarkı", self.music_next),
        ]
        if self.view_mode == "detail":
            items.append(("☰  Kenar çubuğunu aç / kapat", self.toggle_sidebar))
        items.append(("✕  Launcher'ı kapat", self.on_close))
        self.pad_menu_sel = 0
        frame, labels = self.glass_menu_show(items)
        self.pad_menu, self.pad_menu_items, self.pad_menu_labels = frame, items, labels
        self.pad_menu_paint()

    def pad_menu_paint(self):
        self.glass_menu_paint()

    def pad_menu_select(self, i):
        self.pad_menu_sel = i
        self.pad_menu_paint()

    def pad_menu_move(self, step):
        if not self.pad_menu_labels:
            return
        self.pad_menu_sel = (self.pad_menu_sel + step) % len(self.pad_menu_labels)
        self.ui_sound.play("move")
        self.pad_menu_paint()

    def pad_menu_activate(self):
        if self.pad_menu is None:
            return
        cb = self.pad_menu_items[self.pad_menu_sel][1]
        self.pad_menu_close()
        self.after(50, cb)

    def pad_menu_close(self):
        if self.pad_menu is not None:
            try:
                self.pad_menu.destroy()
            except tk.TclError:
                pass
        self.pad_menu, self.pad_menu_items, self.pad_menu_labels = None, [], []

    # ------------------------------------------------------------ BİLDİRİM / OTOMATİK TARAMA
    def show_toast(self, text, actions=(), timeout=None):
        """Alt ortada küçük bildirim. İlk eylem birincil (kumandada A), B ya da ✕ kapatır."""
        self.toast_dismiss()
        f = tk.Frame(self.canvas, bg=T["panel"], highlightthickness=1, highlightbackground=T["accent"])
        tk.Label(f, text=text, bg=T["panel"], fg=T["title"], font=(FONT, 11), padx=14, pady=10,
                 justify="left", wraplength=520).pack(side="left")
        primary = None
        for i, (label, cb) in enumerate(actions):
            def run(cb=cb):
                self.toast_dismiss()
                cb()
            b = chip(f, label, run, primary=(i == 0), font=(FONT, 10))
            b.pack(side="left", padx=(0, 8), pady=8)
            if i == 0:
                primary = run
                self._primary_btns.append(b)
        chip(f, "✕", self.toast_dismiss, font=(FONT, 10)).pack(side="left", padx=(0, 10))
        f.place(relx=0.5, rely=1.0, y=-24, anchor="s")
        f.lift()
        self.toast = {"frame": f, "primary": primary, "job": None}
        if timeout:
            self.toast["job"] = self.after(timeout, self.toast_dismiss)
        self.ui_sound.play("menu")

    def toast_dismiss(self):
        t = self.toast
        if not t:
            return
        self.toast = None
        if t.get("job"):
            try:
                self.after_cancel(t["job"])
            except Exception:
                pass
        try:
            t["frame"].destroy()
        except tk.TclError:
            pass

    def auto_scan(self, manual=False):
        """Mağazaları arka planda (hızlı modda) tarar; yeni oyun varsa bildirim gösterir."""
        if not ex.IS_WIN:
            if manual:
                self.show_toast("Mağaza taraması yalnızca Windows'ta çalışır.", timeout=4000)
            return
        if self._auto_scanning:
            return
        self._auto_scanning = True
        if manual:
            self.show_toast("Yeni oyunlar aranıyor...", timeout=60000)

        def work():
            try:
                found = ex.scan_all(quick=True)
            except Exception:
                found = []
            self.ui_q.put(("scan", found, manual))
        threading.Thread(target=work, daemon=True).start()

    def _on_auto_scan(self, found, manual):
        self._auto_scanning = False
        ignored = set(self.cfg.get("ignored_scan", []))
        fresh = [f for f in self._new_games(found) if scan_key(f) not in ignored]
        if not fresh:
            if manual:
                self.show_toast("Yeni oyun bulunamadı.", timeout=4000)
            elif self.toast and not self.toast.get("primary"):
                self.toast_dismiss()
            return
        names = ", ".join(f["name"] for f in fresh[:3]) + ("…" if len(fresh) > 3 else "")
        self._notify("new_game", f"{len(fresh)} yeni oyun bulundu", names)
        if not manual:
            return          # açılışta sessiz tarama: sadece bildirim kutusuna yazılır
        self.show_toast(f"🎮 {len(fresh)} yeni oyun bulundu: {names}",
                        actions=[("Ekle", lambda: self.add_scanned(fresh)),
                                 ("Seç...", lambda: self.scan_window(fresh)),
                                 ("Yoksay", lambda: self._ignore_scan(fresh))])

    def _ignore_scan(self, items):
        ign = set(self.cfg.get("ignored_scan", []))
        ign.update(scan_key(f) for f in items)
        self.cfg["ignored_scan"] = sorted(ign)
        self.save()

    # ------------------------------------------------------------ YAPILANDIRMA YEDEĞİ
    def backup_now(self):
        try:
            self.save()
        except Exception:
            pass
        p = fx.make_backup(CONFIG_FILE, force=True)
        self.show_toast("Yedek alındı." if p else "Yedek alınamadı.", timeout=3500)

    def _offer_restore(self):
        """Açılışta launcher_config.json okunamadıysa son yedekten geri yüklemeyi önerir."""
        err = LOAD_STATE.get("error")
        if not err:
            return
        LOAD_STATE["error"] = ""
        msg = "Yapılandırma dosyası (launcher_config.json) okunamadı:\n" + err[:200] + "\n"
        if LOAD_STATE.get("moved_to"):
            msg += f"\nBozuk dosya silinmedi, şuraya taşındı:\n{LOAD_STATE['moved_to']}\n"
        backs = [b for b in fx.list_backups(CONFIG_FILE) if b["valid"]]
        if not backs:
            messagebox.showwarning("Yapılandırma", msg + "\nKullanılabilir yedek bulunamadı; kütüphane boş başladı.")
            return
        b = backs[0]
        if messagebox.askyesno("Yedekten geri yükle",
                               msg + f"\nEn son yedek geri yüklensin mi?\n({b['time']:%d.%m.%Y %H:%M} · {b['games']} oyun)"):
            self._restore(b["path"])
        else:
            self.open_backup_window()

    def _restore(self, path):
        try:
            fx.restore_backup(CONFIG_FILE, path)
        except Exception as e:
            messagebox.showerror("Hata", f"Geri yüklenemedi:\n{e}")
            return False
        self.reload_config()
        self.show_toast(f"Yedek geri yüklendi: {len(self.games)} oyun.", timeout=5000)
        return True

    def reload_config(self):
        """Diskteki yapılandırmayı yeniden okuyup arayüze uygular (geri yükleme sonrası)."""
        self.cfg, self.games = load_data()
        self.games.sort(key=lambda g: name_sort_key(g["name"]))
        self.selected = 0 if self.games else -1
        self.view_game_id = None
        self.size_cache.clear()
        self.search_var.set("")
        v = float(self.cfg.get("volume", 0.4))
        self.music.volume = v
        self.vol.set(int(v * 100))
        self.music.shuffle = bool(self.cfg["shuffle"])
        self.shuffle_var.set(self.music.shuffle)
        self.pause_var.set(bool(self.cfg["pause_on_launch"]))
        self.ui_sound.enabled = bool(self.cfg.get("ui_sounds", True))
        mode = "grid" if self.cfg.get("view_mode", "grid") == "grid" else "detail"
        if mode != self.view_mode:
            self.view_mode = mode
            self._apply_view_layout()
        self.refresh_all()
        self._remote_sync()

    def open_backup_window(self):
        win = tk.Toplevel(self)
        win.title("Yapılandırma yedekleri")
        win.geometry("640x520")
        win.minsize(560, 420)
        win.configure(bg=T["bg"])
        win.transient(self)
        tk.Label(win, text="YEDEKLER", bg=T["bg"], fg=T["title"],
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=20, pady=(18, 2))
        tk.Label(win, text=f"Her açılışta yedek alınır, son {fx.BACKUP_KEEP} tanesi tutulur.\n"
                           f"Klasör: {fx.backup_dir(CONFIG_FILE)}\n"
                           "Not: yalnızca ayarlar ve oyun listesi yedeklenir; kapak/video/müzik dosyaları değil.",
                 bg=T["bg"], fg=T["muted"], font=(FONT, 9), justify="left",
                 wraplength=590).pack(anchor="w", padx=20)
        lst = tk.Frame(win, bg=T["panel"])
        lst.pack(fill="both", expand=True, padx=20, pady=12)
        sel = tk.IntVar(value=0)
        backs = []

        def render():
            for w in lst.winfo_children():
                w.destroy()
            backs[:] = fx.list_backups(CONFIG_FILE)
            if not backs:
                tk.Label(lst, text="Henüz yedek yok.", bg=T["panel"], fg=T["muted"],
                         font=(FONT, 12)).pack(anchor="w", padx=14, pady=14)
                return
            sel.set(next((i for i, b in enumerate(backs) if b["valid"]), 0))
            for i, b in enumerate(backs):
                txt = (f"{b['time']:%d.%m.%Y  %H:%M:%S}   ·   "
                       + (f"{b['games']} oyun" if b["valid"] else "BOZUK")
                       + f"   ·   {self.fmt_size(b['size'])}")
                tk.Radiobutton(lst, text=txt, variable=sel, value=i, anchor="w",
                               state="normal" if b["valid"] else "disabled",
                               bg=T["panel"], fg=T["text"], selectcolor=T["bg"],
                               activebackground=T["panel"], activeforeground=T["title"],
                               font=(FONT, 12)).pack(fill="x", padx=10, pady=3)

        def restore():
            if not backs or not backs[sel.get()]["valid"]:
                return
            b = backs[sel.get()]
            if not messagebox.askyesno(
                    "Geri yükle",
                    f"{b['time']:%d.%m.%Y %H:%M} tarihli yedek ({b['games']} oyun) geri yüklensin mi?\n\n"
                    "Şu anki ayarlar da önce yedeklenir; istersen geri dönebilirsin.", parent=win):
                return
            if self._restore(b["path"]):
                win.destroy()

        def backup():
            self.backup_now()
            render()

        def open_dir():
            d = fx.backup_dir(CONFIG_FILE)
            os.makedirs(d, exist_ok=True)
            try:
                os.startfile(d) if sys.platform.startswith("win") else subprocess.Popen(["xdg-open", d])
            except Exception as e:
                messagebox.showerror("Hata", f"Klasör açılamadı:\n{e}", parent=win)

        row = tk.Frame(win, bg=T["bg"])
        row.pack(fill="x", padx=20, pady=(0, 18))
        chip(row, "Geri yükle", restore, primary=True, font=(FONT, 11)).pack(side="left")
        chip(row, "Şimdi yedek al", backup, font=(FONT, 11)).pack(side="left", padx=8)
        chip(row, "Klasörü aç", open_dir, font=(FONT, 11)).pack(side="left")
        chip(row, "Kapat", win.destroy, font=(FONT, 11)).pack(side="right")
        render()

    # ------------------------------------------------------------ TELEFONDAN KUMANDA
    def remote_start(self):
        if self.remote is not None:
            return True
        if not self.cfg.get("remote_token"):
            self.cfg["remote_token"] = fx.new_token()
            self.save()
        srv = fx.RemoteServer(self.cfg["remote_token"], lambda: self.remote_state,
                              lambda: self.remote_games,
                              lambda c, a: self.ui_q.put(("remote", c, a)),
                              int(self.cfg.get("remote_port", 8765)))
        try:
            srv.start()
        except Exception as e:
            self.cfg["remote_enabled"] = False
            self.save()
            messagebox.showerror("Telefon kumandası", f"Sunucu başlatılamadı:\n{e}")
            return False
        self.remote = srv
        self._remote_snapshot()
        return True

    def remote_stop(self, wait=True):
        srv, self.remote = self.remote, None
        if srv is not None:
            srv.stop(wait)

    def _remote_sync(self):
        want = bool(self.cfg.get("remote_enabled"))
        if want and self.remote is None:
            if self.remote_start():
                self.show_toast("Telefon kumandası açık. Bağlanmak için Ayarlar > \"Telefon kumandası bağlantısı / QR\".",
                                timeout=6000)
        elif not want and self.remote is not None:
            self.remote_stop()

    def _remote_tick(self):
        if self.remote is not None:
            try:
                self._remote_snapshot()
            except Exception:
                pass
        self.after(800, self._remote_tick)

    def _remote_snapshot(self):
        """Telefona gidecek durum. Sunucu başka iş parçacığında okuduğu için her seferinde yeni sözlük atanır."""
        g = self.current()
        names = [x["name"] for x in self.games]
        gv = str(hash(tuple(names)))
        if gv != self.remote_gv:
            self.remote_gv, self.remote_games = gv, names
        m = self.music
        track = ""
        if m.ok and m.playing:
            if m.mode == "playlist":
                track = m.current_name()
            elif m.mode == "game":
                track = "Oyun müziği"
        run = ""
        if self.game_running:
            run = next((x["name"] for x in self.games if x["id"] == self.game_running), "")
        self.remote_state = {"game": g["name"] if g else "", "src": (g.get("source") if g else "") or "",
                             "sel": self.selected, "gv": gv, "track": track,
                             "playing": bool(m.ok and m.playing and not m.paused),
                             "vol": int(self.vol.get()), "running": run,
                             "idle": self.idle is not None, "away": self._hidden,
                             "view": self.view_mode, "accent": T["accent"]}

    def _remote_exec(self, c, a):
        """Telefondan gelen komut (arayüz iş parçacığında çalışır)."""
        was_idle = self._idle_touch()   # telefon da boşta ekranını kapatır
        try:
            if c == "volume":
                self._pad_volume(max(-25, min(25, int(a))))
            elif c == "volume_set":
                v = max(0, min(100, int(a)))
                self.vol.set(v)
                self.on_volume(v)
            elif c == "music" and a in ("toggle", "next", "prev"):
                {"toggle": self.music_toggle, "next": self.music_next, "prev": self.music_prev}[a]()
            elif was_idle or self._hidden or self.splash is not None:
                pass   # uyandıran komut tüketilir; oyun açıkken / açılışta gezinme yok
            elif c == "nav" and a in ("up", "down", "left", "right"):
                self.pad_event(a)
            elif c == "back":
                self.pad_event("b")
            elif c == "play":
                if self.pad_menu_open():
                    self.pad_menu_activate()
                else:
                    g = self.current()
                    if g and ex.is_launchable(g):
                        self.start_game()
                    elif g:
                        self.show_toast("Bu oyunun yolu seçilmemiş; bilgisayardan seçmelisin.", timeout=4000)
            elif c == "select":
                self._remote_select(int(a))
        except (TypeError, ValueError):
            pass
        self._remote_snapshot()

    def _remote_select(self, i):
        if not 0 <= i < len(self.games):
            return
        if self.pad_menu_open():
            self.pad_menu_close()
        if self.search_var.get():
            self.search_var.set("")
        self.select(i)
        if self.view_mode == "detail":
            self._scroll_row_into_view(i)

    def show_remote_info(self):
        if self.remote is None:
            if not messagebox.askyesno(
                    "Telefon kumandası",
                    "Telefon kumandası kapalı. Açılsın mı?\n\nAynı Wi-Fi'deki cihazlar, gizli anahtarlı "
                    "bağlantıyla launcher'ı kontrol edebilir."):
                return
            self.cfg["remote_enabled"] = True
            self.save()
            if not self.remote_start():
                return
        url = self.remote.url()
        win = tk.Toplevel(self)
        win.title("Telefon kumandası")
        win.configure(bg=T["bg"])
        win.transient(self)
        win.resizable(False, False)
        tk.Label(win, text="TELEFONDAN KUMANDA", bg=T["bg"], fg=T["title"],
                 font=(FONT, 14, "bold")).pack(anchor="w", padx=24, pady=(20, 4))
        tk.Label(win, text="Telefonla aynı Wi-Fi'ye bağlıyken QR kodu okut ya da bağlantıyı tarayıcıya yaz.\n"
                           "Windows güvenlik duvarı sorarsa \"Özel ağlar\"a izin ver.\n"
                           "Bağlantıdaki anahtarı bilen kumanda edebilir; paylaşma. Sızdığını düşünürsen yenile.",
                 bg=T["bg"], fg=T["muted"], font=(FONT, 10), justify="left",
                 wraplength=460).pack(anchor="w", padx=24)
        qr = fx.qr_image(url, 300)
        if qr is not None:
            self.refs["remote_qr"] = ImageTk.PhotoImage(qr)
            tk.Label(win, image=self.refs["remote_qr"], bg=T["bg"]).pack(pady=14)
        else:
            tk.Label(win, text="QR kodu için:  pip install qrcode", bg=T["bg"], fg=T["muted"],
                     font=(FONT, 10)).pack(pady=14)
        ent = tk.Entry(win, width=52, bg=T["panel"], fg=T["text"], relief="flat",
                       readonlybackground=T["panel"], font=(FONT, 11))
        ent.insert(0, url)
        ent.configure(state="readonly")
        ent.pack(padx=24, ipady=6)

        def copy():
            self.clipboard_clear()
            self.clipboard_append(url)
            self.show_toast("Bağlantı kopyalandı.", timeout=2500)

        def renew():
            if not messagebox.askyesno("Anahtarı yenile",
                                       "Eski bağlantı geçersiz olur; telefonda yenisini açman gerekir. Devam?",
                                       parent=win):
                return
            self.remote_stop()
            self.cfg["remote_token"] = fx.new_token()
            self.save()
            win.destroy()
            if self.remote_start():
                self.show_remote_info()

        row = tk.Frame(win, bg=T["bg"])
        row.pack(fill="x", padx=24, pady=(14, 20))
        chip(row, "Kopyala", copy, primary=True, font=(FONT, 11)).pack(side="left")
        chip(row, "Anahtarı yenile", renew, font=(FONT, 11)).pack(side="left", padx=8)
        chip(row, "Kapat", win.destroy, font=(FONT, 11)).pack(side="right")

    # ------------------------------------------------------------ BOŞTA KALMA EKRANI
    def _idle_set(self):
        self.cfg["idle_minutes"] = int(self.idle_var.get())
        self.save()
        self._idle_touch()

    def _idle_motion(self, e):
        p = (e.x_root, e.y_root)
        if abs(p[0] - self._idle_mouse[0]) + abs(p[1] - self._idle_mouse[1]) < 6:
            return   # fare titremesi uyandırmasın
        self._idle_mouse = p
        st = self.idle
        if st is None or time.time() - st["t0"] >= st["grace"]:
            self._idle_touch()

    def _idle_touch(self):
        """Etkinliği kaydeder. Boşta ekranı açıksa kapatır ve True döner (o girdi tüketilmeli)."""
        self._idle_last = time.time()
        if self.idle is not None:
            self._idle_stop()
            return True
        return False

    def _idle_ok(self):
        if self.splash is not None or self._hidden or self.game_running or self.pad_menu_open():
            return False
        try:
            if self.state() not in ("normal", "zoomed"):
                return False
            for w in self.winfo_children():   # açık pencere / iletişim kutusu varken başlama
                if isinstance(w, tk.Toplevel) and w.winfo_viewable():
                    return False
        except tk.TclError:
            return False
        return True

    def _idle_check(self):
        try:
            mins = int(self.cfg.get("idle_minutes", 3) or 0)
            if mins > 0 and self.idle is None and self._idle_ok() \
                    and time.time() - self._idle_last >= mins * 60:
                self._idle_start()
        except Exception:
            pass
        self.after(2000, self._idle_check)

    def _idle_start(self, preview=False):
        """Saat + yavaş kayan kapaklar. Siyah zemin ve hareket, OLED'de yanmayı önler."""
        if self.idle is not None or self.splash is not None:
            return
        self.update_idletasks()
        W, H = self.winfo_width(), self.winfo_height()
        if W < 200 or H < 200:
            return
        try:
            prev_focus = self.focus_get()
        except Exception:
            prev_focus = None
        sp = tk.Canvas(self, bg="#000000", highlightthickness=0, bd=0, cursor="none")
        sp.place(x=0, y=0, relwidth=1, relheight=1)
        tk.Misc.lift(sp)
        sp.focus_set()

        pool = [g for g in self.games if find_asset(g["id"], "kapak")]
        random.shuffle(pool)
        pool = pool[:14]
        ch = max(150, min(380, int(H * 0.24)))
        cw = int(ch / 1.4)
        gap = max(20, cw // 8)
        photos = {}

        def photo(g):
            if g["id"] not in photos:
                base = get_image(g, "kapak", (cw, ch)).convert("RGB")
                dim = ImageEnhance.Brightness(base).enhance(0.5).convert("RGBA")
                photos[g["id"]] = ImageTk.PhotoImage(round_corners(dim, 14))
            return photos[g["id"]]

        lanes = []
        if pool:
            n = -(-(W + cw + gap) // (cw + gap)) + 1
            span = n * (cw + gap)
            for li, y in enumerate((int(H * 0.05), int(H * 0.95) - ch)):
                items = []
                for j in range(n):
                    g = pool[(j + li * 5) % len(pool)]
                    x = float(j * (cw + gap) - li * (cw // 2))
                    items.append({"id": sp.create_image(x, y, image=photo(g), anchor="nw"), "x": x})
                lanes.append({"y": y, "v": (14 + 7 * li) * (1 if li % 2 == 0 else -1),
                              "span": span, "items": items})

        size = max(40, int(min(W, H) * 0.085))
        f_time = tkfont.Font(family=FONT, size=size, weight="bold")
        f_date = tkfont.Font(family=FONT, size=max(14, size // 4))
        f_small = tkfont.Font(family=FONT, size=max(11, size // 6))
        dark = "#000000"
        t_id = sp.create_text(W / 2, H / 2, text="", font=f_time, fill=blend(dark, "#ffffff", 0.62))
        d_id = sp.create_text(W / 2, H / 2, text="", font=f_date, fill=blend(dark, "#ffffff", 0.38))
        m_id = sp.create_text(W / 2, H / 2, text="", font=f_small, width=int(W * 0.8), justify="center",
                              fill=blend(dark, T["accent"], 0.7))
        self.idle = {"canvas": sp, "W": W, "H": H, "cw": cw, "lanes": lanes, "ids": (t_id, d_id, m_id),
                     "fonts": (f_time, f_date, f_small), "ls": f_time.metrics("linespace"),
                     "ds": f_date.metrics("linespace"), "t": time.perf_counter(), "t0": time.time(),
                     "grace": 3.0 if preview else 0.6, "txt": None, "job": None, "focus": prev_focus,
                     "phase": random.random() * 100}
        self._idle_frame()

    def _idle_frame(self):
        st = self.idle
        if st is None:
            return
        st["job"] = None
        sp, W, H = st["canvas"], st["W"], st["H"]
        try:
            if self.winfo_width() != W or self.winfo_height() != H:   # pencere boyutu değişti
                self._idle_stop()
                self._idle_start()
                return
            import math
            now = time.perf_counter()
            dt = min(0.25, now - st["t"])
            st["t"] = now
            for ln in st["lanes"]:
                v, span, y = ln["v"], ln["span"], ln["y"]
                for it in ln["items"]:
                    x = it["x"] + v * dt
                    if v > 0 and x > W:
                        x -= span
                    elif v < 0 and x < -st["cw"]:
                        x += span
                    it["x"] = x
                    sp.coords(it["id"], x, y)
            # saat çok yavaş gezinir (piksel kaydırma)
            tt = time.time() + st["phase"]
            cx = W / 2 + W * 0.06 * math.sin(tt * 2 * math.pi / 97)
            cy = H / 2 + H * 0.02 * math.cos(tt * 2 * math.pi / 131)
            t_id, d_id, m_id = st["ids"]
            ls, ds = st["ls"], st["ds"]
            sp.coords(t_id, cx, cy)
            sp.coords(d_id, cx, cy + ls * 0.6 + ds * 0.4)
            sp.coords(m_id, cx, cy + ls * 0.6 + ds * 1.9)
            n = datetime.now()
            m = self.music
            track = ""
            if m.ok and m.playing and not m.paused:
                track = "♪ " + (m.current_name() if m.mode == "playlist" else "Oyun müziği")
            txt = (n.strftime("%H:%M"), fx.date_tr(n), track)
            if txt != st["txt"]:
                st["txt"] = txt
                sp.itemconfigure(t_id, text=txt[0])
                sp.itemconfigure(d_id, text=txt[1])
                sp.itemconfigure(m_id, text=txt[2])
        except tk.TclError:
            self.idle = None
            return
        st["job"] = self.after(40, self._idle_frame)

    def _idle_stop(self):
        st, self.idle = self.idle, None
        if not st:
            return
        if st.get("job"):
            try:
                self.after_cancel(st["job"])
            except Exception:
                pass
        try:
            st["canvas"].destroy()
        except tk.TclError:
            pass
        try:
            f = st.get("focus")
            if f is not None and f.winfo_exists():
                f.focus_set()
            elif self.view_mode == "grid":
                self.grid_cv.focus_set()
        except Exception:
            pass


def _write_error(text):
    try:
        with open(os.path.join(BASE_DIR, "launcher_error.log"), "w", encoding="utf-8") as f:
            f.write(text)
    except OSError:
        pass


def _show_error(text):
    try:
        import tkinter as _tk
        from tkinter import messagebox as _mb
        _r = _tk.Tk()
        _r.withdraw()
        _mb.showerror("Launcher hatası", text[-1500:] + "\n\nTam kayıt: launcher_error.log", parent=_r)
        _r.destroy()
    except Exception:
        pass


_TEK_MUTEX = None


def _tek_ornek():
    """Windows adlandırılmış mutex ile yalnızca tek launcher çalışır. Yeni kopya False döner."""
    global _TEK_MUTEX
    if not ex.IS_WIN:
        return True
    import ctypes
    k = ctypes.WinDLL("kernel32", use_last_error=True)
    k.CreateMutexW.restype = ctypes.c_void_p
    _TEK_MUTEX = k.CreateMutexW(None, False, "MultiLibraryLauncher_Tek")
    return ctypes.get_last_error() != 183          # 183 = ERROR_ALREADY_EXISTS


if __name__ == "__main__":
    import traceback as _tb
    if not _tek_ornek():
        # çalışan kopyaya "göster" sinyali ver, bu kopya kendini kapatsın
        try:
            with open(os.path.join(BASE_DIR, "goster.flag"), "w", encoding="utf-8") as f:
                f.write("kol" if "--kol" in sys.argv else "klavye")
        except OSError:
            pass
        sys.exit(0)
    if ex.IS_WIN:
        # DPI ölçeklemesini kapat: Windows monitör koordinatlarını gerçek piksel olarak versin
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(2)
        except Exception:
            pass
    try:
        _app = Launcher()
        _app.report_callback_exception = lambda exc, val, tb: (
            _write_error("".join(_tb.format_exception(exc, val, tb))))
        _app.mainloop()
    except Exception:
        _err = _tb.format_exc()
        _write_error(_err)
        _show_error(_err)
        raise