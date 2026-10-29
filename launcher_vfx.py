"""Launcher için görsel efektler (konsol arayüzü hissi).

İçerik
  * Yazı tipi:     Inter (exe'nin yanındaki "fonts" klasörü) > Segoe UI Variable > Segoe UI
  * TileArt:       seçili kapak için eğim (perspektif), büyüme, parıltı, gölge, vurgu çerçevesi
  * hero_strip:    ızgara üstündeki geniş "hero" şeridinin arka planı
  * glass_image:   cam efekti (arkadaki görseli bulanıklaştırıp yarı saydam zemin)
  * VisualsMixin:  Launcher'a karışan Tk tarafı (animasyon döngüleri, hero, crossfade,
                   cam menü, başlatma geçişi)

launcher.py bu modülü içe aktarıp vfx.init(...) ile kendi yardımcılarını (T, get_image, ...) verir.
"""
import math
import os
import time
from functools import lru_cache

import tkinter as tk
from tkinter import font as tkfont
from PIL import Image, ImageChops, ImageColor, ImageDraw, ImageEnhance, ImageFilter, ImageFont, ImageOps, ImageTk

try:  # Pillow 9.1+ / eski sürümler
    _BICUBIC = Image.Resampling.BICUBIC
    _BILINEAR = Image.Resampling.BILINEAR
    _LANCZOS = Image.Resampling.LANCZOS
    _PERSPECTIVE = Image.Transform.PERSPECTIVE
except AttributeError:  # pragma: no cover
    _BICUBIC, _BILINEAR, _LANCZOS, _PERSPECTIVE = Image.BICUBIC, Image.BILINEAR, Image.LANCZOS, Image.PERSPECTIVE


# ====================================================================== AYARLAR
MAXS = 1.06          # seçili kapağın ulaştığı ölçek (1.00 -> 1.06)
PAD = 56             # kapak çevresinde parıltı/gölge için bırakılan pay (px)
BORDER = 3           # perspektif dönüşümünde kenar yumuşatma payı
LIFT = 7             # seçili kapak hafifçe yukarı kalkar (px)
MAX_ANGLE = math.radians(8.0)   # en fazla eğim (çok hafif)
CAM_D = 900.0        # perspektif uzaklığı: büyüdükçe etki azalır
XFADE_MS = 260       # çapraz solma süresi
LAUNCH_GROW = 0.60   # başlatma geçişinde kapağın ekranı kaplama süresi (sn)
LAUNCH_HOLD = 0.55   # kapak tam ekranda kaldığı süre (sn)
LAUNCH_BACK = 0.50   # kapağın eski yerine dönme süresi (sn)
LAUNCH_MIN = 1.2     # başlatma ekranının en az görünme süresi (sn)
LAUNCH_MAX = 6.0     # oyun algılanmazsa en geç bu kadar sonra kapanır (sn)


class _Ctx:
    """launcher.py'nin verdiği yardımcılar (T, get_image, find_asset, ...)."""


ctx = _Ctx()


def init(**kw):
    for k, v in kw.items():
        setattr(ctx, k, v)


# ====================================================================== YAZI TİPİ
FONT = "Arial"
_PIL_FONTS = {}     # {"regular": yol, "bold": yol}


def _win_fonts_dirs():
    out = []
    win = os.environ.get("WINDIR") or os.environ.get("SystemRoot") or r"C:\Windows"
    out.append(os.path.join(win, "Fonts"))
    local = os.environ.get("LOCALAPPDATA")
    if local:
        out.append(os.path.join(local, "Microsoft", "Windows", "Fonts"))
    return out


def setup_fonts(base_dir):
    """Yazı tipini seçer ve FONT'a yazar. Tk açılmadan önce çağrılmalı (Windows'ta
    exe'nin yanındaki Inter dosyaları yalnızca bu işlem için yüklenir, sisteme kurulmaz)."""
    global FONT
    inter = []
    for d in (os.path.join(base_dir, "fonts"), os.path.join(base_dir, "assets", "fonts"), base_dir):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            lf = f.lower()
            if lf.startswith("inter") and lf.endswith((".ttf", ".otf")) and "variable" not in lf:
                inter.append(os.path.join(d, f))
    is_win = os.name == "nt"
    registered = False
    if is_win and inter:
        try:
            import ctypes
            for p in inter:
                if ctypes.windll.gdi32.AddFontResourceExW(p, 0x10, 0):   # FR_PRIVATE
                    registered = True
        except Exception:
            registered = False
    sys_inter = False
    if is_win and not registered:
        for d in _win_fonts_dirs():
            try:
                if any(f.lower().startswith("inter") and "variable" not in f.lower() for f in os.listdir(d)):
                    sys_inter = True
                    break
            except OSError:
                pass
    if registered or sys_inter:
        FONT = "Inter"
    elif is_win:
        win_fonts = _win_fonts_dirs()[0]
        FONT = "Segoe UI Variable Text" if os.path.exists(os.path.join(win_fonts, "SegUIVar.ttf")) else "Segoe UI"
    else:
        FONT = "Arial"
    # PIL tarafı (yer tutucu kapaklar) için dosya yolları
    for p in inter:
        lp = os.path.basename(p).lower()
        if "bold" in lp and "semi" not in lp and "extra" not in lp:
            _PIL_FONTS.setdefault("bold", p)
        elif "regular" in lp:
            _PIL_FONTS.setdefault("regular", p)
    return FONT


@lru_cache(maxsize=32)
def pil_font(size, bold=False):
    size = max(8, int(size))
    cands = []
    if bold and _PIL_FONTS.get("bold"):
        cands.append(_PIL_FONTS["bold"])
    if _PIL_FONTS.get("regular"):
        cands.append(_PIL_FONTS["regular"])
    cands += (["segoeuib.ttf", "arialbd.ttf", "DejaVuSans-Bold.ttf"] if bold
              else ["segoeui.ttf", "arial.ttf", "DejaVuSans.ttf"])
    for c in cands:
        try:
            return ImageFont.truetype(c, size)
        except Exception:
            continue
    try:
        return ImageFont.load_default(size)
    except TypeError:  # eski Pillow
        return ImageFont.load_default()


# ====================================================================== GÖRSEL YARDIMCILAR
@lru_cache(maxsize=64)
def rr_mask(size, radius, inset=0, ss=3):
    """Kenarları yumuşatılmış (3x süperörnekleme) yuvarlak köşeli 'L' maske."""
    w, h = size
    big = Image.new("L", (w * ss, h * ss), 0)
    r = max(0.0, radius - inset) * ss
    ins = inset * ss
    ImageDraw.Draw(big).rounded_rectangle([ins, ins, w * ss - 1 - ins, h * ss - 1 - ins],
                                          radius=r, fill=255)
    return big.resize((w, h), _LANCZOS)


def _solve(a, b):
    """8x8 doğrusal sistem (Gauss eleme); numpy gerekmez."""
    n = len(b)
    m = [row[:] + [b[i]] for i, row in enumerate(a)]
    for c in range(n):
        piv = max(range(c, n), key=lambda r: abs(m[r][c]))
        if abs(m[piv][c]) < 1e-12:
            raise ValueError("tekil")
        m[c], m[piv] = m[piv], m[c]
        pv = m[c][c]
        m[c] = [v / pv for v in m[c]]
        for r in range(n):
            if r != c and m[r][c]:
                f = m[r][c]
                m[r] = [rv - f * cv for rv, cv in zip(m[r], m[c])]
    return [m[i][n] for i in range(n)]


def persp_coeffs(dst, src):
    """PIL PERSPECTIVE katsayıları: çıktı (dst) köşelerini kaynak (src) köşelerine eşler."""
    a, b = [], []
    for (X, Y), (x, y) in zip(dst, src):
        a.append([X, Y, 1, 0, 0, 0, -x * X, -x * Y])
        b.append(x)
        a.append([0, 0, 0, X, Y, 1, -y * X, -y * Y])
        b.append(y)
    return _solve(a, b)


def smooth(k):
    k = max(0.0, min(1.0, k))
    return k * k * k * (k * (6 * k - 15) + 10)


# ====================================================================== KAPAK: EĞİM + BÜYÜME + PARILTI
class TileArt:
    """Tek bir kapak için çizici. render(p, tx, ty) -> RGBA (tw+2*PAD, th+2*PAD)

    p  : seçilme ilerlemesi 0..1 (ölçek 1.00->1.06, parlaklık, parıltı, gölge, çerçeve)
    tx : -1..1 yatay eğim (imleç sağdaysa sağ kenar uzaklaşır), ty: dikey
    """

    def __init__(self, cover_rgb, tw, th, radius=18):
        self.tw, self.th = int(tw), int(th)
        self.hw, self.hh = cover_rgb.size            # yüksek çözünürlük = tw*MAXS
        self.cw, self.ch = self.tw + 2 * PAD, self.th + 2 * PAD
        self.bright = cover_rgb
        self.dim = Image.blend(Image.new("RGB", cover_rgb.size, (0, 0, 0)), cover_rgb, 0.62)
        r = radius * MAXS
        self.mask = rr_mask((self.hw, self.hh), r)
        inner = rr_mask((self.hw, self.hh), r, inset=4)
        self.ring_alpha = ImageChops.subtract(self.mask, inner)
        self.white = Image.new("RGB", cover_rgb.size, (255, 255, 255))
        g = ImageOps.invert(Image.radial_gradient("L")).resize((self.hw * 2, self.hh * 2), _BILINEAR)
        self.gloss = g.point([int((v / 255.0) ** 1.7 * 255) for v in range(256)])
        self.accent = (99, 102, 241)
        self.ring_img = None
        self.set_accent("#6366f1")

    def set_accent(self, color):
        try:
            self.accent = ImageColor.getrgb(color)[:3]
        except Exception:
            pass
        self.ring_img = Image.new("RGBA", (self.hw, self.hh), self.accent + (255,))

    # -- 3B -> 2B: köşe noktaları
    def _quad(self, s, tx, ty, p):
        u = self.tw * s / self.hw
        hxp, hyp = (self.hw / 2 + BORDER) * u, (self.hh / 2 + BORDER) * u
        ay, ax = tx * MAX_ANGLE, ty * MAX_ANGLE
        cx, cy = self.cw / 2.0, self.ch / 2.0 - LIFT * p
        pts = []
        for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
            x, y = sx * hxp, sy * hyp
            z = x * math.sin(ay) + y * math.sin(ax)
            k = CAM_D / (CAM_D + z)
            pts.append((cx + x * math.cos(ay) * k, cy + y * math.cos(ax) * k))
        return pts

    def _soft(self, quad, off, grow, sigma, strength):
        qs = 4
        gw, gh = self.cw // qs, self.ch // qs
        mx = sum(p[0] for p in quad) / 4.0
        my = sum(p[1] for p in quad) / 4.0
        pts = [((mx + (X - mx) * grow + off[0]) / qs, (my + (Y - my) * grow + off[1]) / qs) for X, Y in quad]
        m = Image.new("L", (gw, gh), 0)
        ImageDraw.Draw(m).polygon(pts, fill=255)
        m = m.filter(ImageFilter.GaussianBlur(sigma / qs))
        m = m.point([int(v * strength) for v in range(256)])
        return m.resize((self.cw, self.ch), _BILINEAR)

    def render(self, p, tx=0.0, ty=0.0):
        p = max(0.0, min(1.0, p))
        tx, ty = max(-1.0, min(1.0, tx)), max(-1.0, min(1.0, ty))
        s = 1.0 + (MAXS - 1.0) * p
        hw, hh = self.hw, self.hh
        if p <= 0.0:
            rgb = self.dim
        elif p >= 1.0:
            rgb = self.bright
        else:
            rgb = Image.blend(self.dim, self.bright, p)
        if p > 0.02:   # parıltı: imlecin/çubuğun olduğu yerde hafif ışık lekesi
            mag = min(1.0, math.hypot(tx, ty))
            k = p * (0.14 + 0.24 * mag)
            ox = int(hw * 0.5 - tx * 0.5 * hw)
            oy = int(hh * 0.5 - ty * 0.5 * hh)
            gm = self.gloss.crop((ox, oy, ox + hw, oy + hh)).point([int(v * k) for v in range(256)])
            rgb = Image.composite(self.white, rgb, gm)
        card = rgb.convert("RGBA")
        card.putalpha(self.mask)
        if p > 0.01:
            ring = self.ring_alpha.point([int(v * p) for v in range(256)])
            card.paste(self.ring_img, (0, 0), ring)
        sw, sh = hw + 2 * BORDER, hh + 2 * BORDER
        src = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
        src.paste(card, (BORDER, BORDER))
        quad = self._quad(s, tx, ty, p)
        coeffs = persp_coeffs(quad, [(0, 0), (sw, 0), (sw, sh), (0, sh)])
        out = src.transform((self.cw, self.ch), _PERSPECTIVE, coeffs, _BILINEAR)
        if p > 0.01:
            base = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
            glow = Image.new("RGBA", (self.cw, self.ch), self.accent + (0,))
            glow.putalpha(self._soft(quad, (-tx * 12, -ty * 12 + 6), 1.03, 14, 0.62 * p))
            shadow = Image.new("RGBA", (self.cw, self.ch), (0, 0, 0, 0))
            shadow.putalpha(self._soft(quad, (tx * 8, 14 * p + ty * 6), 1.0, 10, 0.80 * p))
            base = Image.alpha_composite(base, glow)
            base = Image.alpha_composite(base, shadow)
            out = Image.alpha_composite(base, out)
        return out


# ====================================================================== HERO ŞERİDİ
def hero_strip(base_rgb, bg_hex="#000000"):
    """Geniş arka plan görselini sol ve alttan siyaha eriterek hero şeridi yapar."""
    w, h = base_rgb.size
    base = ImageEnhance.Brightness(base_rgb).enhance(0.85)
    solid = Image.new("RGB", (w, h), ImageColor.getrgb(bg_hex)[:3])
    vert = Image.linear_gradient("L").resize((w, h), _BILINEAR)
    vmask = vert.point(lambda v: max(0, min(255, int((v - 120) * 255 / 135))))
    img = Image.composite(solid, base, vmask)
    horiz = ImageOps.invert(Image.linear_gradient("L").rotate(90)).resize((w, h), _BILINEAR)
    hmask = horiz.point(lambda v: int(max(0, min(255, (v - 70) * 1.5)) * 0.9))
    return Image.composite(solid, img, hmask)


# ====================================================================== CAM EFEKTİ
def glass_image(backdrop, box, radius=20, blur=22, tint=(10, 12, 26), tint_a=135,
                border_a=46, sheen=0.0, opacity=0.9):
    """backdrop (RGB) üzerindeki box bölgesini bulanıklaştırıp koyu yarı saydam zemin ekler.
    Dönen RGBA resim kutunun boyutundadır (köşeler yuvarlak)."""
    x0, y0, x1, y1 = [int(v) for v in box]
    w, h = max(2, x1 - x0), max(2, y1 - y0)
    m = int(blur * 2)
    region = backdrop.crop((x0 - m, y0 - m, x1 + m, y1 + m)).convert("RGB")
    rw, rh = region.size
    small = region.resize((max(2, rw // 2), max(2, rh // 2)), _BILINEAR).filter(ImageFilter.GaussianBlur(blur / 2.0))
    soft = small.resize((rw, rh), _BICUBIC).crop((m, m, m + w, m + h))
    soft = ImageEnhance.Color(soft).enhance(1.35)
    soft = ImageEnhance.Brightness(soft).enhance(0.55)   # soluk gri görünümü azaltmak için koyulaştır
    glass = Image.blend(soft, Image.new("RGB", (w, h), tint), tint_a / 255.0)
    if sheen > 0:   # üstte ince ışık yansıması
        top = ImageOps.invert(Image.linear_gradient("L")).resize((w, h), _BILINEAR)
        top = top.point(lambda v: int(max(0, v - 128) * 2 * sheen))
        glass = Image.composite(Image.new("RGB", (w, h), (255, 255, 255)), glass, top)
    rgba = glass.convert("RGBA")
    mask = rr_mask((w, h), radius)
    # yarı saydam: panelin altındaki arka plan hafifçe görünür
    rgba.putalpha(mask.point(lambda v: int(v * opacity)))
    ring =ImageChops.subtract(mask, rr_mask((w, h), radius, inset=1)).point(
        [int(v * border_a / 255.0) for v in range(256)])
    rgba.paste(Image.new("RGBA", (w, h), (255, 255, 255, 255)), (0, 0), ring)
    return rgba


# ====================================================================== BAŞLATMA GEÇİŞİ KARESİ
def _corner_alpha(w, h, r):
    """Büyük boyutlarda bile ucuz: yalnızca dört köşeyi yuvarlayan 'L' maske."""
    r = max(1, int(math.ceil(r)))
    r = min(r, w // 2, h // 2)
    q = rr_mask((2 * r + 2, 2 * r + 2), r, ss=4)
    c = r + 1
    m = Image.new("L", (w, h), 255)
    m.paste(q.crop((0, 0, c, c)), (0, 0))
    m.paste(q.crop((c, 0, 2 * c, c)), (w - c, 0))
    m.paste(q.crop((0, c, c, 2 * c)), (0, h - c))
    m.paste(q.crop((c, c, 2 * c, 2 * c)), (w - c, h - c))
    return m


def launch_frame(src_rgb, rect, radius, dark):
    """src_rgb kapağını rect=(x,y,w,h) boyutuna sığdırır; radius>0 ise köşeleri yuvarlar
    (köşeler siyah kalır, zemin siyah olduğundan RGB yeterli), dark (0..1) siyaha doğru karartır.
    (img, (x, y)) döner."""
    x, y, w, h = rect
    w, h = max(4, int(w)), max(4, int(h))
    im = ImageOps.fit(src_rgb, (w, h), _BILINEAR)
    if dark > 0.01:
        f = 1.0 - min(1.0, dark)
        im = im.point([int(v * f) for v in range(256)] * 3)
    if radius > 0.6:
        im = Image.composite(im, Image.new("RGB", (w, h), (0, 0, 0)), _corner_alpha(w, h, radius))
    return im, (int(x), int(y))


# ====================================================================== TK TARAFI
class VisualsMixin:
    """Launcher sınıfına karışır. Tüm durum fx_init() içinde kurulur."""

    # ------------------------------------------------------------ KURULUM
    def fx_init(self):
        self._tfx = {}
        self._tfx_job = None
        self._tfx_last = 0.0
        self._fx_snap = False
        self._tilt_t = (0.0, 0.0)
        self._pad_stick_on = False
        self._xf_tok = {}
        self._xf_cur = {}
        self._hero = {"bg": None, "key": None, "size": None, "btn": None, "pil": None}
        self._hero_h = 0
        self._hero_job = None
        self._detail_pil = None
        self._detail_xf_from = None
        self._detail_cover_rect = None
        self._bd = None
        self.launching = None

    def fx_reload(self):
        """Ayar değişti: ızgarayı yeni ayara göre yeniden kur."""
        self.fx_clear()
        if self.view_mode == "grid":
            self.grid_rebuild()

    def fx_on(self):
        return self.view_mode == "grid" and bool(self.cfg.get("fx_motion", True))

    def _xf_on(self):
        return bool(self.cfg.get("fx_motion", True))

    # ------------------------------------------------------------ KAPAK ANİMASYONU
    def fx_clear(self):
        self._tfx = {}
        if self._tfx_job:
            try:
                self.after_cancel(self._tfx_job)
            except Exception:
                pass
            self._tfx_job = None

    def fx_select(self, i, sel):
        """Izgara karosu seçildi/bırakıldı: büyüme animasyonunu başlatır."""
        t = self.grid_tiles.get(i)
        if not t or not self.grid_m:
            return
        e = self._tfx.get(i)
        if sel:
            if e is None:
                e = self.fx_create(i, snap=self._fx_snap)
            if e is None:
                return
            e["tp"] = 1.0
            if self._fx_snap:
                e["p"] = 1.0
                self.fx_render(i)
        elif e is not None:
            e["tp"] = 0.0
            if self._fx_snap:
                self._fx_restore(i)
                return
        self.fx_kick()

    def fx_create(self, i, snap=False):
        t, m = self.grid_tiles.get(i), self.grid_m
        if not t or not m:
            return None
        g = self.games[i]
        tw, th = m["tw"], m["th"]
        hw, hh = int(round(tw * MAXS)), int(round(th * MAXS))
        try:
            cover = ctx.get_image(g, "kapak", (hw, hh)).convert("RGB")
            art = TileArt(cover, tw, th)
            art.set_accent(ctx.T["accent"])
        except Exception:
            return None
        e = {"art": art, "p": 1.0 if snap else 0.0, "tp": 0.0, "tx": 0.0, "ty": 0.0, "photo": None}
        self._tfx[i] = e
        try:
            self.grid_cv.itemconfigure(t["img"], anchor="center")
        except tk.TclError:
            pass
        self.fx_render(i)
        return e

    def fx_render(self, i):
        e, t, m = self._tfx.get(i), self.grid_tiles.get(i), self.grid_m
        if not e or not t or not m:
            return
        try:
            img = e["art"].render(e["p"], e["tx"], e["ty"])
            e["photo"] = ImageTk.PhotoImage(img)
            cx = t["x"] + m["tw"] / 2.0
            cy = t["y"] + m["th"] / 2.0 - LIFT * e["p"]
            self.grid_cv.itemconfigure(t["img"], image=e["photo"])
            self.grid_cv.coords(t["img"], cx, cy)
        except tk.TclError:
            pass

    def _fx_restore(self, i):
        """Animasyon bitti: karoyu hafif statik görsele döndür."""
        e, t = self._tfx.pop(i, None), self.grid_tiles.get(i)
        if t:
            try:
                self.grid_cv.itemconfigure(t["img"], image=t["pn"], anchor="nw")
                self.grid_cv.coords(t["img"], t["x"], t["y"])
            except tk.TclError:
                pass

    def fx_kick(self):
        if self._tfx_job is None:
            self._tfx_last = 0.0
            self._tfx_job = self.after(1, self.fx_tick)

    def fx_tick(self):
        self._tfx_job = None
        now = time.perf_counter()
        dt = min(0.05, now - self._tfx_last) if self._tfx_last else 0.016
        self._tfx_last = now
        kp = 1.0 - math.exp(-dt / 0.075)    # büyüme / solma
        kt = 1.0 - math.exp(-dt / 0.090)    # eğim
        active = False
        for i, e in list(self._tfx.items()):
            if i not in self.grid_tiles:
                self._tfx.pop(i, None)
                continue
            ttx, tty = self._tilt_t if e["tp"] > 0.5 else (0.0, 0.0)
            dp, dx, dy = e["tp"] - e["p"], ttx - e["tx"], tty - e["ty"]
            if abs(dp) < 0.002 and abs(dx) < 0.003 and abs(dy) < 0.003:
                changed = (dp, dx, dy) != (0.0, 0.0, 0.0)
                e["p"], e["tx"], e["ty"] = e["tp"], ttx, tty
                if e["tp"] <= 0.0:
                    self._fx_restore(i)       # bırakılan karo hafif statik görsele döner
                elif changed:
                    self.fx_render(i)
                continue
            e["p"] += dp * kp
            e["tx"] += dx * kt
            e["ty"] += dy * kt
            self.fx_render(i)
            active = True
        if active:
            self._tfx_job = self.after(12, self.fx_tick)
        else:
            self._tfx_last = 0.0

    def fx_set_tilt(self, tx, ty):
        tx, ty = max(-1.0, min(1.0, tx)), max(-1.0, min(1.0, ty))
        if abs(tx - self._tilt_t[0]) < 0.004 and abs(ty - self._tilt_t[1]) < 0.004:
            return
        self._tilt_t = (tx, ty)
        if any(e["tp"] > 0.5 for e in self._tfx.values()):
            self.fx_kick()

    def fx_accent(self):
        """Vurgu rengi değişti: seçili kapağın çerçeve ve parıltısını yenile."""
        for i, e in list(self._tfx.items()):
            e["art"].set_accent(ctx.T["accent"])
            if e["tp"] > 0.5:
                self.fx_render(i)

    def _grid_motion(self, e):
        if not self.fx_on():
            return
        t, m = self.grid_tiles.get(self.selected), self.grid_m
        if not t or not m:
            return
        gc = self.grid_cv
        px, py = gc.canvasx(e.x), gc.canvasy(e.y)
        nx = (px - (t["x"] + m["tw"] / 2.0)) / (m["tw"] / 2.0)
        ny = (py - (t["y"] + m["th"] / 2.0)) / (m["th"] / 2.0)
        if abs(nx) <= 1.0 and abs(ny) <= 1.0:
            self.fx_set_tilt(nx, ny)
        else:
            self.fx_set_tilt(0.0, 0.0)

    def _grid_leave(self, e=None):
        self.fx_set_tilt(0.0, 0.0)

    def fx_pad_tilt(self):
        """Kumanda çubuğu: sağ çubuk (yoksa sol çubuğun yumuşatılmış hâli) kapağı eğer."""
        st = getattr(self.pad, "sticks", None)
        if not st or not self.fx_on():
            return
        rx, ry, lx, ly = st
        if math.hypot(rx, ry) > 0.22:
            self._pad_stick_on = True
            self.fx_set_tilt(rx, -ry)
        elif math.hypot(lx, ly) > 0.22:
            self._pad_stick_on = True
            self.fx_set_tilt(lx * 0.7, -ly * 0.7)
        elif self._pad_stick_on:
            self._pad_stick_on = False
            self.fx_set_tilt(0.0, 0.0)

    # ------------------------------------------------------------ ÇAPRAZ SOLMA
    def xfade_start(self, key, canvas, item, old, new, post=None, ms=XFADE_MS):
        """item'in görselini old -> new olarak ms sürede çapraz soldurur. old/new aynı boyutta
        RGB PIL resmi; post (ops.) kareyi ekrana basmadan önce dönüştürür (örn. büyütme)."""
        tok = self._xf_tok.get(key, 0) + 1
        self._xf_tok[key] = tok
        t0 = time.perf_counter()

        def step():
            if self._xf_tok.get(key) != tok:
                return
            try:
                if canvas.type(item) is None:
                    return
            except tk.TclError:
                return
            k = min(1.0, (time.perf_counter() - t0) * 1000.0 / ms)
            e = k * k * (3 - 2 * k)
            frame = new if k >= 1.0 else (old if k <= 0.0 else Image.blend(old, new, e))
            self._xf_cur[key] = frame
            img = post(frame) if post else frame
            photo = ImageTk.PhotoImage(img)
            self.refs["xf_" + key] = photo
            try:
                canvas.itemconfigure(item, image=photo)
            except tk.TclError:
                return
            if k < 1.0:
                self.after(16, step)

        step()

    # ------------------------------------------------------------ YEDEK ARKA PLAN (CAM İÇİN)
    def _backdrop(self, w, h):
        """Cam panellerin arkasında bulanıklaşacak görsel: seçili oyunun arka planı (yoksa kapağı)."""
        g = self.current()
        kind = next((k for k in ("arkaplan", "kapak") if g and ctx.find_asset(g["id"], k)), None)
        path = ctx.find_asset(g["id"], kind) if kind else None
        try:
            stamp = os.path.getmtime(path) if path else None
        except OSError:
            stamp = None
        dim = float(self.cfg.get("bg_dim", 0.36))      # Ayarlar > Genel parlaklık ile değişir
        key = (g["id"] if g else None, kind, stamp, w, h, dim)
        if self._bd and self._bd[0] == key:
            return self._bd[1]
        if not kind:
            img = Image.new("RGB", (w, h), (0, 0, 0))
        else:
            small = ctx.get_image(g, kind, (max(8, w // 3), max(8, h // 3))).convert("RGB")
            img = ImageEnhance.Brightness(small).enhance(min(1.0, dim * 1.4)).resize((w, h), _BICUBIC)
        self._bd = (key, img)
        return img

    # ------------------------------------------------------------ HERO ŞERİDİ
    def hero_build(self, parent):
        self.hero_cv = tk.Canvas(parent, bg=ctx.T["bg"], highlightthickness=0, bd=0, height=10)
        self.hero_cv.bind("<Configure>", lambda e: self.hero_draw_later())
        parent.bind("<Configure>", self._hero_resize, add="+")

    def _hero_resize(self, e=None):
        wh = self.grid_wrap.winfo_height()
        avail = wh - 86 - 1 - 40          # üst çubuk + ayırıcı + alt ipucu satırı
        hh = 0 if avail < 520 else max(220, min(380, int(avail * 0.26)))
        if hh == self._hero_h:
            return
        self._hero_h = hh
        if hh == 0:
            self.hero_cv.pack_forget()
        else:
            self.hero_cv.configure(height=hh)
            self.hero_cv.pack(side="top", fill="x", before=self.grid_cv)

    def hero_draw_later(self):
        if self._hero_job:
            try:
                self.after_cancel(self._hero_job)
            except Exception:
                pass
        self._hero_job = self.after(30, self.hero_draw)

    def _fit_font(self, text, maxw, size, weight="bold", lo=18):
        f = tkfont.Font(family=FONT, size=size, weight=weight)
        while size > lo and f.measure(text) > maxw:
            size -= 2
            f = tkfont.Font(family=FONT, size=size, weight=weight)
        return size

    def hero_draw(self):
        self._hero_job = None
        if self.view_mode != "grid" or self._hero_h <= 0:
            return
        cv = self.hero_cv
        w, h = cv.winfo_width(), cv.winfo_height()
        if w < 200 or h < 100:
            return
        T = ctx.T
        g = self.current()
        hs = self._hero
        if not g or not self.grid_items:
            cv.delete("all")
            hs.update(bg=None, key=None, size=None, pil=None)
            return
        # ---- arka plan (çapraz solmalı)
        kind = next((k for k in ("arkaplan", "kapak") if ctx.find_asset(g["id"], k)), None)
        path = ctx.find_asset(g["id"], kind) if kind else None
        try:
            stamp = os.path.getmtime(path) if path else None
        except OSError:
            stamp = None
        key = (g["id"], kind, stamp, w, h)
        size_changed = hs["size"] != (w, h) or hs["bg"] is None
        if size_changed:
            cv.delete("all")
            hs["bg"] = cv.create_image(0, 0, anchor="nw")
            hs["size"] = (w, h)
            hs["key"] = None
        else:
            cv.delete("hero_fg")
        if hs["key"] != key:
            if kind == "arkaplan":
                base = ctx.get_image(g, "arkaplan", (w, h)).convert("RGB")
            elif kind == "kapak":
                small = ctx.get_image(g, "kapak", (max(8, w // 6), max(8, h // 6))).convert("RGB")
                small = small.filter(ImageFilter.GaussianBlur(3))
                base = ImageEnhance.Brightness(small).enhance(0.8).resize((w, h), _BICUBIC)
            else:
                base = Image.new("RGB", (w, h), ImageColor.getrgb(ctx.color_for(g["id"])))
            new = hero_strip(base, T["bg"])
            prev = hs["pil"]
            if prev is not None and prev.size == new.size and not size_changed and self._xf_on():
                self.xfade_start("hero", cv, hs["bg"], prev, new)
            else:
                self._xf_tok["hero"] = self._xf_tok.get("hero", 0) + 1
                self.refs["xf_hero"] = ImageTk.PhotoImage(new)
                cv.itemconfigure(hs["bg"], image=self.refs["xf_hero"])
                self._xf_cur["hero"] = new
            hs["pil"], hs["key"] = new, key
        cv.tag_lower(hs["bg"])
        # ---- ön plan: ikon/logo, başlık, bilgi, OYNA, toplam süre
        pad = 38
        btn_h, btn_w, bottom = 52, 196, 30
        if hs["btn"] is None:
            hs["btn"] = ctx.RoundButton(cv, "OYNA", self.start_game, primary=True, width=btn_w, height=btn_h,
                                        font=(FONT, 15, "bold"), icon="▶", bg=T["bg"])
            self._primary_btns.append(hs["btn"])
        btn_top = h - bottom - btn_h
        cv.create_window(pad, h - bottom, window=hs["btn"], anchor="sw", tags=("hero_fg",))
        meta = "  ·  ".join(x for x in (g.get("source", ""), g.get("genre", ""), g.get("developer", "")) if x)
        icon_ok = bool(ctx.find_asset(g["id"], "ikon"))
        tx = pad + (82 if icon_ok else 0)
        maxw = max(200, w - tx - pad - 40)
        meta_y = btn_top - 14
        if meta:
            cv.create_text(tx, meta_y, text=meta, anchor="sw", fill="#cbd5e1",
                           font=(FONT, 12), tags=("hero_fg",), width=maxw)
        logo_p = ctx.find_asset(g["id"], "logo")
        title_y = meta_y - (26 if meta else 6)
        drawn_logo = False
        if logo_p:
            try:
                lg = Image.open(logo_p).convert("RGBA")
                lg.thumbnail((min(460, maxw), 96), _LANCZOS)
                self.refs["hero_logo"] = ImageTk.PhotoImage(lg)
                cv.create_image(tx, title_y + 6, image=self.refs["hero_logo"], anchor="sw", tags=("hero_fg",))
                drawn_logo = True
            except Exception:
                drawn_logo = False
        if not drawn_logo:
            name = g["name"]
            fs = self._fit_font(name, maxw, int(32 * float(self.cfg.get("font_scale", 1.0))))
            cv.create_text(tx + 2, title_y + 2, text=name, anchor="sw", fill="#000000",
                           font=(FONT, fs, "bold"), tags=("hero_fg",))
            cv.create_text(tx, title_y, text=name, anchor="sw", fill=T["title"],
                           font=(FONT, fs, "bold"), tags=("hero_fg",))
        if icon_ok:
            try:
                ic = ctx.round_corners(ctx.get_image(g, "ikon", (64, 64)), 14)
                self.refs["hero_icon"] = ImageTk.PhotoImage(ic)
                cv.create_image(pad, meta_y if meta else title_y, image=self.refs["hero_icon"],
                                anchor="sw", tags=("hero_fg",))
            except Exception:
                pass
        # toplam oynama süresi + son oynanma (OYNA'nın sağında)
        sx = pad + btn_w + 30
        if w - sx > 240:
            tot = ctx.fmt_playtime(g.get("play_seconds", 0)) or "Henüz oynanmadı"
            cv.create_text(sx, btn_top + 2, text="TOPLAM OYNANMA", anchor="nw", fill="#a3a3a3",
                           font=(FONT, 8, "bold"), tags=("hero_fg",))
            cv.create_text(sx, btn_top + 18, text=tot, anchor="nw", fill=T["title"],
                           font=(FONT, 18, "bold"), tags=("hero_fg",))
            last = g.get("last_played") or ""
            if last and w - sx > 470:
                try:
                    from datetime import datetime
                    last = datetime.fromisoformat(last).strftime("%d.%m.%Y")
                except Exception:
                    pass
                cv.create_text(sx + 230, btn_top + 2, text="SON OYNANMA", anchor="nw", fill="#a3a3a3",
                               font=(FONT, 8, "bold"), tags=("hero_fg",))
                cv.create_text(sx + 230, btn_top + 18, text=last, anchor="nw", fill=T["title"],
                               font=(FONT, 18, "bold"), tags=("hero_fg",))

    # ------------------------------------------------------------ CAM MENÜ (kumanda menüsü)
    def glass_menu_show(self, items):
        T = ctx.T
        W, H = self.winfo_width(), self.winfo_height()
        mw = min(720, int(W * 0.88))
        rowh, head, foot = 56, 66, 54
        mh = head + rowh * len(items) + foot
        x0 = (W - mw) // 2
        y0 = max(10, min(int(H * 0.45 - mh / 2), H - mh - 10))
        img = glass_image(self._backdrop(W, H), (x0, y0, x0 + mw, y0 + mh), radius=24, blur=24,
                          tint=(8, 10, 22), tint_a=int(self.cfg.get("glass_tint", 150)), border_a=60)
        cv = tk.Canvas(self, width=mw, height=mh, highlightthickness=0, bd=0, bg=T["panel"])
        self.refs["glass_menu"] = ImageTk.PhotoImage(img)
        cv.create_image(0, 0, image=self.refs["glass_menu"], anchor="nw")
        cv.create_text(30, 34, text="MENÜ", anchor="w", fill="#a3a3a3", font=(FONT, 12, "bold"))
        rows = []
        for i, (txt, _cb) in enumerate(items):
            y = head + i * rowh
            poly = cv.create_polygon(ctx.rr_points(14, y + 4, mw - 14, y + rowh - 4, 14), smooth=True,
                                     fill="", outline="")
            tid = cv.create_text(36, y + rowh / 2, text=txt, anchor="w", fill=T["text"], font=(FONT, 16))
            rows.append((poly, tid))
        cv.create_text(30, mh - 28, text="A: seç   B: kapat", anchor="w", fill="#a3a3a3", font=(FONT, 10))

        def row_at(e):
            i = int((e.y - head) // rowh)
            return i if 0 <= i < len(items) else None

        def click(e):
            i = row_at(e)
            if i is not None:
                self.pad_menu_select(i)
                self.pad_menu_activate()

        def motion(e):
            i = row_at(e)
            if i is not None and i != self.pad_menu_sel:
                self.pad_menu_select(i)

        cv.bind("<Button-1>", click)
        cv.bind("<Motion>", motion)
        cv.place(x=x0, y=y0)
        tk.Misc.lift(cv)   # Canvas.lift() öğe yükseltir; pencere için Misc.lift
        return cv, rows

    def glass_menu_paint(self):
        T = ctx.T
        for i, (poly, tid) in enumerate(self.pad_menu_labels):
            sel = i == self.pad_menu_sel
            try:
                self.pad_menu.itemconfigure(poly, fill=ctx.blend("#161a30", T["accent"], 0.50) if sel else "")
                self.pad_menu.itemconfigure(tid, fill="#ffffff" if sel else T["text"],
                                            font=(FONT, 16, "bold" if sel else "normal"))
            except tk.TclError:
                pass

    # ------------------------------------------------------------ BAŞLATMA GEÇİŞİ
    def _launch_start_rect(self, g, W, H):
        """Kapağın pencere içindeki konumu (x, y, w, h)."""
        try:
            if self.view_mode == "grid":
                i = self.selected
                t, m = self.grid_tiles.get(i), self.grid_m
                if t and m:
                    gc = self.grid_cv
                    ox = gc.winfo_rootx() - self.winfo_rootx()
                    oy = gc.winfo_rooty() - self.winfo_rooty()
                    e = self._tfx.get(i)
                    s = (1.0 + (MAXS - 1.0) * e["p"]) if e else 1.0
                    cx = ox + t["x"] + m["tw"] / 2.0
                    cy = oy + (t["y"] - self._grid_cur) + m["th"] / 2.0
                    return (cx - m["tw"] * s / 2.0, cy - m["th"] * s / 2.0, m["tw"] * s, m["th"] * s)
            elif self._detail_cover_rect:
                x, y, w, h = self._detail_cover_rect
                return (x + self.canvas.winfo_rootx() - self.winfo_rootx(),
                        y + self.canvas.winfo_rooty() - self.winfo_rooty(), w, h)
        except tk.TclError:
            pass
        w, h = W * 0.2, W * 0.28
        return ((W - w) / 2, (H - h) / 2, w, h)

    def launch_transition(self, g):
        """OYNA: kapak büyüyüp ekranı kaplar, 'Başlatılıyor...' ve ince ilerleme çizgisi görünür."""
        if not self.cfg.get("fx_launch", True) or self.launching:
            return
        try:
            if self._hidden or self.state() == "iconic":
                return
            self.update_idletasks()
            W, H = self.winfo_width(), self.winfo_height()
            if W < 200 or H < 200:
                return
            rect0 = self._launch_start_rect(g, W, H)
            src = ctx.get_image(g, "kapak", (900, 1260)).convert("RGB")
            cv = tk.Canvas(self, bg="#000000", highlightthickness=0, bd=0, cursor="watch")
            cv.place(x=0, y=0, relwidth=1, relheight=1)
            tk.Misc.lift(cv)
            item = cv.create_image(0, 0, anchor="nw")
        except Exception:
            return
        cv.bind("<Button-1>", lambda e: self.launch_finish(force=True))
        self.launching = {"cv": cv, "item": item, "src": src, "rect0": rect0, "W": W, "H": H,
                          "t0": time.perf_counter(), "name": g["name"], "ui": None, "photo": None,
                          "finish": False, "force": False, "fin_t": None}
        self._launch_step()

    def launch_finish(self, force=False):
        """Oyun başladı (ya da vazgeçildi): ilerleme çizgisi dolar, sonra ekran kapanır."""
        L = self.launching
        if not L:
            return
        L["finish"] = True
        if force:
            L["force"] = True

    def _launch_close(self):
        L, self.launching = self.launching, None
        if L:
            try:
                L["cv"].destroy()
            except tk.TclError:
                pass
        if hasattr(self, "_play_busy"):
            self._play_busy(False)               # OYNA düğmesi eski rengine döner

    def _launch_step(self):
        L = self.launching
        if not L:
            return
        T = ctx.T
        if self._hidden:      # oyun açılıp launcher tepsiye indi: geçişe gerek kalmadı
            self._launch_close()
            return
        cv, W, H = L["cv"], L["W"], L["H"]
        now = time.perf_counter()
        t = now - L["t0"]
        try:
            k = min(1.0, t / LAUNCH_GROW)
            x0, y0, w0, h0 = L["rect0"]
            t_back0 = LAUNCH_GROW + LAUNCH_HOLD
            t_done = t_back0 + LAUNCH_BACK
            if t < t_back0:                       # 1) kapak yerinden büyüyüp ekranı kaplar
                e = smooth(k)
            elif t < t_done:                      # 2) tam ekrandan eski yerine geri döner
                e = smooth(1 - (t - t_back0) / LAUNCH_BACK)
            else:
                e = 0.0
            rect = (x0 + (0 - x0) * e, y0 + (0 - y0) * e, w0 + (W - w0) * e, h0 + (H - h0) * e)
            if k < 0.22:
                # başlamadan önce kapak hafifçe zoom yapar (kendi merkezinde büyüyüp küçülür)
                s = 1 + 0.08 * math.sin(math.pi * k / 0.22)
                rx, ry, rw, rh = rect
                rect = (rx + rw / 2 - rw * s / 2, ry + rh / 2 - rh * s / 2, rw * s, rh * s)
            if t < t_back0:
                dark = 0.55 * max(0.0, (k - 0.30) / 0.70)
            else:
                dark = 0.55 * max(0.0, 1 - (t - t_back0) / LAUNCH_BACK)
            if t < t_done or L["photo"] is None:
                im, pos = launch_frame(L["src"], rect, 18 * (1 - e), dark)
                L["photo"] = ImageTk.PhotoImage(im)
                cv.itemconfigure(L["item"], image=L["photo"])
                cv.coords(L["item"], *pos)
            if t >= t_done:
                # kapak eski yerine oturdu: ekran gizlenir, oyun açılana kadar launcher bekler
                try:
                    cv.destroy()                 # başlatma ekranını tamamen kaldır (kapak zaten yerine döndü)
                except tk.TclError:
                    pass
                L["covering"] = False            # ekran artık kapalı: kullanıcı diğer oyunlara tıklayabilir
                if t > LAUNCH_MAX or (L["finish"] and (L["force"] or t >= LAUNCH_MIN)):
                    self._launch_close()          # oyun açıldı ya da zaman aşımı: launcher bekleme durumundan çıkar
                    return
                self.after(100, self._launch_step)
                return
            if t >= t_back0 and L["ui"] is not None:
                for key in ("name", "sh", "txt", "track", "fill"):
                    cv.itemconfigure(L["ui"][key], state="hidden")
            if k >= 1.0 and t < t_back0:
                if L["ui"] is None:
                    tl, tr = int(W * 0.22), int(W * 0.78)
                    ly = int(H * 0.56)
                    ui = {"tl": tl, "tr": tr, "ly": ly}
                    ui["name"] = cv.create_text(W // 2, int(H * 0.44) - 40, text=L["name"], fill="#cbd5e1",
                                                font=(FONT, 15), width=int(W * 0.8), justify="center")
                    ui["sh"] = cv.create_text(W // 2 + 2, int(H * 0.44) + 2, text="Başlatılıyor...", fill="#000000",
                                              font=(FONT, 32, "bold"))
                    ui["txt"] = cv.create_text(W // 2, int(H * 0.44), text="Başlatılıyor...", fill="#303030",
                                               font=(FONT, 32, "bold"))
                    ui["track"] = cv.create_rectangle(tl, ly, tr, ly + 3, fill="#ffffff", outline="",
                                                      stipple="gray25")
                    ui["fill"] = cv.create_rectangle(tl, ly, tl, ly + 3, fill=T["accent_hover"], outline="")
                    L["ui"] = ui
                ui = L["ui"]
                tp = t - LAUNCH_GROW
                cv.itemconfigure(ui["txt"], fill=ctx.blend("#303030", "#ffffff", min(1.0, tp / 0.25)))
                frac = 0.92 * (1 - math.exp(-tp / 1.3))
                if L["finish"] and (L["force"] or t >= LAUNCH_MIN):
                    if L["fin_t"] is None:
                        L["fin_t"] = now
                        L["fin_from"] = frac
                    f = min(1.0, (now - L["fin_t"]) / 0.18)
                    frac = L["fin_from"] + (1.0 - L["fin_from"]) * f
                    if f >= 1.0:
                        cv.coords(ui["fill"], ui["tl"], ui["ly"], ui["tr"], ui["ly"] + 3)
                        self.after(120, self._launch_close)
                        return
                if t > LAUNCH_MAX and not L["finish"]:
                    L["finish"] = L["force"] = True
                cv.coords(ui["fill"], ui["tl"], ui["ly"], ui["tl"] + (ui["tr"] - ui["tl"]) * frac,
                          ui["ly"] + 3)
        except tk.TclError:
            self._launch_close()          # ekranı da kaldır; yalnızca durumu sıfırlamak ekranı açık bırakırdı
            return
        except Exception:
            _log_err()
            self._launch_close()
            return
        self.after(16, self._launch_step)
