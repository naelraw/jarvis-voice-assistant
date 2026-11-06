"""Pont JARVIS <-> Copilote Roblox (projet « roblox-ia », optionnel).

Le Copilote est un panneau de chat dans Roblox Studio relié à un serveur OpenCode local (127.0.0.1:4096, mot de passe dans
motdepasse.txt) : une IA y construit directement dans Studio par le serveur MCP de Studio. Ce module envoie une demande
à CE MÊME serveur, comme le fait le panneau (POST /api/session, /agent, /model, /prompt), puis suit l'avancement
(/api/session/active, /api/session/<id>/message). JARVIS peut ainsi, à la voix ou depuis le téléphone, demander au Copilote
de construire (modèles 3D, mécaniques...) et dire quand c'est fini.

Variante « Claude » : le pont `claude/pont.py` (port 4098, même API) lance Claude Code avec le MCP de Studio ; elle ne sert
QUE si l'utilisateur la demande explicitement.

Rien ici ne lit ni n'affiche le mot de passe ou les clés des IA : seul l'en-tête d'authentification est construit.
"""
from __future__ import annotations

import base64
import json
import logging
import os
import re
import subprocess
import sys
import time
from pathlib import Path

import httpx

log = logging.getLogger("jarvis")
DIR = Path.home() / "roblox-ia"
SERVER = "http://127.0.0.1:4096/api"
BRIDGE = "http://127.0.0.1:4098/api"

# Modèles, dans l'ordre d'essai par défaut : gratuits d'abord (on reste sur du gratuit ; Mistral consomme un crédit mensuel).
# id/provider/agent sont lus dans le plugin (MODELES) s'il est là, pour rester d'accord avec le menu du panneau.
FALLBACK_MODELS = {
    "nemotron": {"id": "nvidia/nemotron-3-ultra-550b-a55b", "providerID": "nvidia", "agent": "roblox-gemini"},
    "gemini": {"id": "gemini-3.5-flash-lite", "providerID": "google", "agent": "roblox-gemini"},
    "kilo": {"id": "nvidia/nemotron-3-ultra-550b-a55b:free", "providerID": "kilolibre", "agent": "roblox-gemini"},
    "mistral": {"id": "mistral-large-4", "providerID": "mistral", "agent": "roblox-gemini"},
}
ORDER = ["nemotron", "gemini", "kilo", "mistral"]
PAID = {"mistral"}
LIMIT_WORDS = ("free usage limit", "quota", "rate limit", "rate_limit", "too many requests", "429", "exceeded",
               "insufficient", "credit", "billing", "overloaded", "limit reached")


def models() -> dict:
    """Modèles du menu du panneau (plugin/AssistantIA.lua), classés par famille ; sinon valeurs de secours."""
    out = dict(FALLBACK_MODELS)
    try:
        src = (DIR / "plugin" / "AssistantIA.lua").read_text(encoding="utf-8")
        for m in re.finditer(r'\{\s*id = "([^"]+)",\s*provider = "([^"]+)",\s*agent = "([^"]+)"', src):
            mid, prov, agent = m.groups()
            key = ("mistral" if prov == "mistral" else "kilo" if prov == "kilolibre" else "gemini" if prov == "google"
                   else "nemotron" if "nemotron" in mid else "")
            if key:
                out[key] = {"id": mid, "providerID": prov, "agent": agent}
    except OSError:
        pass
    return out


def _auth() -> dict:
    pw = (DIR / "motdepasse.txt").read_text(encoding="ascii").strip()
    return {"Authorization": "Basic " + base64.b64encode(f"opencode:{pw}".encode()).decode()}


def call(method: str, path: str, body: dict | None = None, base: str = SERVER, timeout: float = 20) -> dict:
    r = httpx.request(method, base + path, json=body, headers=_auth(), timeout=timeout)
    if r.status_code >= 400:
        raise RuntimeError(f"{r.status_code} {r.text[:200]}")
    return r.json() if r.content else {}


def up(base: str = SERVER) -> bool:
    try:
        call("GET", "/info", base=base, timeout=3)
        return True
    except Exception:
        return False


def studio_open() -> bool:
    try:
        out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq RobloxStudioBeta.exe", "/NH"], capture_output=True,
                             text=True, timeout=10, creationflags=0x08000000).stdout
        return "RobloxStudioBeta" in out
    except Exception:
        return False


def _wait(base: str, seconds: float) -> bool:
    t0 = time.time()
    while time.time() - t0 < seconds:
        if up(base):
            return True
        time.sleep(1)
    return False


def start_server() -> bool:
    """Lance le serveur du Copilote caché, comme le fait Windows au démarrage (demarrer-cache.vbs)."""
    vbs = DIR / "demarrer-cache.vbs"
    if not vbs.exists():
        return False
    subprocess.Popen(["wscript.exe", str(vbs)], cwd=str(DIR), creationflags=0x08000000)
    return _wait(SERVER, 40)


def start_bridge() -> bool:
    """Lance le pont Claude Code (claude/pont.py, port 4098)."""
    pont = DIR / "claude" / "pont.py"
    if not pont.exists():
        return False
    exe = Path(sys.executable)
    pyw = exe.with_name("pythonw.exe")
    subprocess.Popen([str(pyw if pyw.exists() else exe), str(pont)], cwd=str(pont.parent), creationflags=0x08000000)
    return _wait(BRIDGE, 15)


def clean(text: str, n: int = 240) -> str:
    t = re.sub(r"```.*?```", " ", text or "", flags=re.S)
    t = re.sub(r"[*_`#>|]+", " ", t)
    t = re.sub(r"\s+", " ", t).strip()
    return t if len(t) <= n else t[: n].rsplit(" ", 1)[0] + "…"


def read_result(base: str, sid: str) -> tuple[str, str]:
    """(issue, texte) de la dernière réponse : issue = succeeded / failed / interrupted / ''."""
    msgs = (call("GET", f"/session/{sid}/message?order=desc&limit=40", base=base).get("data") or [])
    outcome, texts = "", []
    for m in msgs:  # du plus récent au plus ancien
        if m.get("type") == "idle" and not outcome:
            outcome = str(m.get("outcome") or "")
        if m.get("type") == "assistant":
            for part in m.get("content") or []:
                if part.get("type") == "text" and part.get("text", "").strip():
                    texts.append(part["text"])
            if texts:
                break
    return outcome, (texts[0] if texts else "")


def start(request: str, model: str = "", via: str = "copilote") -> dict:
    """Envoie la demande ; renvoie {sid, base, model} ou lève RuntimeError avec un message pour l'utilisateur."""
    base = BRIDGE if via == "claude" else SERVER
    if not up(base):
        ok = start_bridge() if via == "claude" else start_server()
        if not ok:
            raise RuntimeError("Le serveur du Copilote Roblox ne démarre pas." if via != "claude"
                               else "Le pont Claude pour Roblox ne démarre pas.")
    if not studio_open():
        raise RuntimeError("Roblox Studio n'est pas ouvert : ouvre ta place en mode édition, puis redemande.")
    chosen = None
    if via != "claude":
        chosen = models().get(model or ORDER[0]) or models()[ORDER[0]]
    sess = call("POST", "/session", {"title": "JARVIS : " + clean(request, 40)}, base=base)
    sid = (sess.get("data") or sess).get("id")
    if not sid:
        raise RuntimeError("Le Copilote n'a pas créé de conversation.")
    if chosen:  # même ordre que le panneau : agent, modèle, puis message
        for path, body in ((f"/session/{sid}/agent", {"agent": chosen["agent"]}),
                           (f"/session/{sid}/model", {"model": {"id": chosen["id"], "providerID": chosen["providerID"]}})):
            try:
                call("POST", path, body, base=base)
            except RuntimeError as exc:
                log.warning("Copilote %s refusé (%s)", path.rsplit("/", 1)[-1], str(exc)[:100])
    text = (f"[Demande transmise à la voix par JARVIS, l'assistant de l'utilisateur] {request}\n\n"
            "(Travaille directement dans Roblox Studio avec tes outils. Termine par un résumé de deux phrases "
            "maximum, en français, de ce que tu as construit ou modifié.)")
    call("POST", f"/session/{sid}/prompt", {"text": text}, base=base)
    return {"sid": sid, "base": base, "model": model or (ORDER[0] if via != "claude" else "claude")}


def watch(sid: str, base: str, timeout: float = 25 * 60, poll: float = 5.0, first_wait: float = 4.0) -> tuple[str, str]:
    """Attend la fin du travail ; renvoie (issue, texte). issue = succeeded / failed / interrupted / timeout."""
    time.sleep(first_wait)  # le temps que la conversation passe en « active »
    t0 = time.time()
    while time.time() - t0 < timeout:
        try:
            if sid not in (call("GET", "/session/active", base=base).get("data") or {}):
                break
        except Exception:
            pass
        time.sleep(poll)
    else:
        return "timeout", ""
    try:
        outcome, text = read_result(base, sid)
    except Exception as exc:
        return "failed", str(exc)
    return (outcome or "succeeded"), text


def is_limit(text: str) -> bool:
    return any(w in (text or "").lower() for w in LIMIT_WORDS)


def interrupt_all() -> int:
    """Arrête les travaux en cours (Copilote et pont Claude) ; renvoie le nombre de conversations arrêtées."""
    n = 0
    for base in (SERVER, BRIDGE):
        if not up(base):
            continue
        for sid in (call("GET", "/session/active", base=base).get("data") or {}):
            try:
                call("POST", f"/session/{sid}/interrupt", base=base)
                n += 1
            except Exception:
                pass
    return n


def status() -> str:
    parts = [f"Roblox Studio : {'ouvert' if studio_open() else 'fermé'}",
             f"serveur du Copilote : {'en marche' if up(SERVER) else 'arrêté'}"]
    if up(SERVER):
        act = call("GET", "/session/active").get("data") or {}
        parts.append(f"{len(act)} travail(aux) en cours" if act else "aucun travail en cours")
    return " ; ".join(parts) + "."
