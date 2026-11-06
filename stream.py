"""Stream (Twitch par OBS) et page « Deck » de JARVIS (2026-10-27).

 - Pilote OBS par son WebSocket local (déjà utilisé pour les clips) : live, micro, son du bureau, écran en pause
   (la capture du jeu masquée), enregistrement, scènes.
 - Surveille le live : durée, images perdues, débit -> tableau de bord (et alerte si la connexion décroche).
 - Page « Deck » : une grille de gros boutons (façon Stream Deck) sur la tablette / le PC : stream, JARVIS, musique,
   raccourcis (gestionnaire de stream Twitch, chat, Discord…) et boutons perso (ajoutés à la voix ou sur la page).

Lancer ou couper le live publie quelque chose : toujours une confirmation (deuxième appui, ou « oui » à la voix).
"""
from __future__ import annotations

import base64
import configparser
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

J = None  # module jarvis_voice

_ST: dict = {"live": False, "since": 0.0, "snap": None, "t": 0.0, "frames": None, "alerte": "", "lock": threading.Lock()}
CAPTURE_KINDS = ("game_capture", "monitor_capture", "window_capture")


# ---------------------------------------------------------------------------------------------------------------
# OBS : plusieurs demandes sur une seule connexion
# ---------------------------------------------------------------------------------------------------------------

def _batch(reqs: list[tuple[str, dict | None]], timeout: float = 3.0) -> list[dict | None]:
    """Demandes au WebSocket d'OBS en un seul aller-retour. None pour une demande refusée."""
    from websockets.sync.client import connect

    c = J._obs_conf()
    if not c:
        raise RuntimeError("OBS n'est pas réglé pour JARVIS")
    with connect(f"ws://127.0.0.1:{c.get('server_port', 4455)}", open_timeout=timeout,
                 subprotocols=["obswebsocket.json"]) as ws:
        hello = json.loads(ws.recv(timeout=timeout))["d"]
        ident = {"rpcVersion": 1, "eventSubscriptions": 0}
        if hello.get("authentication"):
            a = hello["authentication"]
            secret = base64.b64encode(hashlib.sha256((c.get("server_password", "") + a["salt"]).encode()).digest())
            ident["authentication"] = base64.b64encode(
                hashlib.sha256(secret + a["challenge"].encode()).digest()).decode()
        ws.send(json.dumps({"op": 1, "d": ident}))
        json.loads(ws.recv(timeout=timeout))
        ws.send(json.dumps({"op": 8, "d": {"requestId": "b", "requests": [
            {"requestType": t, "requestId": str(i), "requestData": d or {}} for i, (t, d) in enumerate(reqs)]}}))
        res = json.loads(ws.recv(timeout=timeout))["d"]["results"]
    out: list[dict | None] = [None] * len(reqs)
    for r in res:
        if r.get("requestStatus", {}).get("result"):
            out[int(r["requestId"])] = r.get("responseData") or {}
    return out


def chaine() -> str:
    """La chaîne Twitch : réglage twitch_chaine, sinon le compte Twitch connecté dans OBS."""
    ch = str(J.CFG.get("twitch_chaine", "") or "").strip()
    if ch:
        return ch
    try:
        for ini in (J.OBS_DIR / "basic" / "profiles").glob("*/basic.ini"):
            cp = configparser.ConfigParser(interpolation=None, strict=False)
            cp.read(ini, encoding="utf-8-sig")
            if cp.has_option("Twitch", "Name"):
                return cp.get("Twitch", "Name").strip()
    except Exception:
        pass
    return ""


def _inputs() -> tuple[str, str]:
    """(micro, son du bureau) : les premières sources audio d'OBS de chaque sorte."""
    r = _batch([("GetInputList", None)])[0] or {}
    mic = next((i["inputName"] for i in r.get("inputs", []) if i["inputKind"] == "wasapi_input_capture"), "")
    desk = next((i["inputName"] for i in r.get("inputs", []) if i["inputKind"] == "wasapi_output_capture"), "")
    return mic, desk


def _fmt_dur(ms: int) -> str:
    s = int(ms // 1000)
    return f"{s // 3600}:{s // 60 % 60:02d}:{s % 60:02d}" if s >= 3600 else f"{s // 60}:{s % 60:02d}"


def etat(force: bool = False) -> dict:
    """État d'OBS pour le Deck et le tableau de bord (gardé 1,5 s : plusieurs écrans peuvent demander en même temps)."""
    with _ST["lock"]:
        if not force and _ST["snap"] and time.time() - _ST["t"] < 1.5:
            return _ST["snap"]
        snap = {"ok": False, "obs": False, "live": False, "chaine": chaine()}
        if J._obs_conf() and J._obs_running():
            snap["obs"] = True
            try:
                mic, desk = _inputs()
                st, rec, rb, scenes, mm, dm = _batch([
                    ("GetStreamStatus", None), ("GetRecordStatus", None), ("GetReplayBufferStatus", None),
                    ("GetSceneList", None),
                    ("GetInputMute", {"inputName": mic}) if mic else ("GetVersion", None),
                    ("GetInputMute", {"inputName": desk}) if desk else ("GetVersion", None)])
                cur = (scenes or {}).get("currentProgramSceneName", "")
                items = (_batch([("GetSceneItemList", {"sceneName": cur})])[0] or {}).get("sceneItems", []) if cur else []
                caps = [i for i in items if i.get("inputKind") in CAPTURE_KINDS]
                st = st or {}
                snap.update({
                    "ok": True, "live": bool(st.get("outputActive")), "reconnect": bool(st.get("outputReconnecting")),
                    "duree": _fmt_dur(st.get("outputDuration") or 0) if st.get("outputActive") else "",
                    "perdues": st.get("outputSkippedFrames") or 0, "images": st.get("outputTotalFrames") or 0,
                    "congestion": round(float(st.get("outputCongestion") or 0), 2),
                    "rec": bool((rec or {}).get("outputActive")), "replay": bool((rb or {}).get("outputActive")),
                    "rec_duree": _fmt_dur((rec or {}).get("outputDuration") or 0) if (rec or {}).get("outputActive") else "",
                    "scene": cur, "scenes": [s["sceneName"] for s in reversed((scenes or {}).get("scenes", []))],
                    "micro": mic, "micro_muet": bool((mm or {}).get("inputMuted")) if mic else None,
                    "bureau": desk, "bureau_muet": bool((dm or {}).get("inputMuted")) if desk else None,
                    "ecran_pause": bool(caps) and not any(i.get("sceneItemEnabled") for i in caps),
                })
            except Exception as exc:
                snap["err"] = str(exc)[:120]
        snap["alerte"] = _ST["alerte"] if snap.get("live") else ""
        _ST["snap"], _ST["t"] = snap, time.time()
        return snap


# ---------------------------------------------------------------------------------------------------------------
# Actions (Deck, voix)
# ---------------------------------------------------------------------------------------------------------------

def _need_obs() -> str:
    if not J._obs_conf():
        return "OBS n'est pas réglé pour JARVIS."
    if not J._obs_running() and not J.obs_ensure(False):
        return "OBS ne répond pas."
    return ""


def _toggle_mute(which: str) -> str:
    err = _need_obs()
    if err:
        return err
    mic, desk = _inputs()
    name = mic if which == "micro" else desk
    if not name:
        return "Je ne trouve pas cette source audio dans OBS."
    r = _batch([("ToggleInputMute", {"inputName": name})])[0] or {}
    muted = r.get("inputMuted")
    what = "Micro" if which == "micro" else "Son du PC"
    return f"{what} coupé sur le stream." if muted else f"{what} remis sur le stream."


def _pause_ecran() -> str:
    """Masque (ou réaffiche) la capture du jeu dans la scène en cours : écran « pause » sur le stream."""
    err = _need_obs()
    if err:
        return err
    cur = (_batch([("GetCurrentProgramScene", None)])[0] or {}).get("currentProgramSceneName", "")
    items = (_batch([("GetSceneItemList", {"sceneName": cur})])[0] or {}).get("sceneItems", [])
    caps = [i for i in items if i.get("inputKind") in CAPTURE_KINDS]
    if not caps:
        return "Pas de capture d'écran ou de jeu dans la scène en cours."
    show = not any(i.get("sceneItemEnabled") for i in caps)
    _batch([("SetSceneItemEnabled", {"sceneName": cur, "sceneItemId": i["sceneItemId"], "sceneItemEnabled": show})
            for i in caps])
    return "Écran réaffiché sur le stream." if show else "Écran masqué sur le stream : les spectateurs ne voient plus le jeu."


def _live(on: bool | None, confirme: bool) -> str:
    err = _need_obs()
    if err:
        return err
    live = bool((_batch([("GetStreamStatus", None)])[0] or {}).get("outputActive"))
    want = (not live) if on is None else on
    if want == live:
        return "Tu es déjà en live." if live else "Tu n'es pas en live."
    if not confirme:
        return ("À CONFIRMER : lancer le live sur Twitch maintenant ? (tout le monde pourra te voir)" if want else
                "À CONFIRMER : couper le live maintenant ?")
    _batch([("StartStream" if want else "StopStream", None)])
    J.log.info("Stream : live %s (demande de l'utilisateur)", "lancé" if want else "coupé")
    _ST["t"] = 0
    return "Live lancé sur Twitch." if want else "Live coupé."


def _scene(name: str) -> str:
    err = _need_obs()
    if err:
        return err
    scenes = [s["sceneName"] for s in (_batch([("GetSceneList", None)])[0] or {}).get("scenes", [])]
    pick = next((s for s in scenes if J.norm(s) == J.norm(name)), None) or \
        next((s for s in scenes if J.norm(name) in J.norm(s)), None)
    if not pick:
        return f"Pas de scène « {name} » dans OBS (scènes : {', '.join(scenes)})."
    _batch([("SetCurrentProgramScene", {"sceneName": pick})])
    return f"Scène « {pick} » à l'écran."


def _open_url(url: str) -> str:
    os.startfile(url)
    return "Ouvert."


def _perso() -> list[dict]:
    p = J.CFG.get("deck_perso") or []
    return [b for b in p if isinstance(b, dict) and b.get("nom") and b.get("cible")]


def _open_target(cible: str) -> str:
    c = cible.strip()
    if re.match(r"^(https?://|[\w-]+:)", c) or re.match(r"^[\w.-]+\.[a-z]{2,}(/.*)?$", c, re.I):
        return J.open_website(c)
    if Path(c).exists():
        os.startfile(c)
        return f"{Path(c).name} ouvert."
    return J.open_application(c)


def boutons() -> list[dict]:
    """Les boutons du Deck, rangés par groupe, avec leur état (allumé / coupé)."""
    s = etat()
    ch = s.get("chaine") or ""
    paused = bool(J.STATE.paused)
    b = [
        {"id": "live", "g": "Stream", "nom": "Couper le live" if s.get("live") else "Lancer le live", "ico": "live",
         "on": s.get("live"), "danger": True, "confirme": True},
        {"id": "micro", "g": "Stream", "nom": "Micro coupé" if s.get("micro_muet") else "Micro", "ico": "mic",
         "on": s.get("micro_muet") is False, "off": bool(s.get("micro_muet"))},
        {"id": "bureau", "g": "Stream", "nom": "Son PC coupé" if s.get("bureau_muet") else "Son du PC", "ico": "son",
         "on": s.get("bureau_muet") is False, "off": bool(s.get("bureau_muet"))},
        {"id": "ecran", "g": "Stream", "nom": "Écran masqué" if s.get("ecran_pause") else "Masquer l'écran", "ico": "ecran",
         "off": bool(s.get("ecran_pause"))},
        {"id": "clip", "g": "Stream", "nom": "Clip", "ico": "clip"},
        {"id": "rec", "g": "Stream", "nom": f"Enreg. {s.get('rec_duree', '')}" if s.get("rec") else "Enregistrer",
         "ico": "rec", "on": s.get("rec")},
    ]
    if len(s.get("scenes") or []) > 1:
        b += [{"id": "scene:" + n, "g": "Scènes", "nom": n, "ico": "scene", "on": n == s.get("scene")}
              for n in s["scenes"][:8]]
    b += [
        {"id": "jarvis", "g": "JARVIS", "nom": "Réveiller JARVIS" if paused else "Pause JARVIS", "ico": "jarvis", "off": paused},
        {"id": "capture", "g": "JARVIS", "nom": "Capture d'écran", "ico": "photo"},
        {"id": "dossier", "g": "JARVIS", "nom": "Mes clips", "ico": "dossier"},
        {"id": "prev", "g": "Musique", "nom": "Précédent", "ico": "prev"},
        {"id": "toggle", "g": "Musique", "nom": "Lecture / pause", "ico": "play"},
        {"id": "next", "g": "Musique", "nom": "Suivant", "ico": "next"},
    ]
    if ch:
        b += [{"id": "twitch_manager", "g": "Raccourcis", "nom": "Gestionnaire de stream", "ico": "twitch"},
              {"id": "twitch_chat", "g": "Raccourcis", "nom": "Chat Twitch", "ico": "chat"},
              {"id": "twitch_chaine", "g": "Raccourcis", "nom": "Ma chaîne", "ico": "twitch"}]
    b += [{"id": "obs", "g": "Raccourcis", "nom": "OBS", "ico": "obs"},
          {"id": "discord", "g": "Raccourcis", "nom": "Discord", "ico": "discord"},
          {"id": "youtube", "g": "Raccourcis", "nom": "YouTube", "ico": "youtube"},
          {"id": "deezer", "g": "Raccourcis", "nom": "Deezer", "ico": "musique"}]
    b += [{"id": f"perso:{i}", "g": "Perso", "nom": p["nom"], "ico": "perso", "cible": p["cible"]}
          for i, p in enumerate(_perso())]
    return b


def deck_state() -> dict:
    s = etat()
    return {"ok": True, "stream": s, "boutons": boutons()}


def action(bid: str, confirme: bool = False) -> dict:
    """Appui sur un bouton du Deck. Renvoie {ok, msg} ; msg « À CONFIRMER » = il faut appuyer une 2e fois."""
    bid = str(bid or "")
    ch = chaine()
    try:
        if bid == "live":
            msg = _live(None, confirme)
        elif bid in ("micro", "bureau"):
            msg = _toggle_mute(bid)
        elif bid == "ecran":
            msg = _pause_ecran()
        elif bid == "clip":
            msg = J.save_clip("clip")
        elif bid == "rec":
            msg = J.save_clip("enregistrement")
        elif bid == "capture":
            msg = J.save_clip("capture")
        elif bid.startswith("scene:"):
            msg = _scene(bid[6:])
        elif bid == "jarvis":
            J.set_paused(not J.STATE.paused, announce=False)
            msg = "JARVIS en pause." if J.STATE.paused else "JARVIS réveillé."
        elif bid == "dossier":
            os.startfile(str(Path.home() / "Videos"))
            msg = "Dossier des clips ouvert."
        elif bid in ("prev", "toggle", "next"):
            J.nowplaying_cmd(bid)
            msg = ""
        elif bid == "twitch_manager" and ch:
            msg = _open_url(f"https://dashboard.twitch.tv/u/{ch}/stream-manager")
        elif bid == "twitch_chat" and ch:
            msg = _open_url(f"https://www.twitch.tv/popout/{ch}/chat?popout=")
        elif bid == "twitch_chaine" and ch:
            msg = _open_url(f"https://www.twitch.tv/{ch}")
        elif bid == "obs":
            msg = J.open_application("OBS Studio")
        elif bid == "discord":
            msg = J.open_application("Discord")
        elif bid == "youtube":
            msg = _open_url("https://www.youtube.com")
        elif bid == "deezer":
            msg = J.open_application("Deezer")
        elif bid.startswith("perso:"):
            p = _perso()
            i = int(bid[6:])
            msg = _open_target(p[i]["cible"]) if 0 <= i < len(p) else "Bouton introuvable."
        else:
            return {"ok": False, "msg": "Bouton inconnu."}
    except Exception as exc:
        J.log.exception("Deck : %s", bid)
        return {"ok": False, "msg": f"Raté : {str(exc)[:100]}"}
    _ST["t"] = 0  # état relu au prochain affichage
    return {"ok": not str(msg).startswith(("OBS ne", "Je ne", "Pas de", "Raté")), "msg": msg,
            "confirmer": str(msg).startswith("À CONFIRMER")}


# ---------------------------------------------------------------------------------------------------------------
# Outils vocaux
# ---------------------------------------------------------------------------------------------------------------

def stream_obs(action: str = "etat", confirme: str = "", scene: str = "") -> str:
    """Stream Twitch par OBS, à la voix."""
    a = J.norm(action or "etat")
    ok = J.norm(str(confirme)) in ("oui", "true", "1", "ok")
    if scene or "scene" in a:
        return _scene(scene or re.sub(r".*scene\s*", "", a))
    if re.search(r"\b(lance|demarr|commence|start|go)\w*", a):
        return _live(True, ok)
    if re.search(r"\b(arret|coupe|stop|termin|fini)\w*", a) and "micro" not in a and "son" not in a:
        return _live(False, ok)
    if "micro" in a or "mic" in a:
        return _toggle_mute("micro")
    if "son" in a or "bureau" in a or "audio" in a:
        return _toggle_mute("bureau")
    if "ecran" in a or "masqu" in a or "cache" in a or "pause" in a:
        return _pause_ecran()
    if "enregistr" in a or "record" in a:
        return J.save_clip("enregistrement")
    s = etat(True)
    if not s.get("obs"):
        return "OBS n'est pas ouvert."
    if not s.get("ok"):
        return "OBS ne répond pas."
    parts = [f"En live depuis {s['duree']}" if s["live"] else "Pas en live"]
    if s["live"] and s.get("images"):
        pct = 100 * s["perdues"] / max(1, s["images"])
        parts.append(f"{pct:.1f} % d'images perdues" + (" (connexion faible)" if pct > 2 else ""))
    if s.get("micro_muet"):
        parts.append("micro coupé")
    if s.get("ecran_pause"):
        parts.append("écran masqué")
    if s.get("rec"):
        parts.append("enregistrement en cours")
    return ", ".join(parts) + "."


def deck_bouton(action: str = "liste", nom: str = "", cible: str = "") -> str:
    """Boutons perso du Deck : ajoute (nom + site / appli / dossier), supprime, liste."""
    a = J.norm(action or "liste")
    p = _perso()
    if "ajout" in a or "cre" in a or "met" in a:
        if not nom or not cible:
            return "Il me faut le nom du bouton et ce qu'il ouvre (site, appli ou dossier)."
        p = [b for b in p if J.norm(b["nom"]) != J.norm(nom)] + [{"nom": nom.strip()[:24], "cible": cible.strip()}]
        J.save_settings({"deck_perso": p})
        return f"Bouton « {nom} » ajouté au Deck."
    if "suppr" in a or "enleve" in a or "retire" in a:
        q = [b for b in p if J.norm(nom) not in J.norm(b["nom"])] if nom else p
        if len(q) == len(p):
            return f"Pas de bouton « {nom} » dans le Deck."
        J.save_settings({"deck_perso": q})
        return f"Bouton « {nom} » retiré du Deck."
    if not p:
        return "Aucun bouton perso dans le Deck pour l'instant."
    return "Boutons perso : " + ", ".join(f"{b['nom']} ({b['cible']})" for b in p) + "."


# ---------------------------------------------------------------------------------------------------------------
# Surveillance du live
# ---------------------------------------------------------------------------------------------------------------

def _watch() -> None:
    """Toutes les 5 s, si OBS est ouvert : début / fin du live, images perdues (connexion qui décroche)."""
    last_warn = 0.0
    while True:
        time.sleep(5)
        try:
            if not (J._obs_conf() and J._obs_running()):
                _ST["live"] = False
                continue
            st = _batch([("GetStreamStatus", None)])[0] or {}
            live = bool(st.get("outputActive"))
            if live != _ST["live"]:
                _ST["live"], _ST["since"], _ST["frames"], _ST["alerte"] = live, time.time(), None, ""
                J.log.info("Stream : %s", "live commencé" if live else "live terminé")
            if not live:
                continue
            fr = (st.get("outputSkippedFrames") or 0, st.get("outputTotalFrames") or 0)
            prev, _ST["frames"] = _ST["frames"], fr
            if prev and fr[1] > prev[1]:
                pct = 100 * (fr[0] - prev[0]) / (fr[1] - prev[1])
                bad = pct > 5 or st.get("outputReconnecting")
                _ST["alerte"] = ("Connexion perdue : OBS se reconnecte" if st.get("outputReconnecting") else
                                 f"{pct:.0f} % d'images perdues") if bad else ""
                if bad and time.time() - last_warn > 300:
                    last_warn = time.time()
                    J.log.warning("Stream : %s", _ST["alerte"])
                    if not getattr(J.STATE, "sleeping", False):  # en jeu : seulement sur le tableau de bord
                        J._say_later(f"Attention, ton stream décroche : {_ST['alerte']}.")
        except Exception:
            time.sleep(10)


def setup(module) -> None:
    global J
    J = module


def start() -> None:
    threading.Thread(target=_watch, daemon=True, name="stream-surveillance").start()
