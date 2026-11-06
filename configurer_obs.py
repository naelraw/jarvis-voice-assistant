"""Règle OBS Studio pour JARVIS : clips des 30 dernières secondes avec le moins d'impact possible sur le jeu.

    python configurer_obs.py          -> applique les réglages (OBS doit être fermé ; sauvegarde des anciens réglages)

- Encodeur de la carte graphique (AMD ou NVIDIA, en HEVC) : le processeur reste libre pour le jeu.
- Tampon de relecture (replay buffer) de 30 s, gardé en mémoire ; « Jarvis, clip » ou Ctrl+Maj+S l'enregistre.
- Image en 1920x1080 sans redimensionnement (aucun calcul en plus), 60 images/s.
- Capture de jeu : « n'importe quelle application en plein écran » (Warzone, Steam, Battle.net…).
- Serveur WebSocket d'OBS activé sur cet ordinateur seulement, avec un mot de passe aléatoire que JARVIS relit dans
  la configuration d'OBS (personne n'a à le taper, il n'est jamais affiché).
"""
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import time
from pathlib import Path

OBS = Path(os.environ["APPDATA"]) / "obs-studio"


def obs_running() -> bool:
    out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq obs64.exe"], capture_output=True, text=True,
                         creationflags=0x08000000).stdout
    return "obs64.exe" in out.lower()


def gpu_vendor() -> str:
    out = subprocess.run(["powershell", "-NoProfile", "-Command",
                          "(Get-CimInstance Win32_VideoController).Name -join ';'"],
                         capture_output=True, text=True, creationflags=0x08000000).stdout.lower()
    return "nvidia" if "nvidia" in out else "amd" if ("amd" in out or "radeon" in out) else "autre"


def set_ini(txt: str, section: str, values: dict) -> str:
    if not re.search(rf"(?m)^\[{re.escape(section)}\]\s*$", txt):
        txt = txt.rstrip("\n") + f"\n\n[{section}]\n"
    head, body = re.split(rf"(?m)^\[{re.escape(section)}\]\s*$\n?", txt, maxsplit=1)
    m = re.search(r"(?m)^\[", body)
    sec, rest = (body[:m.start()], body[m.start():]) if m else (body, "")
    for k, v in values.items():
        line = f"{k}={v}"
        if re.search(rf"(?m)^{re.escape(k)}=", sec):
            sec = re.sub(rf"(?m)^{re.escape(k)}=.*$", lambda _: line, sec)
        else:
            sec = sec.rstrip("\n") + "\n" + line + "\n"
    return f"{head}[{section}]\n{sec.rstrip(chr(10))}\n\n{rest}".rstrip("\n") + "\n"


def main() -> int:
    if not OBS.exists():
        print("OBS Studio n'a jamais été ouvert sur ce PC : ouvre-le une fois, ferme-le, puis relance ce script.")
        return 1
    if obs_running():
        print("OBS est ouvert : ferme-le (clic droit sur l'icône près de l'horloge > Quitter), puis relance ce script.")
        return 1
    glob = "".join((OBS / f).read_text(encoding="utf-8-sig", errors="ignore")  # OBS 32 : user.ini
                   for f in ("user.ini", "global.ini") if (OBS / f).exists())
    prof = re.search(r"(?m)^ProfileDir=(.+)$", glob)
    coll = re.search(r"(?m)^SceneCollectionFile=(.+)$", glob)
    prof_dir = OBS / "basic" / "profiles" / (prof.group(1).strip() if prof else "Sans_nom")
    if not prof_dir.exists():
        prof_dir = next((OBS / "basic" / "profiles").iterdir())
    scene_name = coll.group(1).strip() if coll else prof_dir.name
    scene_file = OBS / "basic" / "scenes" / (scene_name if scene_name.endswith(".json") else scene_name + ".json")
    stamp = time.strftime("%Y%m%d-%H%M%S")

    # 1. sortie : encodeur matériel, tampon de relecture, mêmes dimensions que l'écran
    ini = prof_dir / "basic.ini"
    shutil.copy(ini, ini.with_name(f"basic.ini.avant-jarvis-{stamp}"))
    txt = ini.read_text(encoding="utf-8-sig")
    vendor = gpu_vendor()
    enc = {"amd": "amd_hevc", "nvidia": "nvenc_hevc"}.get(vendor, "x264")
    txt = set_ini(txt, "Output", {"Mode": "Simple"})
    txt = set_ini(txt, "SimpleOutput", {
        "RecEncoder": enc, "StreamEncoder": enc.replace("_hevc", ""), "RecQuality": "Small", "RecFormat2": "mp4",
        "RecRB": "true", "RecRBTime": "30", "RecRBSize": "512", "RecRBPrefix": "Clip",
        "FilePath": str(Path.home() / "Videos").replace("\\", "\\\\")})
    base = re.search(r"(?m)^BaseCX=(\d+)", txt), re.search(r"(?m)^BaseCY=(\d+)", txt)
    cx, cy = (base[0].group(1), base[1].group(1)) if all(base) else ("1920", "1080")
    txt = set_ini(txt, "Video", {"OutputCX": cx, "OutputCY": cy, "FPSType": "0", "FPSCommon": "60"})
    # Ctrl+Maj+S = enregistrer le clip (comme l'ancien raccourci AMD), même en pleine partie
    txt = set_ini(txt, "Hotkeys", {"ReplayBuffer": json.dumps(
        {"ReplayBuffer.Save": [{"control": True, "shift": True, "key": "OBS_KEY_S"}]}, separators=(",", ":"))})
    ini.write_text(txt, encoding="utf-8-sig")

    # 2. capture de jeu : n'importe quelle appli en plein écran
    if scene_file.exists():
        shutil.copy(scene_file, scene_file.with_name(scene_file.name + f".avant-jarvis-{stamp}"))
        d = json.loads(scene_file.read_text(encoding="utf-8"))
        n = 0
        for s in d.get("sources", []):
            if s.get("id") == "game_capture":
                s.setdefault("settings", {})["capture_mode"] = "any_fullscreen"
                n += 1
        scene_file.write_text(json.dumps(d, ensure_ascii=False, indent=4), encoding="utf-8")
        if not n:
            print("Attention : aucune source « Capture de jeu » dans la scène. Ajoute-la dans OBS "
                  "(Sources > + > Capture de jeu > « Capturer n'importe quelle application en plein écran »).")

    # 3. serveur WebSocket (local) pour que JARVIS commande OBS
    ws = OBS / "plugin_config" / "obs-websocket" / "config.json"
    ws.parent.mkdir(parents=True, exist_ok=True)
    conf = json.loads(ws.read_text(encoding="utf-8")) if ws.exists() else {}
    conf.update(server_enabled=True, server_port=conf.get("server_port", 4455), auth_required=True,
                alerts_enabled=False, first_load=False)
    if not conf.get("server_password"):
        conf["server_password"] = secrets.token_urlsafe(18)
    ws.write_text(json.dumps(conf, indent=4), encoding="utf-8")

    print(f"OBS réglé pour JARVIS (carte graphique : {vendor}, encodeur {enc}).")
    print("Clips : « Jarvis, clip » ou Ctrl+Maj+S en jeu -> dossier Vidéos (fichiers « Clip … »).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
