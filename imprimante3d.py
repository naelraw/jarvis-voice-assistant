"""Imprimante 3D (Creality Ender 3 d'origine, firmware Marlin) branchée en USB : état, refroidissement, préchauffage encadré,
découpe (PrusaSlicer + profil Ender 3 / PLA) et impression envoyée par le câble, avec suivi, pause et annulation.

Parle en G-code par le port série (puce CH340, 115 200 bauds). La ligne DTR reste coupée : ouvrir le port ne redémarre pas la
carte. Un seul accès à la fois (verrou). Pendant une impression, le PC est empêché de se mettre en veille, et le fichier
~/.openjarvis/impression_en_cours.json existe : NE PAS redémarrer JARVIS tant qu'il est là (l'impression s'arrêterait).
Chauffer à la main reste limité (buse ≤ 230 °C, plateau ≤ 70 °C) ; le préchauffage s'éteint tout seul au bout de 15 min.
"""
from __future__ import annotations

import json
import re
import subprocess
import threading
import time
from pathlib import Path

VID, PID = 0x1A86, 0x7523       # puce CH340
BAUD = 115200
MAX_HOTEND, MAX_BED = 230, 70
PREHEAT_MINUTES = 15
WORK = Path.home() / ".openjarvis" / "impression3d"
PROFILE = WORK / "ender3_pla.ini"
LOCK_FILE = Path.home() / ".openjarvis" / "impression_en_cours.json"
SLICER = Path(r"C:\Program Files\Prusa3D\PrusaSlicer\prusa-slicer-console.exe")
MODELS_DIR = Path.home() / "Documents" / "Impressions 3D"
MODEL_EXTS = (".stl", ".3mf", ".obj", ".gcode")
_LOCK = threading.Lock()
_AUTO_OFF: dict = {"timer": None}
JOB: dict = {"state": "idle"}   # idle | printing | paused | done | cancelled | error


def find_port() -> str | None:
    from serial.tools import list_ports

    for p in list_ports.comports():
        if p.vid == VID and p.pid == PID:
            return p.device
    return None


def _open():
    import serial

    port = find_port()
    if not port:
        raise RuntimeError("Imprimante introuvable : câble USB débranché, ou imprimante éteinte.")
    s = serial.Serial()
    s.port, s.baudrate, s.timeout = port, BAUD, 0.3
    s.dtr = False
    s.rts = False
    s.open()
    time.sleep(0.4)
    s.reset_input_buffer()
    return s


def busy() -> bool:
    return JOB.get("state") in ("printing", "paused")


def _talk(cmds: list[str], settle: float = 0.6, timeout: float = 4.0) -> str:
    """Envoie des commandes hors impression, renvoie tout ce que dit l'imprimante (attend « ok » après chacune)."""
    if busy():
        raise RuntimeError("Une impression est en cours : commande refusée (utilise pause ou annule).")
    with _LOCK:
        s = _open()
        try:
            out = ""
            for c in cmds:
                s.write((c + "\n").encode())
                t0, got = time.time(), ""
                while time.time() - t0 < timeout:
                    got += s.read(256).decode("utf-8", "ignore")
                    if re.search(r"(^|\n)ok\b", got):
                        time.sleep(0.05)
                        got += s.read(256).decode("utf-8", "ignore")
                        break
                out += got
            time.sleep(settle)
            return out
        finally:
            s.close()


_TEMP_RE = re.compile(r"T:([\d.]+)\s*/([\d.]+).*?B:([\d.]+)\s*/([\d.]+)")


def _temps(txt: str) -> dict | None:
    m = _TEMP_RE.search(txt)
    if not m:
        return None
    t, tt, b, bt = (float(x) for x in m.groups())
    return {"buse": t, "buse_cible": tt, "plateau": b, "plateau_cible": bt, "chauffe": tt > 0 or bt > 0}


_TEMPS: dict = {"t": 0.0, "v": None, "asked": 0.0, "thread": None}


def _temps_loop() -> None:
    """Lit les températures toutes les 3 s tant que la page (ou JARVIS) les a demandées il y a moins de 30 s : la page
    s'affiche tout de suite (avant : 3 s d'attente à chaque fois, le port USB étant rouvert pour chaque lecture)."""
    while time.time() - _TEMPS["asked"] < 30:
        if not busy():
            try:
                t = _temps(_talk(["M105"], settle=0.05, timeout=2.5))
                _TEMPS.update(t=time.time(), v=t if t else {"ok": False, "why": "L'imprimante n'a pas répondu comme prévu."})
            except Exception as exc:
                _TEMPS.update(t=time.time(), v={"ok": False, "why": str(exc)})
        time.sleep(3)
    _TEMPS["thread"] = None


def etat(fast: bool = False) -> dict:
    """Températures (et avancement si une impression tourne). Réponse immédiate : dernière lecture (≤ 3 s).
    fast=True (page) : jamais d'attente, même à la toute première lecture (températures « – » une seconde)."""
    _TEMPS["asked"] = time.time()
    if not _TEMPS["thread"]:
        _TEMPS["thread"] = threading.Thread(target=_temps_loop, daemon=True, name="imprimante-temperatures")
        _TEMPS["thread"].start()
    if not busy() and _TEMPS["v"] is not None and time.time() - _TEMPS["t"] < 10:
        v = _TEMPS["v"]
        if isinstance(v, dict) and v.get("ok") is False:
            return dict(v)
        return {"ok": True, **v, "state": JOB.get("state", "idle"), "last": JOB.get("name")}
    if fast and not busy():
        return {"ok": True, "buse": None, "buse_cible": 0, "plateau": None, "plateau_cible": 0, "chauffe": False,
                "lecture": True, "state": JOB.get("state", "idle"), "last": JOB.get("name")}
    return _etat_direct()


def _etat_direct() -> dict:
    """Températures (et avancement si une impression tourne)."""
    if busy() or JOB.get("state") in ("done", "cancelled", "error"):
        j = dict(JOB)
        j["ok"] = True
        if busy():
            return j
    try:
        t = _temps(_talk(["M105"]))
    except Exception as exc:
        return {"ok": False, "why": str(exc)}
    if not t:
        return {"ok": False, "why": "L'imprimante n'a pas répondu comme prévu."}
    return {"ok": True, **t, "state": JOB.get("state", "idle"), "last": JOB.get("name")}


def refroidir() -> dict:
    """Coupe la buse, le plateau et le ventilateur de pièce."""
    _cancel_timer()
    try:
        _talk(["M104 S0", "M140 S0", "M107"])
    except Exception as exc:
        return {"ok": False, "why": str(exc)}
    return {"ok": True}


def _cancel_timer() -> None:
    t = _AUTO_OFF.get("timer")
    if t:
        t.cancel()
    _AUTO_OFF["timer"] = None


def prechauffer(buse: int = 200, plateau: int = 60) -> dict:
    """Préchauffe (limites de sécurité) et programme l'extinction automatique dans PREHEAT_MINUTES."""
    buse, plateau = int(buse), int(plateau)
    pw = check_power()
    if not pw.get("ok"):
        return {"ok": False, "why": pw.get("why", "Imprimante injoignable.")}
    if not pw.get("powered"):
        return {"ok": False, "why": NOT_POWERED, "unpowered": True}
    if not (0 <= buse <= MAX_HOTEND and 0 <= plateau <= MAX_BED):
        return {"ok": False, "why": f"Température refusée : buse {MAX_HOTEND} °C et plateau {MAX_BED} °C au maximum."}
    try:
        _talk([f"M140 S{plateau}", f"M104 S{buse}"])
    except Exception as exc:
        return {"ok": False, "why": str(exc)}
    _cancel_timer()
    tm = threading.Timer(PREHEAT_MINUTES * 60, refroidir)
    tm.daemon = True
    tm.start()
    _AUTO_OFF["timer"] = tm
    return {"ok": True, "buse": buse, "plateau": plateau, "extinction_min": PREHEAT_MINUTES}


# ---------------------------------------------------------------------------------------------------- modèles et découpe

def find_model(name: str) -> Path | None:
    """Fichier à imprimer : chemin complet, ou nom (même approximatif) cherché dans Documents\\Impressions 3D puis Téléchargements."""
    p = Path(name.strip().strip('"'))
    if p.suffix.lower() in MODEL_EXTS and p.exists():
        return p
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    want = re.sub(r"[^a-z0-9]+", " ", name.lower()).split()
    best, score = None, 0
    for d in (MODELS_DIR, Path.home() / "Downloads"):
        for f in sorted(d.rglob("*"), key=lambda x: x.stat().st_mtime if x.exists() else 0, reverse=True):
            if f.suffix.lower() not in MODEL_EXTS:
                continue
            words = re.sub(r"[^a-z0-9]+", " ", f.stem.lower())
            sc = sum(1 for w in want if w in words) if want else 1
            if sc > score:
                best, score = f, sc
    return best


QUALITY = {"fine": ("0.12", "0.2"), "normal": ("0.2", "0.2"), "rapide": ("0.28", "0.28")}


PATTERNS = {"gyroide": "gyroid", "cubique": "cubic", "grille": "grid", "nid": "honeycomb", "lignes": "rectilinear",
            "adaptatif": "adaptivecubic"}
PATTERN_NAMES = {"gyroide": "gyroïde", "cubique": "cubique", "grille": "grille", "nid": "nid d'abeille", "lignes": "lignes",
                 "adaptatif": "cubique adaptatif"}


def auto_infill(model: Path, density: int = 20, scale: int = 100) -> dict:
    """Mode « Auto » : motif et densité choisis d'après la forme de l'objet, pour un maximum de solidité.
    - petite pièce (≤ 30 mm) : gyroïde, au moins 40 % (presque pleine, ne coûte presque rien en temps) ;
    - pièce haute et fine (hauteur > 2,5 × la base) : gyroïde, au moins 25 % (tient dans toutes les directions) ;
    - grande pièce plate (≤ 15 mm de haut, > 100 mm de large) : grille, au moins 15 % (rigide à plat, rapide) ;
    - le reste : gyroïde (solide dans les 3 directions, ne tape pas la buse), au moins 20 %."""
    try:
        t = read_triangles(model).reshape(-1, 3)
        k = max(0.1, scale / 100)
        w, d, h = ((t.max(axis=0) - t.min(axis=0)) * k).tolist()
    except Exception:
        return {"pattern": "gyroide", "density": max(density, 20), "why": "forme inconnue : gyroïde par défaut"}
    big, base = max(w, d, h), min(w, d)
    if big <= 30:
        return {"pattern": "gyroide", "density": max(density, 40), "why": f"petite pièce ({big:.0f} mm) : presque pleine"}
    if h > 2.5 * max(1.0, base):
        return {"pattern": "gyroide", "density": max(density, 25), "why": f"pièce haute et fine ({h:.0f} mm de haut)"}
    if h <= 15 and max(w, d) > 100:
        return {"pattern": "grille", "density": max(density, 15), "why": "grande pièce plate"}
    return {"pattern": "gyroide", "density": max(density, 20), "why": "solide dans toutes les directions"}


def _opts_args(opts: dict | None) -> tuple[list[str], str]:
    """Options de la visionneuse -> arguments PrusaSlicer + suffixe du fichier découpé (une découpe par jeu d'options)."""
    o = opts or {}
    args, tag = [], []
    if o.get("supports"):
        args += ["--support-material", "--support-material-auto"]
        tag.append("sup")
    inf = int(o.get("infill") or 0)
    if inf and 0 <= inf <= 100:
        args += ["--fill-density", f"{inf}%"]
        tag.append(f"r{inf}")
    pat = str(o.get("pattern") or "")
    if pat in PATTERNS:
        args += ["--fill-pattern", PATTERNS[pat]]
        tag.append(pat)
    q = str(o.get("quality") or "")
    if q in QUALITY and q != "normal":
        args += ["--layer-height", QUALITY[q][0], "--first-layer-height", QUALITY[q][1]]
        tag.append(q)
    sc = int(o.get("scale") or 100)
    if sc != 100 and 10 <= sc <= 500:
        args += ["--scale", f"{sc}%"]
        tag.append(f"x{sc}")
    if o.get("brim"):
        args += ["--brim-width", "5"]
        tag.append("brim")
    return args, ("_" + "_".join(tag)) if tag else ""


def slice_model(model: Path, opts: dict | None = None, placed: bool = False) -> dict:
    """STL / 3MF / OBJ -> G-code avec le profil Ender 3 + PLA (centré sur le plateau), plus les options choisies
    (supports, remplissage, qualité, échelle, bordure). Un .gcode est repris tel quel."""
    if model.suffix.lower() == ".gcode":
        out = model
    else:
        if not PROFILE.exists():
            import profil_impression

            profil_impression.build(PROFILE)
        opts = dict(opts or {})
        fill = None
        if str(opts.get("pattern") or "auto") == "auto" and opts:   # mode Auto : d'après la forme de l'objet
            fill = auto_infill(model, int(opts.get("infill") or 20), int(opts.get("scale") or 100))
            opts["pattern"], opts["infill"] = fill["pattern"], fill["density"]
        extra, tag = _opts_args(opts)
        out = WORK / (re.sub(r"[^\w .-]", "_", model.stem) + tag + ".gcode")
        where = ["--dont-arrange"] if placed else ["--center", "117,117"]  # plateau composé : positions gardées telles quelles
        r = subprocess.run([str(SLICER), "--load", str(PROFILE), *extra, *where, "--export-gcode", str(model),
                            "--output", str(out)], capture_output=True, text=True, timeout=600, creationflags=0x08000000)
        if r.returncode or not out.exists():
            return {"ok": False, "why": "Découpe impossible : " + (r.stderr or r.stdout or "")[-300:].strip()}
    txt = out.read_text(encoding="utf-8", errors="ignore")
    tm = re.search(r"estimated printing time \(normal mode\) = (.+)", txt)
    g = re.search(r"filament used \[g\] = ([\d.]+)", txt)
    res = {"ok": True, "gcode": out, "duree": tm.group(1).strip() if tm else "?", "grammes": float(g.group(1)) if g else None,
           "secondes": _secs(tm.group(1)) if tm else 0}
    if model.suffix.lower() != ".gcode" and opts:
        p = str(opts.get("pattern") or "")
        res["remplissage"] = {"motif": PATTERN_NAMES.get(p, p), "densite": int(opts.get("infill") or 0),
                              "auto": (fill or {}).get("why", "") if model.suffix.lower() != ".gcode" else ""}
    return res


def _secs(s: str) -> int:
    t = 0
    for n, u in re.findall(r"(\d+)\s*([dhms])", s):
        t += int(n) * {"d": 86400, "h": 3600, "m": 60, "s": 1}[u]
    return t


# ---------------------------------------------------------------------------------------------------- impression par le câble

def _commands(gcode: Path) -> list[str]:
    out = []
    for line in gcode.read_text(encoding="utf-8", errors="ignore").splitlines():
        c = line.split(";", 1)[0].strip()
        if c:
            out.append(c)
    return out


def _numbered(n: int, cmd: str) -> bytes:
    body = f"N{n} {cmd}"
    cs = 0
    for ch in body:
        cs ^= ord(ch)
    return f"{body}*{cs}\n".encode()


def _awake(on: bool) -> None:
    try:
        import ctypes

        ctypes.windll.kernel32.SetThreadExecutionState(0x80000000 | (0x00000001 if on else 0))  # ES_CONTINUOUS | ES_SYSTEM_REQUIRED
    except Exception:
        pass


def imprimer(gcode: Path, name: str = "", on_end=None) -> dict:
    """Lance l'impression d'un G-code par le câble, dans un fil à part. on_end(job) est appelé à la fin."""
    if busy():
        return {"ok": False, "why": "Une impression est déjà en cours."}
    pw = check_power()   # câble USB seul : l'écran s'allume mais rien ne chauffe -> on ne lance pas
    if not pw.get("ok"):
        return {"ok": False, "why": pw.get("why", "Imprimante injoignable.")}
    if not pw.get("powered"):
        return {"ok": False, "why": NOT_POWERED, "unpowered": True}
    cmds = _commands(gcode)
    if not cmds:
        return {"ok": False, "why": "Fichier d'impression vide."}
    meta = slice_model(gcode) if gcode.suffix.lower() == ".gcode" else {}
    JOB.clear()
    JOB.update({"state": "printing", "name": name or gcode.stem, "file": str(gcode), "total": len(cmds), "sent": 0,
                "t0": time.time(), "est_s": meta.get("secondes", 0), "cancel": False, "pause": False, "why": ""})
    LOCK_FILE.write_text(json.dumps({"name": JOB["name"], "t0": JOB["t0"], "file": str(gcode)}), encoding="utf-8")
    threading.Thread(target=_stream, args=(cmds, on_end), daemon=True, name="impression-3d").start()
    return {"ok": True}


def _stream(cmds: list[str], on_end) -> None:
    s = None
    _awake(True)
    try:
        with _LOCK:
            s = _open()
            s.timeout = 0.02  # lecture dès que la réponse arrive (sinon 0,3 s perdues par ligne : 45 min de plus sur un cube)
            buf = ""

            def wait_ok(limit: float = 90.0) -> str:
                """Attend « ok » ; renvoie 'ok' ou 'resend:N'. Toute ligne reçue (températures pendant la chauffe) relance le délai."""
                nonlocal buf
                last = time.time()
                while True:
                    chunk = s.read(max(1, s.in_waiting)).decode("utf-8", "ignore")
                    if chunk:
                        buf += chunk
                        last = time.time()
                    while "\n" in buf:
                        line, buf = buf.split("\n", 1)
                        line = line.strip()
                        t = _temps(line)
                        if t:
                            JOB["temps"] = t
                        m = re.match(r"(?i)(resend|rs)[: ]\s*(\d+)", line)
                        if m:
                            return f"resend:{m.group(2)}"
                        if line.startswith("ok"):
                            return "ok"
                        if line.lower().startswith(("error", "!!")) and "checksum" not in line.lower() and "line number" not in line.lower():
                            JOB["why"] = line[:160]
                            if "kill" in line.lower() or "halt" in line.lower() or "thermal" in line.lower():
                                raise RuntimeError(f"L'imprimante s'est arrêtée : {line[:160]}")
                    if time.time() - last > limit:
                        raise RuntimeError("L'imprimante ne répond plus (câble débranché ou imprimante éteinte ?).")

            s.write(_numbered(0, "M110 N0"))
            wait_ok()
            i, last_temp = 0, 0.0
            while i < len(cmds):
                if JOB.get("cancel"):
                    break
                if JOB.get("pause"):
                    JOB["state"] = "paused"
                    time.sleep(0.3)
                    continue
                JOB["state"] = "printing"
                if time.time() - last_temp > 20:  # température toutes les 20 s, sans numéro (n'abîme pas la suite)
                    last_temp = time.time()
                    s.write(b"M105\n")
                    wait_ok()
                n = i + 1
                s.write(_numbered(n, cmds[i]))
                r = wait_ok()
                if r.startswith("resend:"):
                    i = max(0, int(r.split(":")[1]) - 1)
                    continue
                i += 1
                JOB["sent"] = i
            # fin (terminée ou annulée) : la buse remonte un peu au-dessus de la pièce puis revient à son point de départ
            # en X/Y (mise à l'origine X/Y, pas en Z : elle ne redescend jamais sur la pièce), moteurs relâchés
            ending = (("M104 S0", "M140 S0", "M107", "G91", "G1 Z10 F600", "G90", "G28 X Y", "M84") if JOB.get("cancel")
                      else ("M104 S0", "M140 S0", "M107", "G90", "G28 X Y", "M84"))
            for c in ending:
                s.write((c + "\n").encode())
                try:
                    wait_ok(60)
                except Exception:
                    break
            JOB["state"] = "cancelled" if JOB.get("cancel") else "done"
    except Exception as exc:
        JOB["state"], JOB["why"] = "error", str(exc)
        try:  # par sécurité : chauffage coupé si on peut encore parler à l'imprimante
            if s:
                for c in ("M104 S0", "M140 S0"):
                    s.write((c + "\n").encode())
        except Exception:
            pass
    finally:
        JOB["t_end"] = time.time()
        try:
            if s:
                s.close()
        except Exception:
            pass
        _awake(False)
        LOCK_FILE.unlink(missing_ok=True)
        if on_end:
            try:
                on_end(dict(JOB))
            except Exception:
                pass


def pause(on: bool) -> dict:
    if not busy():
        return {"ok": False, "why": "Aucune impression en cours."}
    JOB["pause"] = on
    return {"ok": True}


def annuler() -> dict:
    if not busy():
        return {"ok": False, "why": "Aucune impression en cours."}
    JOB["cancel"], JOB["pause"] = True, False
    return {"ok": True}


def avancement() -> str:
    if not JOB or JOB.get("state") == "idle":
        return ""
    pct = 100 * JOB.get("sent", 0) / max(1, JOB.get("total", 1))
    el = time.time() - JOB.get("t0", time.time())
    rest = ""
    if JOB.get("est_s") and pct > 1:
        left = max(0, JOB["est_s"] * (1 - pct / 100))
        rest = f", environ {int(left // 3600)} h {int(left % 3600 // 60):02d} restantes" if left >= 3600 else f", environ {int(left // 60)} min restantes"
    return f"{JOB.get('name')} : {pct:.0f} % ({int(el // 60)} min écoulées{rest})"


# ---------------------------------------------------------------------------------------------------- fichiers (page Imprimante)

def list_models() -> list[dict]:
    """Modèles dans Documents\\Impressions 3D (les plus récents d'abord), avec la découpe déjà faite s'il y en a une."""
    import datetime as _dt

    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    out = []
    for f in sorted(MODELS_DIR.rglob("*"), key=lambda x: x.stat().st_mtime, reverse=True):
        if f.suffix.lower() not in MODEL_EXTS or not f.is_file():
            continue
        g = f if f.suffix.lower() == ".gcode" else WORK / (re.sub(r"[^\w .-]", "_", f.stem) + ".gcode")
        info = {}
        if g.exists() and g.stat().st_mtime >= f.stat().st_mtime:
            head = g.read_text(encoding="utf-8", errors="ignore")[-20000:]
            tm = re.search(r"estimated printing time \(normal mode\) = (.+)", head)
            gr = re.search(r"filament used \[g\] = ([\d.]+)", head)
            info = {"duree": tm.group(1).strip() if tm else "", "grammes": float(gr.group(1)) if gr else None}
        st = f.stat()
        out.append({"name": f.name, "rel": str(f.relative_to(MODELS_DIR)), "type": f.suffix.lower().lstrip("."), "id": model_id(f),
                    "ko": round(st.st_size / 1024), "date": _dt.datetime.fromtimestamp(st.st_mtime).strftime("%d/%m %H:%M"),
                    **info})
    return out


def model_path(rel: str) -> Path | None:
    """Chemin d'un modèle de la liste, sans jamais sortir du dossier Impressions 3D."""
    p = (MODELS_DIR / rel).resolve()
    try:
        p.relative_to(MODELS_DIR.resolve())
    except ValueError:
        return None
    return p if p.is_file() and p.suffix.lower() in MODEL_EXTS else None


def recycle(p: Path) -> bool:
    """Met un fichier à la CORBEILLE (récupérable), jamais supprimé définitivement."""
    import ctypes
    from ctypes import wintypes

    class SHFILEOPSTRUCTW(ctypes.Structure):
        _fields_ = [("hwnd", wintypes.HWND), ("wFunc", ctypes.c_uint), ("pFrom", ctypes.c_wchar_p),
                    ("pTo", ctypes.c_wchar_p), ("fFlags", ctypes.c_ushort), ("fAnyOperationsAborted", wintypes.BOOL),
                    ("hNameMappings", ctypes.c_void_p), ("lpszProgressTitle", ctypes.c_wchar_p)]

    op = SHFILEOPSTRUCTW(None, 3, str(p) + "\0", None, 0x0040 | 0x0010 | 0x0004 | 0x0400, False, None, None)
    rc = ctypes.windll.shell32.SHFileOperationW(ctypes.byref(op))
    return not rc and not p.exists()


def save_upload(name: str, data: bytes) -> Path | None:
    """Fichier déposé sur la page : rangé dans Impressions 3D (nom nettoyé, jamais écrasé)."""
    base = re.sub(r"[^\w .()-]", "_", Path(name).name).strip() or "modele.stl"
    if Path(base).suffix.lower() not in MODEL_EXTS:
        return None
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    p, k = MODELS_DIR / base, 1
    while p.exists():
        p, k = MODELS_DIR / f"{Path(base).stem} ({k}){Path(base).suffix}", k + 1
    p.write_bytes(data)
    return p


def summary() -> dict:
    """Résumé rapide pour le panneau de gauche (sans ouvrir le port série)."""
    st = JOB.get("state", "idle")
    if busy():
        return {"state": st, "line": avancement()}
    try:
        here = bool(find_port())
    except Exception:
        here = False
    return {"state": st if here else "absent", "line": "Prête" if here else "Non branchée"}


# ---------------------------------------------------------------------------------------------------- visionneuse 3D

def _allowed_dirs() -> list[Path]:
    return [MODELS_DIR.resolve(), (Path.home() / "Downloads").resolve()]


def model_id(p: Path) -> str:
    import base64

    return base64.urlsafe_b64encode(str(p.resolve()).encode("utf-8")).decode().rstrip("=")


def model_from_id(mid: str) -> Path | None:
    """Fichier d'un id de la visionneuse, seulement dans Impressions 3D ou Téléchargements, et seulement un modèle."""
    import base64

    try:
        p = Path(base64.urlsafe_b64decode(mid + "=" * (-len(mid) % 4)).decode("utf-8")).resolve()
    except Exception:
        return None
    if p.suffix.lower() not in MODEL_EXTS or not p.is_file():
        return None
    for d in _allowed_dirs():
        try:
            p.relative_to(d)
            return p
        except ValueError:
            continue
    return None


def keep_in_library(p: Path) -> Path:
    """Modèle pris dans Téléchargements : une copie est rangée dans Impressions 3D (la bibliothèque de la page Imprimante)."""
    import shutil

    try:
        p.resolve().relative_to(MODELS_DIR.resolve())
        return p
    except ValueError:
        pass
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    dst = MODELS_DIR / p.name
    if dst.exists() and dst.stat().st_size == p.stat().st_size:
        return dst
    k = 1
    while dst.exists():
        dst, k = MODELS_DIR / f"{p.stem} ({k}){p.suffix}", k + 1
    shutil.copy2(p, dst)
    return dst


# ---------------------------------------------------------------------------------------------------- plateau à plusieurs objets

BED_CENTER = (115.5, 115.5)   # centre de la zone imprimable du profil (plateau 3..228 mm)
BED_HALF = 110.0              # zone affichée par la visionneuse : 220 × 220 mm centrée


def read_triangles(p: Path):
    """Triangles d'un STL (binaire ou texte) ou d'un OBJ -> tableau numpy (n, 3, 3) en mm."""
    import struct

    import numpy as np

    data = p.read_bytes()
    if p.suffix.lower() == ".stl":
        n = struct.unpack_from("<I", data, 80)[0] if len(data) >= 84 else 0
        if n and 84 + n * 50 == len(data):
            rec = np.frombuffer(data, dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]), count=n, offset=84)
            return rec["v"].astype(np.float64)
        v = re.findall(rb"vertex\s+([-+\deE.]+)\s+([-+\deE.]+)\s+([-+\deE.]+)", data)
        a = np.array(v, dtype=np.float64)
        return a[: len(a) // 3 * 3].reshape(-1, 3, 3)
    if p.suffix.lower() == ".obj":
        vs, faces = [], []
        for line in data.decode("utf-8", "ignore").splitlines():
            t = line.split()
            if not t:
                continue
            if t[0] == "v":
                vs.append([float(t[1]), float(t[2]), float(t[3])])
            elif t[0] == "f":
                ix = [int(x.split("/")[0]) for x in t[1:]]
                ix = [i - 1 if i > 0 else len(vs) + i for i in ix]
                for i in range(1, len(ix) - 1):
                    faces.append([ix[0], ix[i], ix[i + 1]])
        return np.array(vs, dtype=np.float64)[np.array(faces, dtype=np.int64)]
    raise ValueError("Format non pris en charge pour le plateau (STL ou OBJ seulement).")


def build_plate(objects: list[dict]) -> dict:
    """Assemble les objets placés dans la visionneuse en UN fichier STL aux vraies positions du plateau.

    Chaque objet : {id, x, z (décalage dans la visionneuse, mm), rot (radians, autour de la verticale), scale (%)}.
    Repère de la visionneuse : X = X de l'imprimante, Z = -Y de l'imprimante, plateau centré en (0, 0)."""
    import math
    import struct

    import numpy as np

    parts, problems = [], []
    for i, o in enumerate(objects):
        m = model_from_id(str(o.get("id", "")))
        if not m:
            return {"ok": False, "why": f"Objet {i + 1} introuvable."}
        t = read_triangles(m)
        if not len(t):
            return {"ok": False, "why": f"{m.name} est vide."}
        flat = t.reshape(-1, 3)
        lo, hi = flat.min(axis=0), flat.max(axis=0)
        c = np.array([(lo[0] + hi[0]) / 2, (lo[1] + hi[1]) / 2, lo[2]])
        k = max(0.1, min(5.0, float(o.get("scale", 100)) / 100))
        a = float(o.get("rot", 0))
        ca, sa = math.cos(a), math.sin(a)
        q = (flat - c) * k
        x = ca * q[:, 0] - sa * q[:, 1] + BED_CENTER[0] + float(o.get("x", 0))
        y = sa * q[:, 0] + ca * q[:, 1] + BED_CENTER[1] - float(o.get("z", 0))
        out = np.stack([x, y, q[:, 2]], axis=1)
        x0, y0, x1, y1 = out[:, 0].min(), out[:, 1].min(), out[:, 0].max(), out[:, 1].max()
        if (x0 < BED_CENTER[0] - BED_HALF - 0.5 or x1 > BED_CENTER[0] + BED_HALF + 0.5
                or y0 < BED_CENTER[1] - BED_HALF - 0.5 or y1 > BED_CENTER[1] + BED_HALF + 0.5 or out[:, 2].max() > 250):
            problems.append(f"{m.name} dépasse du plateau")
        parts.append(out.reshape(-1, 3, 3))
    tri = np.concatenate(parts).astype(np.float32)
    if problems:
        return {"ok": False, "why": " ; ".join(problems) + "."}
    WORK.mkdir(parents=True, exist_ok=True)
    path = WORK / "plateau.stl"
    nrm = np.cross(tri[:, 1] - tri[:, 0], tri[:, 2] - tri[:, 0])
    nrm /= np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    rec = np.zeros(len(tri), dtype=np.dtype([("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")]))
    rec["n"], rec["v"] = nrm, tri
    with open(path, "wb") as f:
        f.write(b"plateau JARVIS".ljust(80, b" "))
        f.write(struct.pack("<I", len(tri)))
        f.write(rec.tobytes())
    return {"ok": True, "path": path, "objects": len(objects), "triangles": int(len(tri))}


_DL_CACHE: dict = {"t": 0.0, "v": []}


def list_downloads(limit: int = 80) -> list[dict]:
    """Modèles 3D du dossier Téléchargements (les plus récents d'abord), pour les ajouter au plateau sans les déplacer.
    Gardé 30 s (Téléchargements contient des milliers de fichiers : 0,4 s à parcourir)."""
    import datetime as _dt

    if time.time() - _DL_CACHE["t"] < 30:
        return _DL_CACHE["v"]

    d = Path.home() / "Downloads"
    out = []
    try:
        files = [f for f in d.rglob("*") if f.is_file() and f.suffix.lower() in (".stl", ".obj", ".3mf")]
    except Exception:
        files = []
    for f in sorted(files, key=lambda x: x.stat().st_mtime, reverse=True)[:limit]:
        st = f.stat()
        out.append({"name": f.name, "type": f.suffix.lower().lstrip("."), "id": model_id(f), "ko": round(st.st_size / 1024),
                    "date": _dt.datetime.fromtimestamp(st.st_mtime).strftime("%d/%m %H:%M")})
    _DL_CACHE.update(t=time.time(), v=out)
    return out


# ---------------------------------------------------------------------------------------------------- vue 3D en direct

_TP_CACHE: dict = {}


def toolpath(gcode: Path, max_seg: int = 700_000) -> bytes:
    """Trajet d'extrusion d'un G-code pour la vue en direct : [n (uint32)] [n × 6 float32 : x0 y0 z0 x1 y1 z1]
    [n × uint32 : numéro de commande]. Les numéros sont ceux de _commands (= JOB['sent']) : la page sait ainsi
    exactement quelle partie est déjà imprimée. Gardé en mémoire tant que le fichier ne change pas."""
    import struct

    import numpy as np

    key = (str(gcode), gcode.stat().st_mtime)
    if key in _TP_CACHE:
        return _TP_CACHE[key]
    cmds = _commands(gcode)
    x = y = z = e = 0.0
    abs_xyz, abs_e = True, True
    seg, idx = [], []
    num = re.compile(r"([XYZEF])(-?[\d.]+)")
    for i, c in enumerate(cmds):
        up = c.upper()
        if up.startswith(("G0", "G1")) and (len(up) == 2 or not up[2].isdigit()):
            v = {k: float(n) for k, n in num.findall(up)}
            nx = (v["X"] if abs_xyz else x + v["X"]) if "X" in v else x
            ny = (v["Y"] if abs_xyz else y + v["Y"]) if "Y" in v else y
            nz = (v["Z"] if abs_xyz else z + v["Z"]) if "Z" in v else z
            ext = False
            if "E" in v:
                ext = (v["E"] > e + 1e-6) if abs_e else v["E"] > 1e-6
                e = v["E"] if abs_e else e
            if ext and (nx != x or ny != y):
                seg.append((x, y, z, nx, ny, nz))
                idx.append(i)
            x, y, z = nx, ny, nz
        elif up.startswith("G90"):
            abs_xyz = True
        elif up.startswith("G91"):
            abs_xyz = False
        elif up.startswith("M82"):
            abs_e = True
        elif up.startswith("M83"):
            abs_e = False
        elif up.startswith("G92"):
            v = {k: float(n) for k, n in num.findall(up)}
            if "E" in v:
                e = v["E"]
    a = np.array(seg, dtype=np.float32).reshape(-1, 6)
    b = np.array(idx, dtype=np.uint32)
    if len(a) > max_seg:  # très grosse pièce : un segment sur k (la forme reste lisible)
        k = int(np.ceil(len(a) / max_seg))
        a, b = a[::k], b[::k]
    out = struct.pack("<I", len(a)) + a.tobytes() + b.tobytes()
    _TP_CACHE.clear()
    _TP_CACHE[key] = out
    return out


def origine() -> dict:
    """Ramène la buse à sa position de départ : elle remonte de 1 cm (jamais contre la pièce), puis mise à l'origine X/Y
    (le coin de départ) ; moteurs relâchés ensuite. Refusé pendant une impression."""
    try:
        _talk(["G91", "G1 Z10 F600", "G90", "G28 X Y", "M84"], timeout=60)
    except Exception as exc:
        return {"ok": False, "why": str(exc)}
    return {"ok": True}


def toolpath2(gcode: Path) -> bytes:
    """Trajet COMPLET pour la vue en direct animée (format « TP2 ») : tous les mouvements (extrusion ET déplacements à
    vide), chacun avec sa durée estimée (vitesse F, accélération M204) pour animer la buse à vitesse réelle.
    [b'TP2\0'][n uint32][n × 6 float32 : x0 y0 z0 x1 y1 z1][n × uint32 : numéro de commande][n × float32 : durée (s)]
    [n × uint8 : 1 = extrusion]. Les numéros sont ceux de _commands (= JOB['sent'])."""
    import math
    import struct

    import numpy as np

    key = ("tp2", str(gcode), gcode.stat().st_mtime)
    if key in _TP_CACHE:
        return _TP_CACHE[key]
    cmds = _commands(gcode)
    x = y = z = e = 0.0
    f = 1500.0       # mm/min
    acc = 500.0      # mm/s²
    abs_xyz, abs_e = True, True
    seg, idx, dur, ext = [], [], [], []
    num = re.compile(r"([XYZEFS])(-?[\d.]+)")
    for i, c in enumerate(cmds):
        up = c.upper()
        if up.startswith(("G0", "G1")) and (len(up) == 2 or not up[2].isdigit()):
            v = {k: float(n) for k, n in num.findall(up)}
            if "F" in v and v["F"] > 0:
                f = v["F"]
            nx = (v["X"] if abs_xyz else x + v["X"]) if "X" in v else x
            ny = (v["Y"] if abs_xyz else y + v["Y"]) if "Y" in v else y
            nz = (v["Z"] if abs_xyz else z + v["Z"]) if "Z" in v else z
            is_ext = False
            if "E" in v:
                is_ext = (v["E"] > e + 1e-6) if abs_e else v["E"] > 1e-6
                e = v["E"] if abs_e else e
            d = math.sqrt((nx - x) ** 2 + (ny - y) ** 2 + (nz - z) ** 2)
            if d > 1e-6:
                vel = max(1.0, f / 60.0)
                t = 2 * math.sqrt(d / acc) if d < vel * vel / acc else d / vel + vel / acc
                seg.append((x, y, z, nx, ny, nz))
                idx.append(i)
                dur.append(t)
                ext.append(1 if (is_ext and (nx != x or ny != y)) else 0)
            x, y, z = nx, ny, nz
        elif up.startswith("G90"):
            abs_xyz = True
        elif up.startswith("G91"):
            abs_xyz = False
        elif up.startswith("M82"):
            abs_e = True
        elif up.startswith("M83"):
            abs_e = False
        elif up.startswith("M204"):
            v = {k: float(n) for k, n in num.findall(up)}
            if v.get("S", 0) > 0:
                acc = v["S"]
        elif up.startswith("G92"):
            v = {k: float(n) for k, n in num.findall(up)}
            if "E" in v:
                e = v["E"]
    n = len(seg)
    out = (b"TP2\0" + struct.pack("<I", n) + np.array(seg, dtype=np.float32).reshape(-1, 6).tobytes()
           + np.array(idx, dtype=np.uint32).tobytes() + np.array(dur, dtype=np.float32).tobytes()
           + np.array(ext, dtype=np.uint8).tobytes())
    _TP_CACHE.clear()
    _TP_CACHE[key] = out
    return out


def check_power(seconds: float = 12.0) -> dict:
    """L'alimentation (interrupteur) est-elle allumée ? Câble USB seul, la carte répond et l'écran s'allume, mais rien ne
    chauffe. Test : la buse vise brièvement 80 °C (au-dessus de sa température actuelle) ; si elle prend au moins 2 °C en
    ~12 s, le chauffage marche. Le chauffage est coupé ensuite (bien avant la sécurité du firmware, qui stoppe la carte
    si la buse ne chauffe pas en 20 s)."""
    if busy():
        return {"ok": True, "powered": True, "why": "impression en cours"}
    import serial  # noqa: F401  (même dépendance que le reste)

    try:
        t0 = _temps(_talk(["M105"], settle=0.05))
        if not t0:
            return {"ok": False, "why": "L'imprimante n'a pas répondu."}
        start = t0["buse"]
        target = int(min(250, max(80, start + 15)))   # buse déjà chaude : on vise un peu au-dessus
        with _LOCK:
            s = _open()
            try:
                def cmd(c: str) -> str:
                    s.write((c + "\n").encode())
                    got, t_end = "", time.time() + 3
                    while time.time() < t_end:
                        got += s.read(256).decode("utf-8", "ignore")
                        if re.search(r"(^|\n)ok\b", got):
                            break
                    return got

                cmd(f"M104 S{target}")
                best, t_end = start, time.time() + seconds
                while time.time() < t_end:
                    time.sleep(1.0)
                    t = _temps(cmd("M105"))
                    if t:
                        best = max(best, t["buse"])
                    if best - start >= 2.0:
                        break
            finally:
                try:
                    s.write(b"M104 S0\n")
                    time.sleep(0.2)
                finally:
                    s.close()
        rise = round(best - start, 1)
        return {"ok": True, "powered": rise >= 2.0, "rise": rise, "start": start}
    except Exception as exc:
        return {"ok": False, "why": str(exc)}


NOT_POWERED = ("L'imprimante n'est pas alimentée : l'écran s'allume grâce au câble USB, mais le chauffage ne marche pas. "
               "Allume l'interrupteur de l'imprimante (à l'arrière, sur le bloc d'alimentation), puis relance.")
