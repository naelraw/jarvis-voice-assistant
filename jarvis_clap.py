"""Réveille JARVIS quand on tape deux fois dans ses mains.

Tourne en arrière-plan (démarrage de Windows). N'enregistre rien : il mesure seulement le son du micro,
par petits blocs, pour repérer deux claquements rapprochés (son très bref, sec, riche en aigus).

  pythonw jarvis_clap.py              -> écoute en arrière-plan
  python  jarvis_clap.py --test       -> affiche ce qu'il détecte (pour vérifier)
  python  jarvis_clap.py --calibrate  -> tape 4 fois dans tes mains : règle la sensibilité tout seul
"""

from __future__ import annotations

import ctypes
import json
import logging
import queue
import re
import socket
import subprocess
import sys
import time
import tomllib
import urllib.request
from collections import deque
from pathlib import Path

HERE = Path(__file__).resolve().parent
CONF_DIR = Path.home() / ".openjarvis"
CONF_DIR.mkdir(exist_ok=True)
CONF_FILE = CONF_DIR / "jarvis_voice.toml"
LOG_FILE = CONF_DIR / "jarvis_clap.log"
TEST = "--test" in sys.argv
CALIBRATE = "--calibrate" in sys.argv

if sys.stdout is None or sys.stderr is None:
    sys.stdout = sys.stderr = open(LOG_FILE, "a", encoding="utf-8", buffering=1)
logging.basicConfig(filename=str(LOG_FILE), level=logging.INFO,
                    format="%(asctime)s %(levelname)s %(message)s", encoding="utf-8")
log = logging.getLogger("clap")

import numpy as np  # noqa: E402
import sounddevice as sd  # noqa: E402

DEFAULTS = {"clap_enabled": True, "clap_min_peak": 0.03, "clap_ratio": 6.0,
            "clap_hf": 0.0,      # aigus exigés : aucun (micros de portable et écouteurs Bluetooth : claquements « graves »)
            "clap_gap_min": 0.12, "clap_gap_max": 1.2,  # écart entre les 2 claquements (s) : rapides ou posés
            "clap_jump": 2.5,    # montée brutale : niveau x2,5 d'un coup (le 2e claquement arrive sur l'écho du 1er)
            "clap_decay": 0.7}   # retombée après le claquement (micro du portable : 45-70 % ; la voix reste au-dessus de 80 %)


def settings() -> dict:
    cfg = dict(DEFAULTS)
    try:
        cfg.update(tomllib.loads(CONF_FILE.read_text(encoding="utf-8")))
    except Exception:
        pass
    return cfg


BUILTIN_MIC = re.compile(r"r[ée]seau de microphones|microphone array|micro.*int[ée]gr|internal mic", re.I)
HEADSET_MIC = re.compile(r"casque|headset|mains libres|hands-free|buds|airpods|bluetooth", re.I)


def pick_device(builtin_first: bool = False, wanted: str = "", force_builtin: bool = False) -> tuple[int | None, int]:
    """Micro via WASAPI (48 kHz natif : les sons secs ne sont pas lissés par le rééchantillonnage).

    wanted : nom du micro choisi dans les paramètres de JARVIS (« clap_device ») ; vide = automatique.
    builtin_first : le micro intégré du PC passe avant celui d'écouteurs Bluetooth (leur réduction de bruit étouffe
    les claquements, et ouvrir leur micro les bascule en « kit main-libre », ce qui dégrade la musique et les jeux)."""
    try:
        default_name = sd.query_devices(kind="input")["name"]
        inputs = []
        for api in sd.query_hostapis():
            if "WASAPI" in api["name"]:
                inputs = [(d, sd.query_devices(d)) for d in api["devices"]]
                inputs = [(d, dv) for d, dv in inputs if dv["max_input_channels"] > 0]
        if force_builtin:  # le micro choisi n'envoie rien : micro intégré du PC plutôt que rien du tout
            for d, dv in inputs:
                if BUILTIN_MIC.search(dv["name"]):
                    return d, int(dv["default_samplerate"])
        if wanted:
            for d, dv in inputs:
                if dv["name"][:28] == wanted[:28]:
                    return d, int(dv["default_samplerate"])
            log.warning("Micro choisi introuvable (%s) : choix automatique", wanted)
        if builtin_first and HEADSET_MIC.search(default_name):
            for d, dv in inputs:
                if BUILTIN_MIC.search(dv["name"]):
                    return d, int(dv["default_samplerate"])
        for d, dv in inputs:
            if dv["name"].startswith(default_name[:20]):
                return d, int(dv["default_samplerate"])
    except Exception:
        log.exception("Recherche du micro WASAPI")
    return None, 16000


def jarvis_running() -> bool:
    with socket.socket() as s:
        s.settimeout(0.3)
        return s.connect_ex(("127.0.0.1", 8765)) == 0


def jarvis_starting() -> bool:
    """Un JARVIS est-il en train de démarrer (processus lancé, serveur pas encore prêt) ?"""
    try:
        out = subprocess.run(["powershell", "-NoProfile", "-Command",
                              "(Get-CimInstance Win32_Process -Filter \"Name='pythonw.exe'\").CommandLine"],
                             capture_output=True, text=True, timeout=15, creationflags=0x08000000).stdout
        return "jarvis_voice.py" in out
    except Exception:
        return False


def wake_jarvis() -> None:
    if not jarvis_running() and jarvis_starting():
        for _ in range(30):  # le serveur de JARVIS arrive en quelques secondes
            time.sleep(1)
            if jarvis_running():
                break
    if jarvis_running():
        try:
            tok = (CONF_DIR / "jarvis_token").read_text(encoding="utf-8").strip()
            req = urllib.request.Request("http://127.0.0.1:8765/api/summon", method="POST",
                                         data=json.dumps({"token": tok, "briefing": True, "source": "clap"}).encode(),
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
            log.info("Double claquement : JARVIS réveillé")
            return
        except Exception:
            log.exception("Réveil de JARVIS impossible")
    pyw = Path(sys.executable).with_name("pythonw.exe")
    subprocess.Popen([str(pyw), str(HERE / "jarvis_voice.py")], cwd=str(HERE))
    log.info("Double claquement : JARVIS lancé")


class Detector:
    """Repère les claquements : montée brutale, aigus, retombée rapide."""

    def __init__(self, sr: int, cfg: dict, loose: bool = False, level: dict | None = None) -> None:
        self.sr, self.cfg, self.loose = sr, cfg, loose
        self.level = level  # calibrage : seuils imposés {peak, ratio, hf, jump, decay}
        self.block = int(sr * 0.016)
        self.bg = 0.002
        self.recent: deque = deque(maxlen=4)
        self.event = None
        freqs = np.fft.rfftfreq(self.block, 1 / sr)
        self.hf_mask = freqs >= 2000
        self.win = np.hanning(self.block)

    def feed(self, x: np.ndarray, now: float) -> dict | None:
        """Renvoie un claquement validé {t, peak, ratio, hf, decay} ou None."""
        rms = float(np.sqrt(np.mean(x * x)) + 1e-9)
        peak = float(np.max(np.abs(x)))
        prev = float(np.mean(self.recent)) if self.recent else rms
        self.recent.append(rms)
        if self.event is not None:
            ev = self.event
            ev["after"].append(rms)
            if len(ev["after"]) <= 2:  # micros de portable : le claquement s'étale sur 2-3 blocs, les aigus après le 1er
                ev["hfs"].append(self._hf(x))
            if len(ev["after"]) >= 7:  # ~110 ms après la montée (un seul événement : pas de « double » claquement)
                top = max([ev["rms"]] + ev["after"][:3])  # micro « lent » : le pic arrive juste après la montée
                ev["peak"] = max(ev["peak"], peak)
                ev["decay"] = float(np.mean(ev["after"][3:7])) / top
                ev["hf"] = max(ev.pop("hfs"))
                self.event = None
                lv = self.level
                lim = lv["decay"] if lv else (0.6 if self.loose else float(self.cfg.get("clap_decay", 0.45)))
                hf_min = lv["hf"] if lv else (0.0 if self.loose else float(self.cfg["clap_hf"]))
                ev["ok"] = ev["decay"] < lim and ev["hf"] >= hf_min
                if ev["decay"] >= lim:
                    ev["why"] = "pas assez sec"
                elif not ev["ok"]:
                    ev["why"] = "trop grave"
                return ev
            return None
        ratio = rms / max(self.bg, 1e-4)
        lv = self.level
        min_peak = lv["peak"] if lv else (0.005 if self.loose else float(self.cfg["clap_min_peak"]))
        min_ratio = lv["ratio"] if lv else (4.0 if self.loose else float(self.cfg["clap_ratio"]))
        jump = lv["jump"] if lv else float(self.cfg.get("clap_jump", 3.5))
        if ratio > min_ratio and rms > prev * jump and peak > min_peak:
            # décision après ~110 ms : aigus (meilleur des 3 premiers blocs) et retombée
            self.event = {"t": now, "rms": rms, "peak": peak, "ratio": ratio, "hfs": [self._hf(x)], "after": []}
        else:
            self.bg = min(0.05, max(0.0003, 0.995 * self.bg + 0.005 * rms))
        return None

    def _hf(self, x: np.ndarray) -> float:
        """Part d'aigus (au-dessus de 2 kHz) dans un bloc."""
        if len(x) != self.block:
            return 0.0
        spec = np.abs(np.fft.rfft(x * self.win)) ** 2
        return float(spec[self.hf_mask].sum() / (spec.sum() + 1e-12))


SLEEP_FLAG = CONF_DIR / "jarvis_game_sleep"  # créé par JARVIS pendant les jeux
QUIET_FLAG = CONF_DIR / "jarvis_quiet"       # créé par JARVIS pendant les heures de cours (rafraîchi toutes les 20 s)
MUTE_FLAG = CONF_DIR / "jarvis_micmute"      # micro coupé avec le bouton de l'interface


def must_sleep() -> bool:
    """Jeu en cours ou heures de cours : micro du détecteur fermé."""
    if TEST:
        return False
    if MUTE_FLAG.exists() or not settings().get("clap_enabled", True):
        return True
    try:  # jeu en cours : micro fermé, sauf si le jeu est en arrière-plan (« fond » écrit par JARVIS)
        if SLEEP_FLAG.read_text(encoding="utf-8").strip() != "fond":
            return True
    except OSError:
        pass
    try:  # fichier trop vieux = JARVIS arrêté pendant les cours : on n'en tient plus compte
        return time.time() - QUIET_FLAG.stat().st_mtime < 90
    except OSError:
        return False


class GameSleep(Exception):
    pass


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", ctypes.c_uint), ("dwTime", ctypes.c_uint)]


def input_idle_seconds() -> float:
    """Temps depuis la dernière touche du clavier ou le dernier mouvement / clic de souris (Windows)."""
    lii = _LASTINPUTINFO(ctypes.sizeof(_LASTINPUTINFO), 0)
    if not ctypes.windll.user32.GetLastInputInfo(ctypes.byref(lii)):
        return 999.0
    return ((ctypes.windll.kernel32.GetTickCount() - lii.dwTime) & 0xFFFFFFFF) / 1000.0


class MicChange(Exception):
    """Un autre micro a été choisi dans les paramètres : on rouvre le flux avec lui."""


def save_settings(values: dict) -> None:
    txt = CONF_FILE.read_text(encoding="utf-8") if CONF_FILE.exists() else ""
    for k, v in values.items():
        line = f"{k} = {v}"
        if re.search(rf"(?m)^{k}\s*=", txt):
            txt = re.sub(rf"(?m)^{k}\s*=.*$", line, txt)
        else:
            txt = txt.rstrip("\n") + "\n" + line + "\n"
    CONF_FILE.write_text(txt, encoding="utf-8")


LEVELS = (  # du plus strict (PC fixe, casque) au plus tolérant (micro de portable avec réduction de bruit)
    {"peak": 0.005, "ratio": 4.0, "hf": 0.08, "jump": 3.5, "decay": 0.6},
    {"peak": 0.003, "ratio": 3.0, "hf": 0.05, "jump": 2.5, "decay": 0.75},
    {"peak": 0.002, "ratio": 2.5, "hf": 0.03, "jump": 1.8, "decay": 0.9},
)


def analyse(x: np.ndarray, sr: int, level: dict) -> tuple[list, dict]:
    det = Detector(sr, settings(), loose=True, level=level)
    found, why = [], {}
    for i in range(0, len(x) - det.block, det.block):
        ev = det.feed(x[i:i + det.block], i / sr)
        if not ev:
            continue
        if ev.get("ok"):
            if not found or ev["t"] - found[-1]["t"] > 0.25:
                found.append(ev)
        else:
            why[ev.get("why", "?")] = why.get(ev.get("why", "?"), 0) + 1
    return found, why


def calibrate() -> None:
    dev, sr = pick_device(builtin_first=True, wanted=str(settings().get("clap_device", "")))
    try:
        name = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
    except Exception:
        name = "micro par défaut"
    print("\n  === Calibrage du claquement de mains ===\n")
    print(f"  Micro utilisé : {name}  ({sr} Hz)\n")
    print("  Pendant 10 secondes : tape 4 fois dans tes mains, en laissant 1 seconde entre chaque,")
    print("  à la distance habituelle (assis devant le PC).\n")
    input("  Appuie sur Entrée puis commence à taper...")
    rec = sd.rec(int(sr * 10), samplerate=sr, channels=1, dtype="float32", device=dev)
    for i in range(10, 0, -1):
        print(f"\r  ... {i} s ", end="", flush=True)
        time.sleep(1)
    sd.wait()
    x = rec[:, 0]
    loud = float(np.max(np.abs(x))) if len(x) else 0.0
    floor = float(np.percentile(np.abs(x), 50)) if len(x) else 0.0
    print(f"\n\n  Son le plus fort entendu : {loud:.3f}   (bruit de fond : {floor:.4f})")
    if loud < 0.002:
        print("\n  Le micro ne capte RIEN (silence total). Causes probables :")
        print("   - Paramètres Windows > Confidentialité et sécurité > Microphone :")
        print("     active « Accès au microphone » ET « Autoriser les applications de bureau à accéder au microphone ».")
        print("   - Le micro est coupé (touche micro du clavier, voyant rouge) ou ce n'est pas le bon micro par défaut :")
        print("     Paramètres > Système > Son > Entrée : choisis le micro du portable et parle pour voir la barre bouger.")
        input("\n  Entrée pour fermer")
        return
    found, why, used = [], {}, None
    for n, lv in enumerate(LEVELS):
        found, why = analyse(x, sr, lv)
        if len(found) >= 3:
            used = (n, lv)
            break
    if used is None:
        print(f"\n  Seulement {len(found)} claquement(s) reconnu(s).")
        if why:
            print("  Sons entendus mais refusés : " + ", ".join(f"{k} ({v})" for k, v in why.items()))
        if loud < 0.05:
            print("  Le son arrive très faible : rapproche-toi du micro, ou monte le volume du micro")
            print("  (Paramètres > Système > Son > Entrée > Volume : 80-100 %).")
        print("  Les micros de portable ont souvent une « réduction de bruit » qui efface les claquements :")
        print("  Paramètres > Système > Son > (ton micro) > Améliorations audio / Effets audio : désactive-les,")
        print("  ainsi que « Voice Clarity » ou « Effets Windows Studio » s'ils existent, puis relance le calibrage.")
        input("\n  Entrée pour fermer")
        return
    n, lv = used
    top = sorted(found, key=lambda e: e["peak"], reverse=True)[:4]
    min_peak = max(0.002, round(0.5 * min(e["peak"] for e in top), 4))
    ratio = round(max(2.5, 0.4 * min(e["ratio"] for e in top)), 1)
    hf = round(max(0.03, 0.6 * min(e["hf"] for e in top)), 2)
    decay = round(min(0.9, max(0.45, 1.3 * max(e["decay"] for e in top))), 2)
    for e in top:
        print(f"  claquement : niveau {e['peak']:.3f}  ({e['ratio']:.0f}x le bruit de fond, aigus {e['hf']:.0%}, "
              f"retombée {e['decay']:.2f})")
    save_settings({"clap_min_peak": min_peak, "clap_ratio": ratio, "clap_hf": hf,
                   # jamais plus que 2,5 : le 2e claquement d'une paire arrive sur l'écho du 1er (il « monte »
                   # moins) ; à 3,5, chaque « clap-clap » ne comptait que pour un (PC gamer, 2026-10-17)
                   "clap_jump": min(lv["jump"], 2.5), "clap_decay": decay})
    if n:
        print("\n  Micro « adouci » (réduction de bruit) : réglage plus tolérant appliqué.")
    print(f"\n  Réglé : sensibilité {min_peak} / {ratio}x / aigus {hf:.0%} / retombée {decay}. C'est enregistré !")
    print("  Le détecteur en arrière-plan prend le réglage en compte dans les 10 secondes.")
    input("\n  Entrée pour fermer")


def list_mics() -> list[str]:
    """Micros branchés (noms WASAPI complets), le micro par défaut de Windows en premier."""
    names: list[str] = []
    for api in sd.query_hostapis():
        if "WASAPI" in api["name"]:
            try:
                default = api["default_input_device"]
            except KeyError:
                default = -1
            for d in sorted(api["devices"], key=lambda d: d != default):
                dv = sd.query_devices(d)
                if dv["max_input_channels"] > 0 and dv["name"] not in names:
                    names.append(dv["name"])
    return names


def list_outs() -> list[str]:
    """Sorties son branchées (noms WASAPI complets), la sortie par défaut de Windows en premier."""
    names: list[str] = []
    for api in sd.query_hostapis():
        if "WASAPI" in api["name"]:
            default = api.get("default_output_device", -1)
            for d in sorted(api["devices"], key=lambda d: d != default):
                dv = sd.query_devices(d)
                if dv["max_output_channels"] > 0 and dv["name"] not in names:
                    names.append(dv["name"])
    return names


def mic_level(name: str, seconds: float = 3.0, clap: bool = False) -> dict:
    """Test d'un micro depuis les paramètres : niveau maximal et moyen pendant quelques secondes."""
    dev, sr = pick_device(builtin_first=clap, wanted=name)
    used = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
    got: list = []  # flux avec rappel (sd.rec attend sans fin si le micro n'envoie rien, ex. écouteurs rangés)
    with sd.InputStream(samplerate=sr, channels=1, dtype="float32", device=dev,
                        callback=lambda i, f, t, s: got.append(i[:, 0].copy())):
        time.sleep(seconds)
    if not got:
        return {"name": used, "peak": 0.0, "rms": 0.0, "dead": True}
    x = np.concatenate(got)
    return {"name": used, "peak": round(float(np.max(np.abs(x))), 4), "rms": round(float(np.sqrt(np.mean(x * x))), 5),
            "dead": False}


def main() -> None:
    if "--list-mics" in sys.argv:
        print(json.dumps(list_mics(), ensure_ascii=False))
        return
    if "--list-outs" in sys.argv:
        print(json.dumps(list_outs(), ensure_ascii=False))
        return
    if "--mic-level" in sys.argv:
        i = sys.argv.index("--mic-level")
        name = sys.argv[i + 1] if len(sys.argv) > i + 1 and not sys.argv[i + 1].startswith("--") else ""
        print(json.dumps(mic_level(name, clap="--clap" in sys.argv), ensure_ascii=False))
        return
    if CALIBRATE:
        calibrate()
        return
    lock = socket.socket()
    try:
        lock.bind(("127.0.0.1", 8766))  # une seule instance en arrière-plan
    except OSError:
        if not TEST:
            return
        print("(Le détecteur tourne aussi en arrière-plan : un double claquement réveillera JARVIS.)")
    try:  # priorité « inférieure à la normale » : les jeux passent avant
        import ctypes
        ctypes.windll.kernel32.SetPriorityClass(ctypes.c_void_p(-1), 0x4000)
    except Exception:
        pass
    cfg = settings()
    dead, forced = 0, False  # micro muet (ouvertures de suite sans aucun son) -> micro intégré jusqu'au prochain choix
    while True:  # si le casque se déconnecte, on rebranche le micro
        if must_sleep():
            log.info("Jeu, heures de cours ou claquements désactivés : micro du détecteur fermé")
            while must_sleep():
                time.sleep(1)
            log.info("Fin du jeu ou des cours : détecteur de claquements rallumé")
        try:
            want = str(settings().get("clap_device", ""))
            dev, sr = pick_device(builtin_first=True, wanted=want, force_builtin=forced)
            det = Detector(sr, cfg)
            q: queue.Queue = queue.Queue()

            def cb(indata, frames, t, status) -> None:
                q.put(indata[:, 0].copy())

            chain: list = []  # bruits secs rapprochés (claquements validés ou non)
            cooldown_until = 0.0
            last_cfg = time.time()
            samples = 0
            name = sd.query_devices(dev if dev is not None else sd.default.device[0])["name"]
            log.info("Détecteur de claquements démarré (%s, %d Hz)", name, sr)
            if TEST:
                print(f"Micro : {name} ({sr} Hz). Tape 2 fois dans tes mains. Ctrl+C pour quitter.\n")
            with sd.InputStream(samplerate=sr, channels=1, dtype="float32", blocksize=det.block, device=dev, callback=cb):
                while True:
                    x = q.get(timeout=3)  # plus de son = micro déconnecté
                    samples += len(x)
                    if samples % (sr // 2) < len(x) and must_sleep():
                        raise GameSleep()  # jeu lancé ou cours : on ferme le micro (vérifié toutes les ~0,5 s)
                    now = samples / sr  # horloge du son : insensible aux retards de traitement
                    if time.time() - last_cfg > 10:
                        det.cfg, last_cfg = settings(), time.time()
                        if str(det.cfg.get("clap_device", "")) != want:
                            raise MicChange()
                        if not det.cfg.get("clap_enabled", True) and not TEST:
                            raise GameSleep()  # désactivé dans les paramètres : micro fermé (voir must_sleep)
                    ev = det.feed(x, now)
                    if ev:
                        desc = (f"niveau {ev['peak']:.3f}, {ev['ratio']:.0f}x le fond, aigus {ev['hf']:.0%}, "
                                f"retombée {ev['decay']:.0%}" if ev.get("decay") is not None else
                                f"niveau {ev['peak']:.3f}, aigus {ev['hf']:.0%} ({ev.get('why')})")
                        log.info("%s : %s", "CLAQUEMENT" if ev["ok"] else "son ignoré", desc)
                        if TEST:
                            print(("  CLAQUEMENT    " if ev["ok"] else "  son ignoré    ") + desc)
                        if chain and ev["t"] - chain[-1]["t"] > float(det.cfg["clap_gap_max"]) + 0.1:
                            chain = []
                        if ev["ok"]:  # un bruit refusé (voix, souffle...) entre deux claquements ne casse plus la paire
                            ev["wall"] = time.time() - 0.12  # heure réelle du choc (décidé ~110 ms après)
                            chain.append(ev)
                    # On attend 0,6 s de calme après le dernier bruit, puis on juge la série :
                    # il faut EXACTEMENT deux claquements nets, de force proche, et rien d'autre
                    # (clavier, souris, objet posé = un seul bruit ou plusieurs -> ignoré).
                    # (un seul claquement : on laisse au second le temps d'arriver, jusqu'à l'écart maximal)
                    wait = float(det.cfg["clap_gap_max"]) + 0.1 if len(chain) == 1 else 0.6
                    if chain and now - chain[-1]["t"] > wait:
                        a, b = chain[0], chain[-1]
                        gap = b["t"] - a["t"]
                        ok = (len(chain) == 2 and a["ok"] and b["ok"]
                              and float(det.cfg["clap_gap_min"]) <= gap <= float(det.cfg["clap_gap_max"])
                              and max(a["peak"], b["peak"]) <= 3.5 * min(a["peak"], b["peak"]))
                        # on ne claque pas des mains en tapant : clavier ou souris utilisés juste avant ou pendant
                        # = frappe de touches / clics captés par le micro du portable (juste au-dessus du clavier)
                        typing = time.time() - input_idle_seconds() > a.get("wall", time.time()) - 1.0
                        if len(chain) >= 2:
                            log.info("Série de %d bruits, écart %.2f s : %s", len(chain), gap,
                                     "ignorée (clavier ou souris utilisés)" if ok and typing and not TEST
                                     else "DOUBLE CLAQUEMENT" if ok else "ignorée")
                        if typing and not TEST:
                            ok = False
                        chain = []
                        if ok and now > cooldown_until:
                            cooldown_until = now + 4
                            if TEST:
                                print(f"\n  >>> DOUBLE CLAQUEMENT (écart {gap:.2f} s) : JARVIS se réveille !\n")
                            wake_jarvis()

        except Exception as exc:
            if isinstance(exc, KeyboardInterrupt):
                raise
            if isinstance(exc, GameSleep):
                continue
            if isinstance(exc, MicChange):
                dead, forced = 0, False
                log.info("Autre micro choisi dans les paramètres : changement")
            else:
                log.warning("Micro perdu (%s) : reconnexion...", type(exc).__name__)
                if isinstance(exc, queue.Empty):
                    dead += 1
                    if dead >= 2 and not forced:
                        forced = True
                        log.warning("Le micro n'envoie aucun son (écouteurs rangés ou déconnectés ?) : "
                                    "micro intégré du PC utilisé à la place")
            if TEST:
                print("\n  (micro perdu, reconnexion...)")
            time.sleep(2)
            try:
                sd._terminate()
                sd._initialize()
            except Exception:
                log.exception("Réinitialisation audio")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        pass
    except Exception:
        log.exception("Détecteur de claquements arrêté")
        if TEST or CALIBRATE:
            raise
