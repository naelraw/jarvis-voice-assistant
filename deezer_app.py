"""Appli Deezer (Microsoft Store) pilotée par JARVIS.

Le lien deezer://www.deezer.com/<type>/<id> ouvre la bonne page dans l'appli mais ne lance pas la lecture, et l'appli
n'expose rien à l'accessibilité Windows. On repère donc le bouton violet « Écouter » sur une capture de la fenêtre
(PrintWindow : marche même si elle est cachée derrière une autre) et on lui envoie le clic directement
(PostMessage) : ni la souris ni le premier plan ne bougent, on peut rester en jeu.
"""
from __future__ import annotations

import ctypes
import os
import subprocess
import threading
import time
from ctypes import wintypes

user32 = ctypes.WinDLL("user32", use_last_error=True)
gdi32 = ctypes.WinDLL("gdi32")
APP_ID = "Deezer.62021768415AF_q7m17pa7q8kj0!Deezer.Music"
PLAYER_BAR = 110  # hauteur (px à 100 %) de la barre de lecture en bas, qui a aussi un bouton violet


def installed() -> bool:
    root = os.path.join(os.environ.get("ProgramFiles", r"C:\Program Files"), "WindowsApps")
    try:
        return any(n.startswith("Deezer.62021768415AF_") for n in os.listdir(root))
    except Exception:  # dossier protégé : on regarde le menu Démarrer
        try:
            out = subprocess.run(["powershell", "-NoProfile", "-Command", "Get-AppxPackage Deezer.62021768415AF"],
                                 capture_output=True, text=True, timeout=10, creationflags=0x08000000).stdout
            return "Deezer" in out
        except Exception:
            return False


def hwnd() -> int:
    """Fenêtre principale de l'appli Deezer (0 si fermée)."""
    import psutil

    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(h, _):
        if user32.GetWindow(h, 4) or not user32.GetWindowTextLengthW(h):
            return True
        pid = wintypes.DWORD()
        user32.GetWindowThreadProcessId(h, ctypes.byref(pid))
        try:
            cls = ctypes.create_unicode_buffer(64)
            user32.GetClassNameW(h, cls, 64)
            if (psutil.Process(pid.value).name().lower() == "deezer.exe" and cls.value == "Chrome_WidgetWin_1"
                    and user32.IsWindowVisible(h)):  # réduite, l'appli n'a plus de zone de page : on prend la fenêtre
                found.append(h)
        except Exception:
            pass
        return True

    user32.EnumWindows(cb, 0)
    return found[0] if found else 0


def _render_child(h: int, visible: bool = True) -> int:
    kids = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def cb(c, _):
        buf = ctypes.create_unicode_buffer(64)
        user32.GetClassNameW(c, buf, 64)
        if buf.value == "Chrome_RenderWidgetHostHWND" and (not visible or user32.IsWindowVisible(c)):
            kids.append(c)
        return True

    user32.EnumChildWindows(h, cb, 0)
    return kids[0] if kids else 0


def launch(wait: float = 20.0) -> int:
    h = hwnd()
    if h:
        return h
    subprocess.Popen(["explorer.exe", f"shell:AppsFolder\\{APP_ID}"])
    t0 = time.time()
    while time.time() - t0 < wait:
        time.sleep(0.5)
        h = hwnd()
        if h:
            time.sleep(2.5)  # l'appli s'affiche, puis charge le compte
            return h
    return 0


def _capture(h: int):
    """Image de la zone de page (enfant de rendu) : (image PIL, enfant) ; None si impossible."""
    from PIL import Image

    c = _render_child(h)
    if not c:
        return None
    r = wintypes.RECT()
    user32.GetClientRect(c, ctypes.byref(r))
    w, ht = r.right, r.bottom
    if w < 200 or ht < 200:
        return None
    hdc = user32.GetDC(c)
    mdc = gdi32.CreateCompatibleDC(hdc)
    bmp = gdi32.CreateCompatibleBitmap(hdc, w, ht)
    gdi32.SelectObject(mdc, bmp)
    ok = user32.PrintWindow(c, mdc, 2)  # PW_RENDERFULLCONTENT : marche pour Chromium, même caché

    class BMI(ctypes.Structure):
        _fields_ = [("biSize", wintypes.DWORD), ("biWidth", wintypes.LONG), ("biHeight", wintypes.LONG),
                    ("biPlanes", wintypes.WORD), ("biBitCount", wintypes.WORD), ("biCompression", wintypes.DWORD),
                    ("biSizeImage", wintypes.DWORD), ("biXPelsPerMeter", wintypes.LONG),
                    ("biYPelsPerMeter", wintypes.LONG), ("biClrUsed", wintypes.DWORD), ("biClrImportant", wintypes.DWORD)]

    bi = BMI(ctypes.sizeof(BMI), w, -ht, 1, 32, 0, 0, 0, 0, 0, 0)
    buf = ctypes.create_string_buffer(w * ht * 4)
    gdi32.GetDIBits(mdc, bmp, 0, ht, buf, ctypes.byref(bi), 0)
    gdi32.DeleteObject(bmp)
    gdi32.DeleteDC(mdc)
    user32.ReleaseDC(c, hdc)
    if not ok:
        return None
    return Image.frombuffer("RGB", (w, ht), buf, "raw", "BGRX", 0, 1), c


def _purple(p) -> bool:
    r, g, b = p
    return 120 <= r <= 200 and g <= 100 and b >= 200


def find_listen(img) -> tuple[int, int] | None:
    """Centre du bouton violet « Écouter » de la page (pas celui de la barre de lecture)."""
    w, ht = img.size
    scale = max(1.0, w / 1210 if w > 1500 else 1.0)
    bottom = ht - int(PLAYER_BAR * scale)
    px = img.load()
    for y in range(0, bottom, 3):
        xs = [x for x in range(0, w, 3) if _purple(px[x, y])]
        if len(xs) * 3 >= 90 * scale:  # une large bande violette : le bouton (le rond de lecture fait ~32 px)
            # descendre jusqu'au milieu du bouton
            y2 = y
            while y2 < bottom and sum(1 for x in xs if _purple(px[x, y2])) * 3 >= 60 * scale:
                y2 += 2
            return (min(xs) + max(xs)) // 2, (y + y2) // 2
    return None


def click(child: int, x: int, y: int) -> None:
    lp = (y << 16) | (x & 0xFFFF)
    user32.PostMessageW(child, 0x0200, 0, lp)  # WM_MOUSEMOVE
    time.sleep(0.05)
    user32.PostMessageW(child, 0x0201, 1, lp)  # WM_LBUTTONDOWN
    time.sleep(0.06)
    user32.PostMessageW(child, 0x0202, 0, lp)  # WM_LBUTTONUP


def play(kind: str, item_id, wait: float = 10.0) -> str:
    """Ouvre la page (titre, album, playlist, artiste) dans l'appli et appuie sur « Écouter ».
    Réponses : « ok », « pas-installe », « pas-de-fenetre », « pas-de-bouton »."""
    try:
        ctypes.windll.user32.SetThreadDpiAwarenessContext(ctypes.c_void_p(-4))  # pixels réels
    except Exception:
        pass
    h = launch()
    if not h:
        return "pas-de-fenetre" if installed() else "pas-installe"
    was_min = bool(user32.IsIconic(h))
    if was_min:
        user32.ShowWindow(h, 4)  # SW_SHOWNOACTIVATE : la page doit être dessinée, sans voler le premier plan
        for _ in range(20):
            time.sleep(0.15)
            if _render_child(h):
                break
        time.sleep(0.4)
    before = _capture(h)
    os.startfile(f"deezer://www.deezer.com/{kind}/{item_id}")
    t0, last = time.time(), None
    while time.time() - t0 < wait:
        time.sleep(0.5)
        cap = _capture(h)
        if not cap:
            continue
        img, child = cap
        # la nouvelle page doit être affichée (sinon on cliquerait le bouton de l'ancienne)
        if before and time.time() - t0 < 1.5 and _same(img, before[0]):
            continue
        pos = find_listen(img)
        if pos and pos == last:  # bouton stable sur deux captures : la page a fini de se placer
            click(child, *pos)
            if was_min:  # on la remet réduite, comme avant (l'appli se rouvre parfois une fois de plus en ouvrant le lien)
                def remin() -> None:
                    for _ in range(3):
                        time.sleep(0.8)
                        if not user32.IsIconic(h):
                            user32.ShowWindow(h, 7)

                threading.Thread(target=remin, daemon=True).start()
            return "ok"
        last = pos
    if was_min:
        user32.ShowWindow(h, 7)
    return "pas-de-bouton"


def _same(a, b) -> bool:
    if a.size != b.size:
        return False
    sa, sb = a.resize((48, 30)).tobytes(), b.resize((48, 30)).tobytes()
    return sum(abs(x - y) for x, y in zip(sa, sb)) < 48 * 30 * 3 * 4


if __name__ == "__main__":
    import sys

    print(play(sys.argv[1], sys.argv[2]))
