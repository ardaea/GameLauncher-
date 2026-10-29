"""F7 tuşu ve Xbox kumandasındaki Xbox düğmesiyle Oyun Launcher'ı açar.

- Launcher kapalıysa açar.
- Launcher tepsideyse ya da arkada kaldıysa öne getirir.

Bu dosyayı launcher.py ile aynı klasöre koy. Windows açılışında da çalışsın istersen
Win+R → shell:startup → buraya bu dosyanın kısayolunu koy.
"""
import ctypes
import os
import subprocess
import sys
import threading
import time
from ctypes import wintypes

BASE = os.path.dirname(os.path.abspath(__file__))
FLAG = os.path.join(BASE, "goster.flag")
LAUNCHER = os.path.join(BASE, "launcher.py")

HOTKEY_ID = 1
VK_F7 = 0x76
MOD_NOREPEAT = 0x4000
WM_HOTKEY = 0x0312
XINPUT_GUIDE = 0x0400      # Xbox (rehber) düğmesi bit değeri

user32 = ctypes.windll.user32


class XINPUT_GAMEPAD(ctypes.Structure):
    _fields_ = [("wButtons", wintypes.WORD), ("bLeftTrigger", ctypes.c_ubyte),
                ("bRightTrigger", ctypes.c_ubyte), ("sThumbLX", ctypes.c_short),
                ("sThumbLY", ctypes.c_short), ("sThumbRX", ctypes.c_short),
                ("sThumbRY", ctypes.c_short)]


class XINPUT_STATE(ctypes.Structure):
    _fields_ = [("dwPacketNumber", wintypes.DWORD), ("Gamepad", XINPUT_GAMEPAD)]


STATE = os.path.join(BASE, "calisiyor.txt")   # launcher her ~1 sn'de yazar: "acik" / "tepsi"
KAPAT = os.path.join(BASE, "kapat.flag")
_child = None   # bu dinleyicinin başlattığı launcher süreci


def launcher_acik():
    """Launcher son 3 saniye içinde 'acik' (ekranda) bildirdiyse True."""
    try:
        if time.time() - os.path.getmtime(STATE) > 3:
            return False
        with open(STATE, encoding="utf-8") as f:
            return f.read().strip() == "acik"
    except OSError:
        return False


def open_launcher(kol=False):
    """F7 / Xbox: launcher açıksa kapatır (kapat.flag), değilse açar.
    kol=True (Xbox düğmesi): launcher tam ekran kapak (grid) modunda açılır."""
    if launcher_acik():
        try:
            with open(KAPAT, "w") as f:
                f.write("1")
        except OSError:
            pass
        return
    global _child
    # Bu dinleyicinin başlattığı launcher hâlâ çalışıyor (henüz açılıyor olabilir): yenisini açma,
    # sadece "göster" sinyali bırak; çalışan kopya alıp öne getirir.
    yeni = _child is None or _child.poll() is not None
    try:
        with open(FLAG, "w", encoding="utf-8") as f:
            f.write("kol" if kol else "klavye")
    except OSError:
        return
    if not yeni:
        return
    time.sleep(0.6)
    if os.path.exists(FLAG):
        try:
            os.remove(FLAG)
        except OSError:
            pass
        py = sys.executable
        if py.lower().endswith("python.exe"):
            py = py[:-len("python.exe")] + "pythonw.exe"   # konsol penceresi açılmasın
        args = [py, LAUNCHER] + (["--kol"] if kol else [])
        _child = subprocess.Popen(args, cwd=BASE)


def guide_watch():
    """Xbox kumandasının rehber düğmesini izler (XInputGetStateEx, gizli 100 numaralı fonksiyon)."""
    dll = None
    for name in ("xinput1_4.dll", "xinput1_3.dll", "xinput9_1_0.dll"):
        try:
            dll = ctypes.windll.LoadLibrary(name)
            break
        except OSError:
            continue
    if dll is None:
        return
    get_ex = dll[100]
    get_ex.argtypes = [wintypes.DWORD, ctypes.POINTER(XINPUT_STATE)]
    get_ex.restype = wintypes.DWORD
    st = XINPUT_STATE()
    was = False
    while True:
        pressed = False
        for i in range(4):
            if get_ex(i, ctypes.byref(st)) == 0 and (st.Gamepad.wButtons & XINPUT_GUIDE):
                pressed = True
                break
        if pressed and not was:
            threading.Thread(target=open_launcher, kwargs={"kol": True}, daemon=True).start()
        was = pressed
        time.sleep(0.05)


def main():
    threading.Thread(target=guide_watch, daemon=True).start()
    if not user32.RegisterHotKey(None, HOTKEY_ID, MOD_NOREPEAT, VK_F7):
        print("F7 kısayolu kaydedilemedi; başka bir program bu tuşu kullanıyor olabilir.")
    msg = wintypes.MSG()
    while user32.GetMessageW(ctypes.byref(msg), None, 0, 0) != 0:
        if msg.message == WM_HOTKEY:
            threading.Thread(target=open_launcher, daemon=True).start()
        user32.TranslateMessage(ctypes.byref(msg))
        user32.DispatchMessageW(ctypes.byref(msg))


if __name__ == "__main__":
    main()
