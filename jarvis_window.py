"""Fenêtre de JARVIS : l'interface dans une fenêtre sans cadre Windows (moteur WebView2, celui d'Edge).

Pas de barre de titre ni de boutons Windows (les boutons sont ceux de l'interface), icône JARVIS dans la barre des
tâches (et pas celle d'Edge). Lancée par jarvis_voice.py : pythonw jarvis_window.py <adresse> [--small] [--title X].
Fermer la fenêtre arrête ce processus ; JARVIS le voit (plus de connexion) et repasse en arrière-plan.
"""
from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONF_DIR = Path.home() / ".openjarvis"
ICON = HERE / "jarvis.ico"

user32 = ctypes.windll.user32
try:  # coordonnées en pixels réels, comme jarvis_voice.py
    ctypes.windll.shcore.SetProcessDpiAwareness(2)
except Exception:
    pass
# Identité propre dans la barre des tâches : regroupée à part, avec l'icône JARVIS (pas Python, pas Edge)
ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("JARVIS.VoiceAssistant")


def _arg(name: str, default: str) -> str:
    return sys.argv[sys.argv.index(name) + 1] if name in sys.argv[:-1] else default


URL = next((a for a in sys.argv[1:] if a.startswith("http")), "http://127.0.0.1:8765")
TITLE = _arg("--title", "JARVIS")
SMALL = "--small" in sys.argv
# --wait-server : ouverte AVANT que JARVIS ait fini de se charger (démarrage du PC) : une page d'attente s'affiche
# tout de suite, la vraie interface dès que le serveur répond (2026-10-19 : « il faut voir JARVIS, pas le bureau »)
WAIT = "--wait-server" in sys.argv
LOAD_TIME = CONF_DIR / "chargement_duree.txt"  # durée du dernier chargement (s), pour la barre de progression
LOAD_PROFILE = CONF_DIR / "chargement_profil.json"  # moment de chaque étape au dernier démarrage (part du total)
ETAPE_FILE = CONF_DIR / "chargement_etape.txt"       # étape réelle en cours (écrite par jarvis_voice.py)
T_START = time.time()
ETAPES: dict = {}  # étape -> secondes depuis l'ouverture de la fenêtre


def _follow_steps(win) -> None:
    """Étapes réelles du chargement -> la page (la barre se recale sur le vrai démarrage)."""
    last = ""
    while WAIT and not ETAPES.get("pret"):
        try:
            v = ETAPE_FILE.read_text(encoding="utf-8").strip()
        except Exception:
            v = ""
        if v and v != last and v.isdigit():
            last = v
            ETAPES[v] = round(time.time() - T_START, 2)
            try:
                win.evaluate_js(f"window.jarvisEtape && window.jarvisEtape({int(v)})")
            except Exception:
                pass
        time.sleep(0.15)


def _loading_html() -> str:
    """Écran de chargement style Iron Man (chargement.html), sinon un simple cercle qui tourne."""
    try:
        try:
            expected = max(4.0, min(90.0, float(LOAD_TIME.read_text(encoding="utf-8"))))
        except Exception:
            expected = 15.0
        try:
            profil = LOAD_PROFILE.read_text(encoding="utf-8").strip() or "{}"
        except Exception:
            profil = "{}"
        return ((HERE / "chargement.html").read_text(encoding="utf-8").replace("__DUREE__", f"{expected:.1f}")
                .replace("__PROFIL__", profil))
    except Exception:
        return ('<body style="margin:0;background:#02060c;color:#00d2ff;font:3vmin Segoe UI;display:flex;'
                'align-items:center;justify-content:center;height:100vh">INITIALISATION…</body>')


SCREEN = _arg("--screen", "secondaire")  # « secondaire » : sur le 2e écran s'il est branché ; « principal »


class _MONITORINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.DWORD), ("rcMonitor", wintypes.RECT), ("rcWork", wintypes.RECT),
                ("dwFlags", wintypes.DWORD)]


def target_monitor() -> tuple[tuple, tuple]:
    """(écran entier, zone de travail) de l'écran choisi, en pixels réels."""
    mons = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(hmon, _hdc, _rc, _lp):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            r, w = mi.rcMonitor, mi.rcWork
            mons.append(((r.left, r.top, r.right, r.bottom), (w.left, w.top, w.right, w.bottom), bool(mi.dwFlags & 1)))
        return True

    user32.EnumDisplayMonitors(None, None, cb, 0)
    mons.sort(key=lambda m: not m[2])  # le principal en premier
    if not mons:
        sw, sh = user32.GetSystemMetrics(0), user32.GetSystemMetrics(1)
        return (0, 0, sw, sh), (0, 0, sw, sh)
    m = mons[1] if SCREEN != "principal" and len(mons) > 1 else mons[0]
    return m[0], m[1]


def small_rect() -> tuple[int, int, int, int]:
    """Petite fenêtre : environ deux tiers de l'écran choisi, centrée (dans la zone sans la barre des tâches)."""
    x0, y0, x1, y1 = target_monitor()[1]
    w, h = int((x1 - x0) * 0.84), int((y1 - y0) * 0.88)
    return x0 + (x1 - x0 - w) // 2, y0 + (y1 - y0 - h) // 2, w, h


def _set_icon(hwnd: int) -> None:
    if not ICON.exists():
        return
    for size, which in ((256, 1), (32, 0)):  # ICON_BIG, ICON_SMALL
        h = user32.LoadImageW(None, str(ICON), 1, size, size, 0x0010)  # IMAGE_ICON, LR_LOADFROMFILE
        if h:
            user32.SendMessageW(hwnd, 0x0080, which, h)  # WM_SETICON


def _after_shown() -> None:
    hwnd = 0
    for _ in range(100):
        hwnd = user32.FindWindowW(None, TITLE)
        if hwnd:
            break
        time.sleep(0.1)
    if not hwnd:
        return
    _set_icon(hwnd)
    # grand : tout l'écran choisi, barre des tâches comprise ; petit : centrée (pixels réels)
    if SMALL:
        x, y, w, h = small_rect()
    else:
        x0, y0, x1, y1 = target_monitor()[0]
        x, y, w, h = x0, y0, x1 - x0, y1 - y0
    user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004 | 0x0040)  # SWP_NOZORDER | SWP_SHOWWINDOW
    user32.SetForegroundWindow(hwnd)


def _monitor_works() -> list[tuple]:
    out = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HMONITOR, wintypes.HDC, ctypes.POINTER(wintypes.RECT), wintypes.LPARAM)
    def cb(hmon, _hdc, _rc, _lp):
        mi = _MONITORINFO()
        mi.cbSize = ctypes.sizeof(_MONITORINFO)
        if user32.GetMonitorInfoW(hmon, ctypes.byref(mi)):
            w = mi.rcWork
            out.append((w.left, w.top, w.right, w.bottom))
        return True

    user32.EnumDisplayMonitors(None, None, cb, 0)
    return out


def _follow_tablet() -> None:
    """Écran de la tablette branché (2e écran qui apparaît) : la fenêtre y saute tout de suite, en grand, sans
    attendre que JARVIS ait fini de se charger. Vérifié toutes les 0,2 s : le bureau ne doit presque pas se voir."""
    if SCREEN == "principal":
        return
    prev = len(_monitor_works())
    while True:
        time.sleep(0.2)
        try:
            n = len(_monitor_works())
            if n >= 2 and prev < 2:
                hwnd = user32.FindWindowW(None, TITLE)
                if hwnd:
                    x0, y0, x1, y1 = target_monitor()[0]
                    if user32.IsZoomed(hwnd) or user32.IsIconic(hwnd):
                        user32.ShowWindow(hwnd, 9)
                    user32.SetWindowPos(hwnd, 0, x0, y0, x1 - x0, y1 - y0, 0x0004 | 0x0040)
            prev = n
        except Exception:
            pass


def _allow_camera(win) -> None:
    """La page de JARVIS (http://127.0.0.1) a le droit d'utiliser la webcam sans demander à chaque ouverture : la
    fenêtre Caméra (suivi des mains, atelier 3D) ne doit pas afficher d'autorisation (2026-10-19). Seulement la
    caméra, seulement cette adresse locale. CoreWebView2 ne se touche que depuis le fil de la fenêtre (Invoke)."""
    import traceback

    log_f = CONF_DIR / "fenetre_camera.log"
    done = []

    for attempt in range(150):
        time.sleep(0.2)
        try:
            form = win.native
            from System import Action

            def attach() -> None:
                core = form.browser.webview.CoreWebView2
                if core is None:
                    return
                from Microsoft.Web.WebView2.Core import CoreWebView2PermissionState

                def on_perm(sender, args) -> None:
                    try:
                        uri, kind = str(args.Uri), str(args.PermissionKind)
                        if kind == "Camera" and uri.startswith(("http://127.0.0.1", "http://localhost")):
                            args.State = CoreWebView2PermissionState.Allow
                            args.Handled = True
                    except Exception:
                        log_f.write_text(traceback.format_exc(), encoding="utf-8")

                core.PermissionRequested += on_perm
                done.append(1)

            form.Invoke(Action(attach))
            if done:
                return
        except Exception:
            if attempt == 149:
                log_f.write_text(traceback.format_exc(), encoding="utf-8")


def _keep_on_screen() -> None:
    """La fenêtre ne doit jamais se retrouver hors des écrans (2026-10-17 : elle était à x = 4296 alors que les
    écrans s'arrêtaient à 3840, après un changement d'écran secondaire / d'échelle : « elle disparaît et ne revient
    pas »). Vérifié toutes les 1,5 s : si moins de 120×80 px est visible sur un écran, elle revient au centre."""
    while True:
        time.sleep(1.5)
        try:
            hwnd = user32.FindWindowW(None, TITLE)
            if not hwnd or user32.IsIconic(hwnd) or not user32.IsWindowVisible(hwnd):
                continue
            r = wintypes.RECT()
            user32.GetWindowRect(hwnd, ctypes.byref(r))
            seen = any(min(r.right, x1) - max(r.left, x0) >= 120 and min(r.bottom, y1) - max(r.top, y0) >= 80
                       for x0, y0, x1, y1 in _monitor_works())
            if not seen:
                x, y, w, h = small_rect()
                user32.SetWindowPos(hwnd, 0, x, y, w, h, 0x0004 | 0x0040)  # SWP_NOZORDER | SWP_SHOWWINDOW
        except Exception:
            pass


def _ensure_shortcut() -> None:
    """Raccourci « JARVIS » du menu Démarrer (même identité que la fenêtre) : sans lui, épingler JARVIS à la barre
    des tâches affiche le logo de Python."""
    import os
    import subprocess

    lnk = Path(os.environ.get("APPDATA", "")) / r"Microsoft\Windows\Start Menu\Programs\JARVIS.lnk"
    script = HERE / "creer_raccourci_jarvis.ps1"
    if not lnk.exists() and script.exists():
        subprocess.Popen(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(script)],
                         creationflags=0x08000000)


def _watchdog(win) -> None:
    """Si JARVIS (le serveur) a répondu puis disparaît pendant 15 s, la fenêtre se ferme toute seule : sinon elle
    reste figée, sans sphère, et ses boutons (qui passent par le serveur) ne ferment plus rien."""
    import urllib.error
    import urllib.request

    seen, down_since, t0 = False, 0.0, time.time()
    while True:
        time.sleep(0.5 if WAIT and not seen else 3)
        try:
            urllib.request.urlopen(URL.rstrip("/") + "/m", timeout=3).close()
            ok = True
        except urllib.error.HTTPError:
            ok = True  # le serveur répond (même par une erreur) : il est là
        except Exception:
            ok = False
        if ok:
            if WAIT and not seen:
                try:
                    total = time.time() - T_START
                    ETAPES["pret"] = total
                    if total > 3:  # vrai chargement (pas JARVIS déjà prêt)
                        LOAD_TIME.write_text(f"{total:.1f}", encoding="utf-8")
                        import json as _json

                        LOAD_PROFILE.write_text(_json.dumps(
                            {k: round(t / total, 3) for k, t in ETAPES.items() if k != "pret"}), encoding="utf-8")
                    win.evaluate_js("window.jarvisPret && window.jarvisPret()")  # barre à 100 %
                    time.sleep(0.6)
                except Exception:
                    pass
                win.load_url(URL)  # JARVIS est prêt à servir l'interface : la vraie page remplace l'attente
            seen, down_since = True, 0.0
        elif WAIT and not seen and time.time() - t0 > 180:
            win.destroy()  # JARVIS ne démarre pas : pas de fenêtre d'attente pour toujours
            return
        elif seen:
            down_since = down_since or time.time()
            if time.time() - down_since > 15:
                try:
                    win.destroy()
                finally:
                    return


class Api:
    """Appelé par la page (window.pywebview.api) : déplacement NATIF de la fenêtre par Windows.

    La zone de déplacement de pywebview déplace la fenêtre à chaque mouvement de souris depuis la page : pendant
    le glissé, surtout entre deux écrans d'échelles différentes (PC 100 %, tablette 150-200 %), la fenêtre
    disparaissait puis revenait (2026-10-17). Ici, Windows s'en charge comme pour une fenêtre normale."""

    def start_drag(self) -> bool:
        hwnd = user32.FindWindowW(None, TITLE)
        if not hwnd:
            return False
        # Déplacement suivi à la main (2026-10-20) : ReleaseCapture + SC_MOVE ne marchait pas (la souris est « capturée »
        # par le fil de WebView2, pas par celui de cet appel) ; on suit la position du curseur tant que le bouton est enfoncé.
        threading.Thread(target=_drag_loop, args=(hwnd,), daemon=True, name="deplacement").start()
        return True

    def start_resize(self, edge: str) -> bool:
        """Redimensionne la fenêtre sans cadre en suivant la souris (bord ou coin : n s e w ne nw se sw), tant que le
        bouton gauche reste enfoncé. Windows ne le fait pas pour une fenêtre sans cadre."""
        hwnd = user32.FindWindowW(None, TITLE)
        if not hwnd or edge not in ("n", "s", "e", "w", "ne", "nw", "se", "sw"):
            return False
        threading.Thread(target=_resize_loop, args=(hwnd, edge), daemon=True, name="redim").start()
        return True


def _drag_loop(hwnd: int) -> None:
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    r, p0 = wintypes.RECT(), wintypes.POINT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    u.GetCursorPos(ctypes.byref(p0))
    x0, y0 = r.left, r.top
    while u.GetAsyncKeyState(0x01) & 0x8000:  # VK_LBUTTON
        p = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(p))
        u.SetWindowPos(hwnd, 0, x0 + p.x - p0.x, y0 + p.y - p0.y, 0, 0, 0x0001 | 0x0004 | 0x0010)  # NOSIZE|NOZORDER|NOACTIVATE
        time.sleep(0.008)


def _resize_loop(hwnd: int, edge: str) -> None:
    import ctypes
    from ctypes import wintypes

    u = ctypes.windll.user32
    r, p0 = wintypes.RECT(), wintypes.POINT()
    u.GetWindowRect(hwnd, ctypes.byref(r))
    u.GetCursorPos(ctypes.byref(p0))
    x0, y0, x1, y1 = r.left, r.top, r.right, r.bottom
    min_w, min_h = 640, 420
    while u.GetAsyncKeyState(0x01) & 0x8000:  # VK_LBUTTON
        p = wintypes.POINT()
        u.GetCursorPos(ctypes.byref(p))
        dx, dy = p.x - p0.x, p.y - p0.y
        nx0, ny0, nx1, ny1 = x0, y0, x1, y1
        if "e" in edge:
            nx1 = max(x0 + min_w, x1 + dx)
        if "w" in edge:
            nx0 = min(x1 - min_w, x0 + dx)
        if "s" in edge:
            ny1 = max(y0 + min_h, y1 + dy)
        if "n" in edge:
            ny0 = min(y1 - min_h, y0 + dy)
        u.SetWindowPos(hwnd, 0, nx0, ny0, nx1 - nx0, ny1 - ny0, 0x0004 | 0x0010)  # SWP_NOZORDER | SWP_NOACTIVATE
        time.sleep(0.012)


def main() -> None:
    import webview

    _ensure_shortcut()

    x, y, w, h = small_rect()
    win = webview.create_window(TITLE, None if WAIT else URL, html=_loading_html() if WAIT else None, width=w, height=h, x=x, y=y, frameless=True, easy_drag=False,
                                background_color="#02060C", min_size=(300, 300), text_select=True, js_api=Api())
    win.events.shown += lambda: threading.Thread(target=_after_shown, daemon=True).start()
    threading.Thread(target=_watchdog, args=(win,), daemon=True).start()
    threading.Thread(target=_keep_on_screen, daemon=True, name="sur-ecran").start()
    threading.Thread(target=_follow_tablet, daemon=True, name="tablette").start()
    threading.Thread(target=_allow_camera, args=(win,), daemon=True, name="camera").start()
    if WAIT:
        threading.Thread(target=_follow_steps, args=(win,), daemon=True, name="etapes").start()
    storage = CONF_DIR / "jarvis-webview"
    storage.mkdir(parents=True, exist_ok=True)
    webview.start(gui="edgechromium", private_mode=False, storage_path=str(storage))


if __name__ == "__main__":
    main()
