"""Ekran koruyucu modu: boşta kalma ekranını kapak slaytına / oynanış videolarına çevirir.

OLED uyumu: zemin tam siyah (#000000), içerik kısık parlaklıkta, hiçbir şey piksel piksel sabit
durmaz (görsel, saat ve yazılar çok yavaş kayar) ve slaytlar arası siyaha solma vardır.

launcher.py bu modülü `_idle_start` içinden çağırır. Modül `launcher`'ı import etmez; ihtiyacı olan
yardımcılar (find_asset, get_image, ...) `env` ile dışarıdan verilir.
"""
import math
import random
import time
import tkinter as tk
from types import SimpleNamespace
from datetime import datetime
from tkinter import font as tkfont

from PIL import Image, ImageEnhance, ImageTk

# Menüde görünen modlar: (anahtar, etiket)
MODES = (
    ("bands", "Kayan kapaklar (klasik)"),
    ("covers", "Kapak slaytı"),
    ("videos", "Oynanış videoları"),
    ("mix", "Karışık (kapak + video)"),
)
DEFAULT_MODE = "covers"
SECONDS_CHOICES = (6, 10, 15, 30, 60)

FADE = 0.9          # siyaha solma süresi (sn), giriş ve çıkış için ayrı ayrı
COVER_DIM = 0.80    # kapak parlaklığı (OLED'de yanma + güç tüketimi için kısık)
VIDEO_DIM = 0.85    # video parlaklığı
SLIDE_SECS = 10     # her slaytın (kapak ya da video) toplam süresi (sn): giriş + gösterim + çıkış solması dahil


class Saver:
    def __init__(self, cv, W, H, env):
        self.cv, self.W, self.H, self.env = cv, W, H, env
        self.mode = env.mode if env.mode in dict(MODES) else DEFAULT_MODE
        # ayardaki süre solmalar dahil toplam süredir; ayar yoksa 10 sn
        self.hold = max(3.0, int(env.seconds or SLIDE_SECS) - 2 * FADE)
        self.phase = random.random() * 100
        self.slide = None
        self.last_kind = None
        self.photo = None
        self.cv2 = None
        self.notice = ""   # videoya geçilemediyse açıklama (ör. opencv yok)

        if self.mode in ("videos", "mix"):
            try:
                import cv2
                self.cv2 = cv2
            except ImportError:
                self.notice = "Video için: pip install opencv-python"

        games = list(env.games)
        self.covers = [g for g in games if env.find_asset(g["id"], "kapak")]
        self.videos = [g for g in games if self.cv2 and env.find_asset(g["id"], "video", env.video_exts)]
        self.bags = {"cover": [], "video": []}

        # ölçüler
        m = min(W, H)
        self.ch = int(min(H * 0.62, W * 0.8 * 1.4))
        self.cw = int(self.ch / 1.4)
        self.vbox = (int(W * 0.92), int(H * 0.75))   # video için en-boy korunarak sığdırılan kutu

        # öğeler (hepsi siyah zeminde, soluk)
        self.f_name = tkfont.Font(family=env.font, size=max(14, int(m * 0.026)), weight="bold")
        self.f_clock = tkfont.Font(family=env.font, size=max(18, int(m * 0.055)), weight="bold")
        self.f_small = tkfont.Font(family=env.font, size=max(11, int(m * 0.018)))
        self.c_name = env.blend("#000000", "#ffffff", 0.62)
        self.c_clock = env.blend("#000000", "#ffffff", 0.42)
        self.c_small = env.blend("#000000", "#ffffff", 0.30)
        self.img_id = cv.create_image(W / 2, H / 2, anchor="center")
        self.name_id = cv.create_text(W / 2, H / 2, text="", font=self.f_name, fill=self.c_name)
        self.clock_id = cv.create_text(W / 2, H * 0.07, text="", font=self.f_clock, fill=self.c_clock)
        self.date_id = cv.create_text(W / 2, H * 0.07, text="", font=self.f_small, fill=self.c_small)
        self.track_id = cv.create_text(W / 2, H * 0.95, text="", font=self.f_small, fill=self.c_small,
                                       width=int(W * 0.8), justify="center")
        self.clock_txt = None
        self.ls = self.f_clock.metrics("linespace")
        self.ds = self.f_small.metrics("linespace")

    # ------------------------------------------------------------------ seçim
    def _kind(self):
        has_c, has_v = bool(self.covers), bool(self.videos)
        if self.mode == "videos":
            return "video" if has_v else ("cover" if has_c else None)
        if self.mode == "mix":
            if has_v and (self.last_kind != "video" or not has_c):
                return "video"
            return "cover" if has_c else None
        return "cover" if has_c else None

    def _pick(self, kind):
        pool = self.covers if kind == "cover" else self.videos
        if not pool:
            return None
        bag = self.bags[kind]
        if not bag:
            bag.extend(random.sample(pool, len(pool)))
            last = self.slide["g"]["id"] if self.slide else None
            if len(bag) > 1 and bag[-1]["id"] == last:   # arka arkaya aynı oyun gelmesin
                bag[0], bag[-1] = bag[-1], bag[0]
        return bag.pop()

    # ------------------------------------------------------------------ slayt hazırlama
    def _next(self):
        self._close_slide()
        for _ in range(6):   # açılamayan videoda diğerine geç
            kind = self._kind()
            if kind is None:
                self.slide = None
                self.cv.itemconfigure(self.img_id, state="hidden")
                self.cv.itemconfigure(self.name_id, text="")
                self.slide_wait = time.perf_counter() + 5
                return
            g = self._pick(kind)
            s = self._open_video(g) if kind == "video" else self._open_cover(g)
            if s:
                self.slide, self.last_kind = s, kind
                self.cv.itemconfigure(self.img_id, state="normal")
                self.cv.itemconfigure(self.name_id, text=g["name"])
                return
            if kind == "video":   # bozuk video: listeden çıkar
                self.videos = [v for v in self.videos if v["id"] != g["id"]]
        self.slide = None
        self.slide_wait = time.perf_counter() + 2

    def _open_cover(self, g):
        try:
            img = self.env.get_image(g, "kapak", (self.cw, self.ch)).convert("RGB")
            img = ImageEnhance.Brightness(img).enhance(COVER_DIM).convert("RGBA")
            img = self.env.round_corners(img, max(8, int(self.ch * 0.03)))
        except Exception:
            return None
        return {"kind": "cover", "g": g, "img": img, "w": img.size[0], "h": img.size[1],
                "t0": time.perf_counter(), "dur": self.hold, "last_f": -1.0}

    def _open_video(self, g):
        cv2 = self.cv2
        path = self.env.find_asset(g["id"], "video", self.env.video_exts)
        if not path:
            return None
        try:
            cap = cv2.VideoCapture(path)
            if not cap.isOpened():
                cap.release()
                return None
            fps = cap.get(cv2.CAP_PROP_FPS) or 30
            fps = fps if 5 <= fps <= 120 else 30
            total = cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0
            fw = cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 16
            fh = cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 9
            start = 0
            if total > fps * (self.hold + 12):   # girişi atla, ortalardan bir yerden başla
                start = int(random.uniform(0.08, 0.6) * (total - fps * self.hold))
                cap.set(cv2.CAP_PROP_POS_FRAMES, start)
            s = min(self.vbox[0] / fw, self.vbox[1] / fh)
            vw, vh = max(2, int(fw * s) // 2 * 2), max(2, int(fh * s) // 2 * 2)
        except Exception:
            return None
        return {"kind": "video", "g": g, "cap": cap, "fps": fps, "start": start, "pos": start,
                "vw": vw, "vh": vh, "raw": None, "ended": False,
                "t0": time.perf_counter(), "dur": self.hold, "last_f": -1.0}

    def _close_slide(self):
        s = self.slide
        if s and s.get("cap") is not None:
            try:
                s["cap"].release()
            except Exception:
                pass
            s["cap"] = None

    def close(self):
        self._close_slide()
        self.slide = None
        self.photo = None

    # ------------------------------------------------------------------ kare
    def tick(self):
        now = time.perf_counter()
        self._chrome(now)
        s = self.slide
        if s is None:
            if now >= getattr(self, "slide_wait", 0):
                self._next()
            return
        el = now - s["t0"]
        d = s["dur"]
        if el < FADE:
            f = el / FADE
        elif el < FADE + d:
            f = 1.0
        elif el < 2 * FADE + d:
            f = (2 * FADE + d - el) / FADE
        else:
            self._next()
            return
        f = f * f * (3 - 2 * f)   # yumuşak geçiş
        if s["kind"] == "cover":
            self._draw_cover(s, f)
        else:
            self._draw_video(s, f, el)
        s["last_f"] = f
        self._place(s, f)

    def _draw_cover(self, s, f):
        if f == s["last_f"] or (f >= 1.0 and s["last_f"] >= 1.0):
            return
        img = s["img"]
        if f < 1.0:
            lut = [int(i * f) for i in range(256)]
            img = img.point(lut * 3 + list(range(256)))   # RGB'yi kıs, alfa'yı koru
        self.photo = ImageTk.PhotoImage(img)
        self.cv.itemconfigure(self.img_id, image=self.photo)

    def _draw_video(self, s, f, el):
        cv2 = self.cv2
        cap = s["cap"]
        new = False
        if cap is not None and not s["ended"]:
            want = s["start"] + int(el * s["fps"])
            try:
                while s["pos"] < want - 1:   # geride kaldıysak kare atla (hız doğru kalsın)
                    if not cap.grab():
                        break
                    s["pos"] += 1
                ok, frame = cap.read()
                if ok:
                    s["pos"] += 1
                    s["raw"] = frame
                    new = True
                elif s["raw"] is not None:
                    s["ended"] = True
                    s["dur"] = max(0.0, min(s["dur"], el - FADE))   # video bitti: söne geç
                else:
                    s["ended"] = True
                    s["dur"] = 0.0
            except Exception:
                s["ended"] = True
        if s["raw"] is None:
            return
        if not new and f >= 1.0 and s["last_f"] >= 1.0:
            return
        try:
            fr = cv2.resize(s["raw"], (s["vw"], s["vh"]), interpolation=cv2.INTER_AREA)
            fr = cv2.convertScaleAbs(fr, alpha=VIDEO_DIM * f)
            fr = cv2.cvtColor(fr, cv2.COLOR_BGR2RGB)
            self.photo = ImageTk.PhotoImage(Image.fromarray(fr))
            self.cv.itemconfigure(self.img_id, image=self.photo)
            s["w"], s["h"] = s["vw"], s["vh"]
        except Exception:
            pass

    def _place(self, s, f):
        """Görsel ve yazılar çok yavaş gezinir; böylece hiçbir piksel sabit kalmaz."""
        W, H = self.W, self.H
        tt = time.time() + self.phase
        cx = W / 2 + W * 0.04 * math.sin(tt * 2 * math.pi / 97)
        cy = H / 2 + H * 0.02 * math.cos(tt * 2 * math.pi / 131)
        h = s.get("h") or self.ch
        self.cv.coords(self.img_id, cx, cy)
        self.cv.coords(self.name_id, cx, cy + h / 2 + self.ds * 1.6)
        self.cv.itemconfigure(self.name_id, fill=self.env.blend("#000000", self.c_name, f))

    def _chrome(self, now):
        """Saat, tarih ve çalan şarkı: üstte ters fazda yavaş kayar."""
        W, H = self.W, self.H
        tt = time.time() + self.phase
        cx = W / 2 + W * 0.05 * math.cos(tt * 2 * math.pi / 113)
        cy = H * 0.07 + H * 0.012 * math.sin(tt * 2 * math.pi / 149)
        self.cv.coords(self.clock_id, cx, cy)
        self.cv.coords(self.date_id, cx, cy + self.ls * 0.55 + self.ds * 0.5)
        self.cv.coords(self.track_id, W / 2 + W * 0.03 * math.sin(tt * 2 * math.pi / 89), H * 0.95)
        n = datetime.now()
        txt = (n.strftime("%H:%M"), self.env.date_tr(n), self.env.track() or self.notice)
        if txt != self.clock_txt:
            self.clock_txt = txt
            self.cv.itemconfigure(self.clock_id, text=txt[0])
            self.cv.itemconfigure(self.date_id, text=txt[1])
            self.cv.itemconfigure(self.track_id, text=txt[2])
