# launcher.py için değişiklikler

Hepsini sırayla uygula. `launcher_extras.py` aynı klasörde olmalı.

## 1) Importlar ve BASE_DIR (tek .exe için şart)

Üstteki `BASE_DIR = ...` satırını şununla değiştir ve importların altına `import launcher_extras as ex` ekle:

```python
import launcher_extras as ex

if getattr(sys, "frozen", False):
    BASE_DIR = os.path.dirname(sys.executable)   # exe'nin yanı (config/assets/music burada kalır)
else:
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
```

Bunu yapmazsan .exe her açılışta geçici klasörü kullanır ve ayarların/görseller silinir.

## 2) load_data / save_data (yeni alanlar kaybolmasın)

`DEFAULT_CFG`'nin altına ekle:

```python
EXTRA_KEYS = {"args": "", "admin": False, "install_dir": "", "source": "", "store_id": ""}
```

`load_data` içindeki `games.append({...})` bloğunu şununla değiştir:

```python
                games.append({"id": gid, "name": g.get("name", gid), "path": g.get("path", ""),
                              "last_played": g.get("last_played", ""),
                              "publisher": g.get("publisher", ""), "developer": g.get("developer", ""),
                              "release": g.get("release", ""), "genre": g.get("genre", ""),
                              "desc": g.get("desc", ""), "launch_count": g.get("launch_count", 0),
                              **{k: g.get(k, d) for k, d in EXTRA_KEYS.items()}})
```

`save_data` içindeki `out["games"] = [...]` bloğunu şununla değiştir:

```python
    out["games"] = [{"id": g["id"], "name": g["name"], "path": g["path"],
                     "last_played": g.get("last_played", ""),
                     "publisher": g.get("publisher", ""), "developer": g.get("developer", ""),
                     "release": g.get("release", ""), "genre": g.get("genre", ""),
                     "desc": g.get("desc", ""), "launch_count": g.get("launch_count", 0),
                     **{k: g.get(k, d) for k, d in EXTRA_KEYS.items()}}
                    for g in games]
```

## 3) Launcher sınıfında değiştirilecek metotlar

### install_dir

```python
    def install_dir(self, g):
        d = g.get("install_dir", "")
        if d and os.path.isdir(d):
            return d
        p = g.get("path", "")
        if p and not ex.is_uri(p) and os.path.exists(p):
            return os.path.dirname(p)
        return ""
```

### start_game

```python
    def start_game(self):
        g = self.current()
        if not g:
            return
        if not ex.is_launchable(g):
            if not self.pick_path():
                return
        try:
            ex.launch_game(g)
        except Exception as e:
            messagebox.showerror("Hata", f"Oyun başlatılamadı:\n{e}")
            return
        g["last_played"] = datetime.now().isoformat(timespec="minutes")
        g["launch_count"] = int(g.get("launch_count", 0) or 0) + 1
        self.save()
        if self.cfg["pause_on_launch"]:
            self.music.pause_now()
            self.user_paused = True
            self.update_music_ui()
        self.redraw()
```

### draw_info_panel içinde (tek satır)

```python
        exe = os.path.basename(g.get("path", "")) if g.get("path") else ""
```
yerine:
```python
        exe = ex.display_target(g)
```

### edit_info (başlatma ayarları dahil, tamamını değiştir)

```python
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
            tk.Label(win, text=label, bg=T["bg"], fg=T["muted"], font=("Arial", 10)
                     ).grid(row=r, column=0, sticky="w", padx=(22, 12), pady=8)
            v = tk.StringVar(value=g.get(k, ""))
            tk.Entry(win, textvariable=v, width=42, bg=T["panel"], fg=T["text"],
                     insertbackground=T["text"], relief="flat", font=("Arial", 11)
                     ).grid(row=r, column=1, padx=(0, 22), pady=8, ipady=5)
            vars_[k] = v

        n = len(fields)
        admin_var = tk.BooleanVar(value=bool(g.get("admin")))
        tk.Checkbutton(win, text="Yönetici olarak çalıştır", variable=admin_var,
                       bg=T["bg"], fg=T["text"], selectcolor=T["panel"],
                       activebackground=T["bg"], activeforeground=T["title"],
                       font=("Arial", 10)).grid(row=n, column=1, sticky="w", pady=(0, 6))

        tk.Label(win, text="Açıklama", bg=T["bg"], fg=T["muted"], font=("Arial", 10)
                 ).grid(row=n + 1, column=0, sticky="nw", padx=(22, 12), pady=8)
        txt = tk.Text(win, width=42, height=6, bg=T["panel"], fg=T["text"],
                      insertbackground=T["text"], relief="flat", font=("Arial", 11), wrap="word")
        txt.insert("1.0", g.get("desc", ""))
        txt.grid(row=n + 1, column=1, padx=(0, 22), pady=8)

        def save():
            for k, v in vars_.items():
                g[k] = v.get().strip()
            g["admin"] = admin_var.get()
            g["desc"] = txt.get("1.0", "end").strip()
            self.save()
            win.destroy()
            self.redraw()

        row = tk.Frame(win, bg=T["bg"])
        row.grid(row=n + 2, column=0, columnspan=2, pady=(6, 18))
        chip(row, "Kaydet", save, primary=True, font=("Arial", 10)).pack(side="left", padx=6)
        chip(row, "Vazgeç", win.destroy, font=("Arial", 10)).pack(side="left", padx=6)
```

Not: Mağaza bağlantılı oyunlarda (Steam, Epic, Xbox) "yönetici olarak çalıştır" etkisizdir, çünkü oyunu mağaza istemcisi açar. Bu oyunlar için exe'yi elle seçersen (sağ tık > Oyun yolunu değiştir) yönetici seçeneği çalışır.

## 4) Kenar çubuğuna "Ayarlar" butonu

`build_sidebar` içinde `add = chip(...)` satırının hemen üstüne ekle:

```python
        self.settings_btn = chip(self.sidebar, "Ayarlar", self.open_settings_menu, pady=6,
                                 icon="⚙", font=("Arial", 10))
        self.settings_btn.pack(side="bottom", fill="x", padx=10, pady=(0, 0))
```

(`add` butonu `side="bottom"` ile sonra paketlendiği için Ayarlar'ın altında kalır.)

## 5) Yeni metotlar (Launcher sınıfının içine, örneğin `delete_game`'in üstüne)

```python
    # ------------------------------------------------------------ AYARLAR / TARAMA
    def open_settings_menu(self):
        m = styled_menu(self)
        self.autostart_var = tk.BooleanVar(value=ex.is_autostart())
        m.add_command(label="Mağaza oyunlarını tara...", command=self.open_store_scan)
        m.add_separator()
        m.add_checkbutton(label="Windows ile başlat", variable=self.autostart_var,
                          command=self.toggle_autostart)
        x = self.settings_btn.winfo_rootx()
        y = self.settings_btn.winfo_rooty() - 60
        try:
            m.tk_popup(x, y)
        finally:
            m.grab_release()

    def toggle_autostart(self):
        try:
            ex.set_autostart(self.autostart_var.get())
        except Exception as e:
            messagebox.showerror("Hata", f"Ayar değiştirilemedi:\n{e}")
            self.autostart_var.set(ex.is_autostart())

    def open_store_scan(self):
        if not self.check_idle():
            return
        self.run_bg(ex.scan_all, self.show_scan_results,
                    "Mağaza oyunları taranıyor...", refresh=False)

    def show_scan_results(self, found):
        have = {(g.get("source", ""), g.get("store_id", "")) for g in self.games if g.get("store_id")}
        paths = {os.path.normcase(g["path"]) for g in self.games if g.get("path")}
        new = [f for f in found
               if (f["source"], f["store_id"]) not in have
               and os.path.normcase(f["path"]) not in paths]
        if not new:
            messagebox.showinfo("Tarama bitti",
                                "Yeni oyun bulunamadı." if not found else
                                f"{len(found)} oyun bulundu, hepsi zaten listende.")
            return

        win = tk.Toplevel(self)
        win.title("Bulunan oyunlar")
        win.geometry("560x720")
        win.configure(bg=T["bg"])
        win.transient(self)
        tk.Label(win, text=f"{len(new)} yeni oyun bulundu", bg=T["bg"], fg=T["title"],
                 font=("Arial", 14, "bold")).pack(anchor="w", padx=20, pady=(18, 8))

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
                           anchor="w", font=("Arial", 11)).pack(fill="x", padx=10, pady=2)

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
        chip(btns, "Seçilenleri ekle", add_selected, primary=True, font=("Arial", 11)).pack(side="left")
        chip(btns, "Tümünü seç", lambda: set_all(True), font=("Arial", 11)).pack(side="left", padx=8)
        chip(btns, "Hiçbiri", lambda: set_all(False), font=("Arial", 11)).pack(side="left")

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
                 "last_played": "", "color": color_for(gid)}
            self.games.append(g)
            added.append(g)
        self.save()
        self.search_var.set("")
        self.selected = len(self.games) - len(added)
        self.refresh_all()
        steam = [g for g in added if g["source"] == "Steam"]
        if steam:
            self.run_bg(lambda: self._fetch_steam_art(steam), None, "Steam görselleri indiriliyor...")

    def _fetch_steam_art(self, games):
        import io
        for g in games:
            for kind, url in ex.steam_art_urls(g["store_id"]).items():
                try:
                    req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
                    with urllib.request.urlopen(req, timeout=10) as r:
                        img = Image.open(io.BytesIO(r.read())).convert("RGBA")
                    remove_assets(g["id"], kind)
                    img.save(os.path.join(ASSETS_DIR, f"{g['id']}_{kind}.png"), "PNG")
                except Exception:
                    pass  # görseli olmayan oyunlar yer tutucuyla kalır
```

## 6) Windows açılışında küçültülmüş başlatma

`__init__` içinde, `self.protocol("WM_DELETE_WINDOW", self.on_close)` satırının altına:

```python
        if "--minimized" in sys.argv:
            self.after(200, self.iconify)
```

## Notlar

- Tarayıcılar Windows'a özgüdür ve ben Linux'ta çalıştığım için gerçek bir Steam/Epic/Xbox kurulumuna karşı deneyemedim. Sadece sözdizimi kontrolü yaptım. En sağlam olanlar Steam ve Epic, en kırılgan olanlar EA app ve Xbox (EA app'in kütüphane dosyası yok, kayıt defteri ve klasör sezgisi kullanıyor; Xbox için PowerShell ile paket adı çözülüyor).
- Tek .exe `--onefile` modunda her açılışta kendini geçici klasöre açar, bu yüzden ilk açılış 2-5 saniye sürebilir. Windows ile başlatmada bu fark edilmez. Antivirüs bazen PyInstaller dosyalarına yanlış alarm verir.
- Arkadaşına verirken sadece `OyunLauncher.exe`'yi ver. `launcher_config.json` içinde senin oyun yollarının olduğu için onu verme, kendi oyunlarını tarayarak ekler.
