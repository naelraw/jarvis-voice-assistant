"""Améliorations de JARVIS demandées le 2026-10-26 (« vas-y, ajoute tout ») :

 1. Tableau de bord de jeu sur la tablette : stats du PC (processeur, carte graphique, mémoire, ping), partie en
    cours, clips, musique — page « Jeu » du tableau de bord + /api/jeu.
 2. Résumé de partie : existait déjà (_game_sessions) ; resume_jeu le donne à la demande.
 3. Best-of de la semaine : les clips des 7 derniers jours assemblés en une vidéo (FFmpeg), le dimanche soir.
 4. Surveillance de l'impression 3D par la webcam : un raté visible -> pause + alerte.
 5. Missions automatiques des agents IA (chaque jour / certains jours à une heure).
 6. Agent « Clips & vidéos » dans l'équipe.
 7. Briefing du matin (premier réveil de la journée) : voir jarvis_voice.briefing_prompt.
 8. Routine du soir : « bonne nuit Jarvis ».
 9. Surveillance de la tablette : Apollo filme le mauvais écran -> alerte.
10. Contrôle de santé quotidien : JARVIS ne parle que si quelque chose cloche.

Tout est gratuit et local (sauf Gemini pour la vision et les agents, déjà utilisés).
"""
from __future__ import annotations

import ctypes
import datetime as dt
import json
import re
import subprocess
import threading
import time
from ctypes import wintypes
from pathlib import Path

J = None  # module jarvis_voice


def _cfg(key: str, default=True):
    return J.CFG.get(key, default)


def _say(text: str, push: bool = False) -> None:
    """Annonce : dite tout de suite, ou gardée pour la prochaine ouverture (pause, jeu, fenêtre fermée)."""
    J.log.info("Amélioration : %s", text[:200])
    if push:
        try:
            J.mobile_push("🔔 " + text)
        except Exception:
            pass
    J._say_later(text)


# ---------------------------------------------------------------------------------------------------------------
# 1. statistiques du PC pour le tableau de bord de jeu (compteurs Windows, sans rien installer)
# ---------------------------------------------------------------------------------------------------------------

class _Pdh:
    """Compteurs de performance Windows (pdh.dll) : usage de la carte graphique et de sa mémoire."""

    def __init__(self) -> None:
        self.pdh = ctypes.WinDLL("pdh")
        self.q = ctypes.c_void_p()
        self.pdh.PdhOpenQueryW(None, None, ctypes.byref(self.q))
        self.c = {}
        for key, path in (("gpu", r"\GPU Engine(*engtype_3D)\Utilization Percentage"),
                          ("vram", r"\GPU Adapter Memory(*)\Dedicated Usage")):
            h = ctypes.c_void_p()
            if self.pdh.PdhAddEnglishCounterW(self.q, path, None, ctypes.byref(h)) == 0:
                self.c[key] = h
        self.pdh.PdhCollectQueryData(self.q)

    def read(self) -> dict:
        self.pdh.PdhCollectQueryData(self.q)
        out = {}

        class FMT(ctypes.Structure):
            _fields_ = [("CStatus", wintypes.DWORD), ("pad", wintypes.DWORD), ("doubleValue", ctypes.c_double)]

        class ITEM(ctypes.Structure):
            _fields_ = [("szName", ctypes.c_wchar_p), ("FmtValue", FMT)]

        for key, h in self.c.items():
            size, count = wintypes.DWORD(0), wintypes.DWORD(0)
            self.pdh.PdhGetFormattedCounterArrayW(h, 0x00000200, ctypes.byref(size), ctypes.byref(count), None)
            if not size.value:
                continue
            buf = (ctypes.c_byte * size.value)()
            if self.pdh.PdhGetFormattedCounterArrayW(h, 0x00000200, ctypes.byref(size), ctypes.byref(count), buf):
                continue
            items = ctypes.cast(buf, ctypes.POINTER(ITEM))
            vals = [items[i].FmtValue.doubleValue for i in range(count.value)]
            out[key] = sum(vals) if key == "gpu" else max(vals or [0])
        return out


_STATS: dict = {"t": 0.0, "v": {}, "pdh": None, "ping": None, "ping_t": 0.0, "asked": 0.0}


def _ping() -> float | None:
    try:
        r = subprocess.run(["ping", "-n", "1", "-w", "1000", "1.1.1.1"], capture_output=True, text=True,
                           encoding="cp850", errors="ignore", timeout=3, creationflags=0x08000000)
        m = re.search(r"[=<]\s*(\d+)\s*ms", r.stdout)
        return float(m.group(1)) if m else None
    except Exception:
        return None


def pc_stats() -> dict:
    import psutil

    now = time.time()
    _STATS["asked"] = now
    if now - _STATS["t"] < 1.5:
        return _STATS["v"]
    v = {"cpu": round(psutil.cpu_percent(None)), "ram": round(psutil.virtual_memory().percent),
         "ram_go": round(psutil.virtual_memory().used / 2**30, 1), "ram_tot": round(psutil.virtual_memory().total / 2**30)}
    try:
        if _STATS["pdh"] is None:
            _STATS["pdh"] = _Pdh()
        g = _STATS["pdh"].read()
        v["gpu"] = round(min(100.0, g.get("gpu", 0)))
        v["vram_go"] = round(g.get("vram", 0) / 2**30, 1)
    except Exception as exc:
        J.log.info("Compteurs carte graphique indisponibles : %s", exc)
    if now - _STATS["ping_t"] > 5:
        _STATS["ping_t"] = now
        threading.Thread(target=lambda: _STATS.__setitem__("ping", _ping()), daemon=True).start()
    v["ping"] = _STATS["ping"]
    _STATS["t"], _STATS["v"] = now, v
    return v


def jeu_state() -> dict:
    """Tout ce que la page « Jeu » affiche."""
    sess, games = _session()
    clips = _clips_since(sess) if sess else []
    return {"ok": True, "stats": pc_stats(), "games": games, "session_min": round((time.time() - sess) / 60) if sess else 0,
            "clips": len(clips), "last_clip": clips[0].stem if clips else "", "now": time.time()}


# ---------------------------------------------------------------------------------------------------------------
# 2. résumé de partie
# ---------------------------------------------------------------------------------------------------------------

def _session() -> tuple[float, list[str]]:
    """Partie en cours d'après JARVIS (début, jeux) ; le résumé de fin de partie existe déjà dans _game_sessions."""
    g = dict(J._SESSION.get("games") or {})
    return (min(g.values()) if g else 0.0), sorted(g)


def _clips_since(t0: float) -> list[Path]:
    return [f for f in J._clip_files(200) if f.stat().st_mtime >= t0 and not f.name.lower().startswith("capture")]


def _fmt_dur(sec: float) -> str:
    m = int(sec // 60)
    return f"{m // 60} h {m % 60:02d}" if m >= 60 else f"{m} minute{'s' if m > 1 else ''}"


def resume_jeu() -> str:
    """Résumé de la partie en cours ou de la journée de jeu."""
    start, names = _session()
    if start:
        clips = _clips_since(start)
        return f"Partie en cours sur {', '.join(names)} depuis {_fmt_dur(time.time() - start)}, {len(clips)} clip(s)."
    today = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    clips = _clips_since(today)
    return f"Aucune partie en cours. Aujourd'hui : {len(clips)} clip(s)."


# ---------------------------------------------------------------------------------------------------------------
# 3. best-of de la semaine (FFmpeg, gratuit)
# ---------------------------------------------------------------------------------------------------------------

BEST_DIR = Path.home() / "Videos" / "Best-of JARVIS"


def best_of_semaine(jours: str = "7") -> str:
    """Assemble les fins de clips des derniers jours (les 15 dernières secondes de chacun, là où est l'action)."""
    import imageio_ffmpeg

    try:
        n = max(1, min(31, int(re.search(r"\d+", str(jours)).group())))
    except Exception:
        n = 7
    t0 = time.time() - n * 86400
    clips = sorted(_clips_since(t0), key=lambda f: f.stat().st_mtime)[-40:]
    clips = [f for f in clips if f.suffix.lower() in (".mp4", ".mkv", ".mov")]
    if not clips:
        return f"Aucun clip ces {n} derniers jours : pas de best-of."
    BEST_DIR.mkdir(parents=True, exist_ok=True)
    out = BEST_DIR / f"Best-of {dt.date.today():%Y-%m-%d}.mp4"
    exe = imageio_ffmpeg.get_ffmpeg_exe()
    tmp = BEST_DIR / "_parts"
    tmp.mkdir(exist_ok=True)
    parts = []
    for i, f in enumerate(clips):
        p = tmp / f"{i:03d}.mp4"
        r = subprocess.run([exe, "-y", "-loglevel", "error", "-sseof", "-15", "-i", str(f),
                            "-vf", "scale=1920:1080:force_original_aspect_ratio=decrease,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,fps=60",
                            "-c:v", "libx264", "-preset", "veryfast", "-crf", "22", "-pix_fmt", "yuv420p",
                            "-c:a", "aac", "-ar", "48000", "-ac", "2", "-b:a", "160k", str(p)],
                           capture_output=True, timeout=600, creationflags=0x08000000 | 0x00004000)
        if r.returncode == 0 and p.exists():
            parts.append(p)
    if not parts:
        return "Le best-of n'a pas pu être créé (conversion des clips impossible)."
    lst = tmp / "liste.txt"
    lst.write_text("".join(f"file '{p.as_posix()}'\n" for p in parts), encoding="utf-8")
    r = subprocess.run([exe, "-y", "-loglevel", "error", "-f", "concat", "-safe", "0", "-i", str(lst), "-c", "copy",
                        "-movflags", "+faststart", str(out)], capture_output=True, timeout=600, creationflags=0x08000000)
    for p in parts + [lst]:
        p.unlink(missing_ok=True)
    try:
        tmp.rmdir()
    except OSError:
        pass
    if r.returncode or not out.exists():
        return "Le best-of n'a pas pu être assemblé."
    J.log.info("Best-of : %s (%d clips)", out, len(parts))
    return f"Best-of créé avec {len(parts)} clips : « {out.name} », dans Vidéos > Best-of JARVIS."


# ---------------------------------------------------------------------------------------------------------------
# 4. surveillance de l'impression par la webcam
# ---------------------------------------------------------------------------------------------------------------

_PRINT_WATCH: dict = {"last": 0.0, "fails": 0, "no_view": 0.0}


def _print_watch() -> None:
    import imprimante3d as ip

    while True:
        time.sleep(30)
        try:
            if not _cfg("print_watch") or not ip.busy() or not J.gemini_key():
                _PRINT_WATCH["fails"] = 0
                continue
            if time.time() - _PRINT_WATCH["last"] < 300:
                continue
            _PRINT_WATCH["last"] = time.time()
            if J._WEBCAM["live"] or not J._WEBCAM["lock"].acquire(blocking=False):
                continue  # webcam déjà utilisée
            try:
                cap = J._webcam_open()
                img = J._webcam_image(cap) if cap is not None else None
                if cap is not None:
                    cap.release()
            finally:
                J._WEBCAM["lock"].release()
            if img is None:
                continue
            ans = J.gemini_vision(
                "Photo d'une imprimante 3D (Ender 3) pendant une impression. Réponds par UN mot puis une courte raison : "
                "OK (impression normale), RATE (fils emmêlés « spaghetti », pièce décollée ou déplacée, buse qui imprime "
                "dans le vide, gros amas de plastique) ou INVISIBLE (on ne voit pas l'impression sur la photo).", img)
            word = (ans or "").strip().split()[0].upper().strip(".,:") if ans else ""
            J.log.info("Surveillance impression : %s", (ans or "")[:120])
            if word == "INVISIBLE":
                if time.time() - _PRINT_WATCH["no_view"] > 6 * 3600:
                    _PRINT_WATCH["no_view"] = time.time()
                    J.log.info("Surveillance impression : la webcam ne voit pas l'imprimante (tourne-la vers elle)")
                continue
            if word.startswith("RAT"):
                _PRINT_WATCH["fails"] += 1
                if _PRINT_WATCH["fails"] >= 2:  # deux photos d'affilée : on ne coupe pas sur une seule image douteuse
                    _PRINT_WATCH["fails"] = 0
                    ip.pause()
                    _say("Impression mise en pause : la webcam voit un raté (" + (ans or "")[:120] + "). Va vérifier.", push=True)
                else:
                    _PRINT_WATCH["last"] = time.time() - 240  # nouvelle photo dans 1 minute pour confirmer
            else:
                _PRINT_WATCH["fails"] = 0
        except Exception:
            J.log.exception("Surveillance de l'impression")


# ---------------------------------------------------------------------------------------------------------------
# 5. missions automatiques des agents
# ---------------------------------------------------------------------------------------------------------------

MISSIONS_FILE = None
_DAYS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]


def _missions() -> list[dict]:
    try:
        return json.loads(MISSIONS_FILE.read_text(encoding="utf-8"))
    except Exception:
        return []


def _save_missions(m: list[dict]) -> None:
    MISSIONS_FILE.write_text(json.dumps(m, ensure_ascii=False, indent=1), encoding="utf-8")


def _parse_when(quand: str) -> tuple[list[int], str] | None:
    q = J.norm(quand or "")
    m = re.search(r"(\d{1,2})\s*(?:h|heures?|:)\s*(\d{2})?", q)
    hour = f"{int(m.group(1)):02d}:{int(m.group(2) or 0):02d}" if m else ("08:00" if "matin" in q else "20:00" if "soir" in q
                                                                          else "13:00" if "midi" in q else "")
    if not hour:
        return None
    days = [i for i, d in enumerate(_DAYS) if d in q]
    if "semaine" in q and not days and "chaque semaine" not in q:
        days = [0, 1, 2, 3, 4]
    if "week end" in q or "weekend" in q:
        days = [5, 6]
    return (days or list(range(7))), hour


def mission_planifiee(action: str = "liste", tache: str = "", quand: str = "", numero: str = "", agents: str = "") -> str:
    """Missions automatiques de l'équipe d'agents : ajoute, liste, supprime."""
    a = J.norm(action or "liste")
    ms = _missions()
    if "ajout" in a or "cree" in a or "planifi" in a:
        when = _parse_when(quand)
        if not (tache or "").strip() or not when:
            return "Il faut la tâche ET le moment (ex. « chaque matin à 8 h », « chaque lundi à 9 h »)."
        days, hour = when
        ms.append({"id": int(time.time()), "tache": tache.strip()[:300], "jours": days, "heure": hour,
                   "agents": agents or "", "last": ""})
        _save_missions(ms)
        jours = "tous les jours" if len(days) == 7 else ", ".join(_DAYS[d] for d in days)
        return f"Mission planifiée : « {tache.strip()[:80]} », {jours} à {hour}. Le rapport sera annoncé et visible dans l'onglet Agents."
    if "suppr" in a or "enleve" in a or "annule" in a:
        k = int(re.search(r"\d+", str(numero)).group()) if re.search(r"\d+", str(numero)) else 0
        if not (1 <= k <= len(ms)):
            return "Quel numéro ? " + mission_planifiee("liste")
        gone = ms.pop(k - 1)
        _save_missions(ms)
        return f"Mission « {gone['tache'][:60]} » supprimée."
    if not ms:
        return "Aucune mission automatique."
    return "Missions : " + " ; ".join(
        f"{i + 1}. {m['tache'][:60]} ({'tous les jours' if len(m['jours']) == 7 else ', '.join(_DAYS[d] for d in m['jours'])} à {m['heure']})"
        for i, m in enumerate(ms))


def _missions_loop() -> None:
    while True:
        time.sleep(30)
        try:
            now = dt.datetime.now()
            if J.STATE.sleeping or J._running_games():
                continue  # pas pendant une partie : la mission part à la fin du jeu (si elle a moins de 3 h de retard)
            ms = _missions()
            changed = False
            for m in ms:
                key = now.strftime("%Y-%m-%d")
                if now.weekday() in m["jours"] and now.strftime("%H:%M") >= m["heure"] and m.get("last") != key:
                    hh, mm = map(int, m["heure"].split(":"))
                    if (now - now.replace(hour=hh, minute=mm, second=0)).total_seconds() > 3 * 3600:
                        m["last"] = key  # PC éteint à l'heure prévue : on ne rattrape pas une mission de plus de 3 h
                        changed = True
                        continue
                    m["last"], changed = key, True
                    keys = [k for k in re.findall(r"[a-z]+", J.norm(m.get("agents") or "")) if k in J.agents_ia.AGENTS]
                    J.log.info("Mission automatique : %s", m["tache"][:80])
                    threading.Thread(target=J.agents_ia.run_boss, args=(m["tache"], keys or None, J._agents_announce),
                                     daemon=True, name="mission-auto").start()
            if changed:
                _save_missions(ms)
        except Exception:
            J.log.exception("Missions automatiques")


# ---------------------------------------------------------------------------------------------------------------
# 8. routine du soir
# ---------------------------------------------------------------------------------------------------------------

def bonne_nuit() -> str:
    """« Bonne nuit Jarvis » : bilan de la journée et programme de demain."""
    bits = []
    today = dt.datetime.combine(dt.date.today(), dt.time()).timestamp()
    clips = _clips_since(today)
    if clips:
        bits.append(f"{len(clips)} clip(s) aujourd'hui")
    try:
        bits.append("Demain : " + str(J.agenda("demain"))[:400])
    except Exception:
        pass
    try:
        rem = [r for r in J._dash_reminders(20) if r.get("day") == "Demain"]
        if rem:
            bits.append("Rappels de demain : " + "; ".join(f"{r['time']} {r['text']}" for r in rem[:5]))
    except Exception:
        pass
    try:
        import imprimante3d as ip
        if ip.busy():
            bits.append("Une impression 3D est encore en cours : " + str(ip.avancement())[:120])
    except Exception:
        pass
    return ("Routine du soir. Dis bonne nuit chaleureusement, puis résume en 2 ou 3 phrases : " + " | ".join(bits)
            + ". Demande ensuite s'il veut que tu mettes le PC en veille ou que tu l'éteignes (system_action, avec "
            "confirmation) — SAUF si une impression est en cours : dans ce cas conseille de laisser le PC allumé.")


# ---------------------------------------------------------------------------------------------------------------
# 9. surveillance de la tablette (Apollo) et 10. contrôle de santé quotidien
# ---------------------------------------------------------------------------------------------------------------

APOLLO_LOG = Path(r"C:\Program Files\Apollo\config\sunshine.log")


def _apollo_watch() -> None:
    pos, warned = 0, 0.0
    try:
        pos = APOLLO_LOG.stat().st_size
    except Exception:
        pass
    while True:
        time.sleep(20)
        try:
            size = APOLLO_LOG.stat().st_size
            if size < pos:
                pos = 0  # journal recommencé (Apollo redémarré)
            if size == pos:
                continue
            with open(APOLLO_LOG, encoding="utf-8", errors="ignore") as f:
                f.seek(pos)
                new = f.read()
            pos = size
            if "Virtual Display creation failed" in new and time.time() - warned > 600 and _cfg("tablet_watch"):
                warned = time.time()
                _say("La tablette risque d'afficher ton écran principal au lieu du sien : Apollo n'a pas créé l'écran "
                     "virtuel. Sur la tablette, dans Artemis, fais un appui long sur « Desktop », « Quitter la session », "
                     "puis relance-le.", push=True)
        except Exception:
            pass


def _health_daily() -> None:
    while True:
        time.sleep(300)
        try:
            now = dt.datetime.now()
            st = J._load_state()
            if (not _cfg("daily_health") or now.hour < 10 or st.get("health_day") == now.strftime("%Y-%m-%d")
                    or J.STATE.sleeping or J._running_games()):
                continue
            st["health_day"] = now.strftime("%Y-%m-%d")
            J._save_state(st)
            rows = J.health_report()
            bad = [f"{n} : {d}" for n, ok, d in rows if not ok and n not in ("Écran de la tablette", "Tablette en USB",
                                                                           "Démarrage de la tablette", "Fenêtre JARVIS")]
            try:  # relevé des prix PC Radar : arrêté alors qu'on ne joue pas ?
                rv = J._RELEVE
                if J.CFG.get("pcradar_releve", True) and J._pcradar() and rv.get("t") and time.time() - rv["t"] > 1800:
                    bad.append(f"Relevé des prix PC Radar : aucune fiche lue depuis {int((time.time() - rv['t']) / 60)} min ({rv.get('etat')})")
            except Exception:
                pass
            J.log.info("Contrôle de santé du jour : %s", "; ".join(bad) or "tout va bien")
            if bad:
                _say("Contrôle du jour : " + " ; ".join(bad[:3]) + ".")
        except Exception:
            J.log.exception("Contrôle de santé quotidien")


def _bestof_weekly() -> None:
    while True:
        time.sleep(600)
        try:
            now = dt.datetime.now()
            st = J._load_state()
            wk = now.strftime("%G-%V")
            if (not _cfg("weekly_bestof") or now.weekday() != 6 or now.hour < 20 or st.get("bestof_week") == wk
                    or J._running_games()):
                continue
            st["bestof_week"] = wk
            J._save_state(st)
            res = best_of_semaine("7")
            if "créé" in res:
                _say(res)
        except Exception:
            J.log.exception("Best-of de la semaine")


# ---------------------------------------------------------------------------------------------------------------
# 11. modes automatiques (2026-10-26) : film / série devant -> JARVIS se met en pause tout seul, et reprend après
# ---------------------------------------------------------------------------------------------------------------

VIDEO_RE = re.compile(r"netflix|prime video|disney\+|crunchyroll|canal\+|mycanal|molotov|arte\.tv|france\.tv|tf1\+|m6\+|"
                      r"apple tv|paramount\+", re.I)
FULLSCREEN_VIDEO_RE = re.compile(r"youtube|twitch|vimeo|dailymotion|kick", re.I)
_AUTO: dict = {"cinema": False, "since": 0.0, "last_seen": 0.0, "auto_paused": False, "suppressed": False}


def _video_context() -> str:
    """'' ou le nom du site vidéo regardé : plateforme de films / séries au premier plan, ou vidéo en plein écran."""
    try:
        fg = J.user32.GetForegroundWindow()
        if not fg or fg == J._jarvis_hwnd():
            return ""
        buf = ctypes.create_unicode_buffer(300)
        J.user32.GetWindowTextW(fg, buf, 300)
        title = buf.value
        m = VIDEO_RE.search(title)
        if m:
            return m.group(0)
        if J._fullscreen_app():
            m = FULLSCREEN_VIDEO_RE.search(title)
            if m:
                return m.group(0) + " (plein écran)"
    except Exception:
        pass
    return ""


def _mark_auto_pause(on: bool) -> None:
    """La pause est gardée après une relance de JARVIS : on note qu'elle vient du mode cinéma, pour la lever ensuite."""
    try:
        st = J._load_state()
        st["auto_pause"] = on
        J._save_state(st)
    except Exception:
        pass


def _auto_mode_loop() -> None:
    try:  # relancé pendant un film : la pause automatique sera levée 45 s après la fin de la vidéo
        if J._load_state().get("auto_pause") and J.STATE.paused:
            _AUTO.update(cinema=True, auto_paused=True, last_seen=time.time())
    except Exception:
        pass
    while True:
        time.sleep(3)
        try:
            if not _cfg("auto_modes") or J.STATE.sleeping or J._running_games():
                continue  # le jeu a déjà son mode automatique (veille, optimisation, tablette)
            now, site = time.time(), _video_context()
            if site:
                _AUTO["last_seen"] = now
                if not _AUTO["cinema"]:
                    _AUTO["since"] = _AUTO["since"] or now
                    if now - _AUTO["since"] >= 4:  # vraiment en train de regarder (pas un simple passage sur l'onglet)
                        _AUTO["cinema"] = True
                        if not J.STATE.paused and not _AUTO["suppressed"]:
                            J.log.info("Mode cinéma automatique (%s) : JARVIS se met en pause", site)
                            J.set_paused(True, announce=False)
                            _AUTO["auto_paused"] = True
                            _mark_auto_pause(True)
                elif _AUTO["auto_paused"] and not J.STATE.paused:
                    # « Jarvis, reprends » pendant le film : on le laisse actif jusqu'à la fin de cette séance
                    _AUTO.update(auto_paused=False, suppressed=True)
                    _mark_auto_pause(False)
                    J.log.info("Mode cinéma : repris à la main, plus de pause automatique pour cette séance")
                continue
            _AUTO["since"] = 0.0
            if _AUTO["cinema"] and now - _AUTO["last_seen"] > 45:  # plus de vidéo depuis 45 s : fin de la séance
                _AUTO["cinema"] = False
                _AUTO["suppressed"] = False
                if _AUTO["auto_paused"] and J.STATE.paused:
                    J.log.info("Fin du mode cinéma : JARVIS reprend tout seul")
                    J.set_paused(False, announce=False)
                _AUTO["auto_paused"] = False
                _mark_auto_pause(False)
        except Exception:
            J.log.exception("Modes automatiques")


def setup(module) -> None:
    global J, MISSIONS_FILE
    J = module
    MISSIONS_FILE = J.CONF_DIR / "jarvis_missions.json"
    # 6. agent « Clips & vidéos » dans l'équipe
    J.agents_ia.AGENTS["clips"] = {
        "name": "Clips & vidéos", "icon": "film", "color": "#ff6bcb",
        "desc": "Clips de jeu, résumé des parties, best-of",
        "tools": ["resume_jeu", "best_of_semaine", "clip_to_phone"],
        "prompt": "Tu es le spécialiste CLIPS & VIDÉOS : clips de jeu enregistrés par OBS, résumé des parties, best-of "
                  "des meilleurs moments. Tu peux créer un best-of et envoyer un clip sur le téléphone de l'utilisateur.",
    }


def start() -> None:
    for fn, name in ((_print_watch, "surveillance-impression"), (_missions_loop, "missions"), (_auto_mode_loop, "modes-auto"),
                     (_apollo_watch, "surveillance-tablette"), (_health_daily, "sante-quotidienne"),
                     (_bestof_weekly, "best-of")):
        threading.Thread(target=fn, daemon=True, name=name).start()
