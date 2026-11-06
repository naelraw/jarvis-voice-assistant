"""Agents IA de JARVIS (demandé le 2026-10-26) : un PATRON qui répartit le travail entre des SPÉCIALISTES.

- JARVIS (la voix) confie une tâche longue ou complexe au patron avec l'outil « delegue ».
- Le patron choisit le ou les spécialistes adaptés, les fait travailler EN ARRIÈRE-PLAN (3 au plus à la fois, pour
  rester dans les quotas gratuits), puis rédige une synthèse que JARVIS annonce.
- Chaque spécialiste n'a que ses outils (une dizaine au lieu d'une centaine) et ses consignes.
- SÉCURITÉ : un agent ne peut JAMAIS confirmer une action (suppression, envoi, impression, téléchargement…) : les
  outils à confirmation lui sont interdits et l'argument « confirme » est retiré ; s'il faut confirmer, il le dit dans
  son rapport et c'est JARVIS qui demande à l'utilisateur.
- Tout est suivi étape par étape (page « Agents » de l'interface).

Modèle : Gemini rapide (gratuit), Groq en secours. Uniquement des services gratuits.
"""
from __future__ import annotations

import json
import re
import threading
import time
import uuid

J = None  # module jarvis_voice (donné par setup)

AGENTS: dict[str, dict] = {
    "impression": {
        "name": "Impression 3D", "icon": "printer", "color": "#ff9f43",
        "desc": "Cherche des modèles 3D, prépare et surveille les impressions",
        "tools": ["imprimante", "modeles_3d", "web_search", "wikipedia"],
        "prompt": "Tu es le spécialiste IMPRESSION 3D (Ender 3, PLA, plateau 220×220 mm). Tu cherches des modèles "
                  "(modeles_3d, en anglais de préférence), tu vérifies l'état de l'imprimante et tu conseilles "
                  "(remplissage, supports, durée). Tu ne lances JAMAIS une impression ni un téléchargement : propose-le.",
    },
    "radar": {
        "name": "PC Radar", "icon": "radar", "color": "#2ed573",
        "desc": "Le site pcradar.tech : visites, tickets, prix, relevé",
        "tools": ["pcradar_report", "pcradar_ticket_details", "releve_prix", "check_website", "web_search"],
        "prompt": "Tu es le spécialiste PC RADAR (site pcradar.tech de l'utilisateur : comparateur de prix de composants "
                  "PC). Tu analyses les visites, les tickets, les prix suspects, le catalogue et le relevé des prix, et tu "
                  "proposes des actions concrètes et chiffrées. Tu ne modifies rien toi-même : propose.",
    },
    "mails": {
        "name": "Mails & agenda", "icon": "mail", "color": "#1e90ff",
        "desc": "Lit, trie et résume les mails, regarde l'agenda et les rappels",
        "tools": ["check_emails", "read_email", "search_emails", "agenda", "list_reminders"],
        "prompt": "Tu es le spécialiste MAILS & AGENDA. Tu lis, tries et résumes les mails (important d'abord, pubs "
                  "ignorées), tu regardes l'agenda et les rappels. Tu n'envoies RIEN : si une réponse est utile, rédige "
                  "un brouillon dans ton rapport.",
    },
    "recherche": {
        "name": "Recherche", "icon": "search", "color": "#a55eea",
        "desc": "Fouille le web, l'actualité, Wikipédia et YouTube",
        "tools": ["web_search", "wikipedia", "news_headlines", "youtube_search", "convert_currency", "get_weather"],
        "prompt": "Tu es le spécialiste RECHERCHE. Tu fais plusieurs recherches si besoin, tu recoupes les sources, tu "
                  "donnes des chiffres et des faits précis, jamais de mémoire. Cite brièvement d'où vient l'info.",
    },
    "pc": {
        "name": "PC & jeux", "icon": "chip", "color": "#ff4757",
        "desc": "État du PC, problèmes, fichiers, jeux",
        "tools": ["system_status", "diagnose_pc", "etat_systeme", "find_files", "search_file_contents", "list_windows",
                  "check_virustotal"],
        "prompt": "Tu es le spécialiste PC & JEUX (PC gamer de l'utilisateur, Windows 11, Radeon RX 6650 XT). Tu "
                  "diagnostiques, tu cherches des fichiers, tu expliques les problèmes et tu proposes des solutions. "
                  "Tu ne modifies rien toi-même : propose.",
    },
}

MAX_STEPS = 6          # appels d'outils au plus par spécialiste
MAX_PARALLEL = 3       # spécialistes en même temps (quotas gratuits)
_SEM = threading.Semaphore(MAX_PARALLEL)
_LOCK = threading.Lock()
JOBS: list[dict] = []  # les 40 dernières tâches (patron et spécialistes)

RULES = ("Réponds en français. Utilise tes outils autant que nécessaire (6 appels au plus), puis termine par un RAPPORT "
         "court et concret (6 phrases au plus, chiffres précis, pas de liste à rallonge). Ne devine jamais : si un outil "
         "échoue, dis-le. Tu ne peux confirmer AUCUNE action : si tu voulais FAIRE une action qui exige le oui de "
         "l'utilisateur (supprimer, envoyer, imprimer, télécharger), termine ton rapport par « À CONFIRMER : … » en disant "
         "exactement quelle action. N'écris JAMAIS « À CONFIRMER » pour un simple conseil ou une vérification à faire.")


def _now() -> float:
    return time.time()


def _job(agent: str, task: str, parent: str = "") -> dict:
    j = {"id": uuid.uuid4().hex[:8], "agent": agent, "task": task[:300], "status": "attente", "steps": [],
         "start": _now(), "end": 0.0, "result": "", "parent": parent, "children": []}
    with _LOCK:
        JOBS.append(j)
        del JOBS[:-40]
    return j


def _step(j: dict, text: str, kind: str = "info", tool: str = "") -> None:
    j["steps"].append({"t": _now(), "text": text[:220], "kind": kind, "tool": tool})
    del j["steps"][:-30]


def _label(name: str, args: dict) -> str:
    lab = (getattr(J, "TOOL_LABELS", {}) or {}).get(name) or name.replace("_", " ")
    arg = next((str(v) for v in args.values() if isinstance(v, str) and v.strip()), "")
    return f"{lab}" + (f" : {arg[:60]}" if arg else "")


# ---- appel du modèle (non diffusé, avec outils) ------------------------------------------------------------------

def _chat(messages: list[dict], tools: list[dict] | None, fast: bool = True) -> dict:
    """Message de réponse au format OpenAI ({content, tool_calls}). Gemini d'abord, Groq en secours."""
    errors = []
    if J.use_gemini():
        main, quick = J.gemini_models()
        body = {"model": quick if fast else main, "messages": messages, "temperature": 0.3}
        if tools:
            body["tools"] = tools
        try:
            r = J._gemini_post(body)
            return r.json()["choices"][0]["message"]
        except Exception as exc:
            errors.append(f"Gemini : {str(exc)[:120]}")
    if J.groq_key():
        msgs = json.loads(json.dumps(messages))
        for m in msgs:
            for tc in m.get("tool_calls") or []:
                tc.pop("extra_content", None)
        body = {"model": J.groq_model(), "messages": msgs, "temperature": 0.3}
        if tools:
            body["tools"] = tools
        try:
            r = J.httpx.post(f"{J.GROQ_BASE}/chat/completions", json=body, timeout=60,
                             headers={"Authorization": f"Bearer {J.groq_key()}"})
            r.raise_for_status()
            return r.json()["choices"][0]["message"]
        except Exception as exc:
            errors.append(f"Groq : {str(exc)[:120]}")
    raise RuntimeError("Aucune IA disponible (" + " ; ".join(errors) + ")")


def _tools_for(agent: str) -> list[dict]:
    names = set(AGENTS[agent]["tools"]) - set(getattr(J, "LIVE_CONFIRM_TOOLS", set()))
    out = []
    for t in J.TOOLS_SPEC:
        fn = t["function"]
        if fn["name"] in names and fn["name"] in J.TOOLS:
            p = json.loads(json.dumps(fn["parameters"]))
            p.get("properties", {}).pop("confirme", None)  # un agent ne confirme jamais rien
            if "confirme" in p.get("required", []):
                p["required"].remove("confirme")
            out.append({"type": "function", "function": {"name": fn["name"], "description": fn["description"], "parameters": p}})
    return out


# ---- un spécialiste au travail -----------------------------------------------------------------------------------

def run_agent(agent: str, task: str, parent: str = "") -> dict:
    j = _job(agent, task, parent)
    _step(j, "En file d'attente (3 agents au plus en même temps)", "wait")
    with _SEM:
        j["status"] = "en_cours"
        _step(j, "Commence la tâche", "start")
        a = AGENTS[agent]
        tools = _tools_for(agent)
        msgs = [{"role": "system", "content": f"{a['prompt']} {RULES} Date : {time.strftime('%d/%m/%Y %H:%M')}."},
                {"role": "user", "content": task}]
        try:
            for _ in range(MAX_STEPS + 1):
                _step(j, "Réfléchit…", "think")
                m = _chat(msgs, tools if len(msgs) < 2 + MAX_STEPS * 2 else None)
                calls = m.get("tool_calls") or []
                for i, c in enumerate(calls):
                    c["id"] = c.get("id") or f"call_{int(_now() * 1000)}_{i}"
                entry = {"role": "assistant", "content": m.get("content") or ""}
                if calls:
                    entry["tool_calls"] = calls
                msgs.append(entry)
                if not calls:
                    j["result"] = (m.get("content") or "").strip() or "Rien à signaler."
                    break
                for c in calls:
                    fn = c.get("function", {})
                    name = fn.get("name", "")
                    try:
                        args = json.loads(fn.get("arguments") or "{}") if isinstance(fn.get("arguments"), str) else (fn.get("arguments") or {})
                    except Exception:
                        args = {}
                    args.pop("confirme", None)
                    args.pop("confirmed", None)
                    allowed = name in {t["function"]["name"] for t in tools}
                    _step(j, _label(name, args), "tool", name)
                    if not allowed:
                        res = f"Outil {name} interdit à cet agent."
                    else:
                        try:
                            res = str(J.TOOLS[name](**args))
                        except Exception as exc:
                            res = f"Erreur pendant {name} : {exc}"
                    J.log.info("Agent %s : %s %s -> %s", agent, name, args, res[:200])
                    msgs.append({"role": "tool", "tool_call_id": c.get("id", "call"), "content": res[:6000]})
            else:
                j["result"] = "Arrêté : trop d'étapes."
            j["status"] = "a_confirmer" if "À CONFIRMER" in j["result"].upper() else "fini"
            _step(j, "Rapport rendu", "done")
        except Exception as exc:
            j["status"], j["result"] = "erreur", f"Erreur : {str(exc)[:200]}"
            _step(j, j["result"], "error")
            J.log.warning("Agent %s en erreur : %s", agent, exc)
        j["end"] = _now()
    return j


# ---- le patron -----------------------------------------------------------------------------------------------------

def _route(task: str) -> list[str]:
    """Le patron choisit 1 à 3 spécialistes (IA rapide), avec un tri par mots-clés en secours."""
    menu = "\n".join(f"- {k} : {a['desc']}" for k, a in AGENTS.items())
    try:
        m = _chat([{"role": "system", "content": "Tu es le PATRON d'une équipe d'agents IA. Choisis le ou les agents "
                                                 "(1 à 3, le moins possible) pour cette tâche. Réponds UNIQUEMENT par "
                                                 "leurs clés séparées par des virgules.\n" + menu},
                   {"role": "user", "content": task}], None)
        keys = [k for k in re.findall(r"[a-z]+", (m.get("content") or "").lower()) if k in AGENTS]
        if keys:
            return list(dict.fromkeys(keys))[:3]
    except Exception:
        pass
    t = J.norm(task)
    guess = [k for k, words in (("impression", "imprim stl modele 3d filament buse"), ("radar", "radar pcradar ticket prix fiche site"),
                                ("mails", "mail courriel agenda rappel rendez"), ("pc", "pc ordinateur jeu fichier lent bug"))
             if any(w in t for w in words.split())]
    return guess[:3] or ["recherche"]


def run_boss(task: str, agents: list[str] | None = None, announce=None) -> dict:
    boss = _job("patron", task)
    boss["status"] = "en_cours"
    _step(boss, "Lit la demande", "start")
    keys = [a for a in (agents or []) if a in AGENTS] or _route(task)
    _step(boss, "Confie le travail à : " + ", ".join(AGENTS[k]["name"] for k in keys), "assign")
    results: dict[str, dict] = {}
    threads = []
    for k in keys:
        sub = f"{task}\n(Tu fais partie d'une équipe : occupe-toi seulement de ce qui relève de ta spécialité.)" if len(keys) > 1 else task
        th = threading.Thread(target=lambda k=k, sub=sub: results.__setitem__(k, run_agent(k, sub, boss["id"])),
                              daemon=True, name=f"agent-{k}")
        th.start()
        threads.append(th)
    time.sleep(0.2)
    boss["children"] = [j["id"] for j in JOBS if j.get("parent") == boss["id"]]
    for th in threads:
        th.join(600)
    _step(boss, "Rassemble les rapports", "think")
    reports = "\n\n".join(f"[{AGENTS[k]['name']}] {results[k]['result']}" for k in keys if k in results)
    if len(keys) == 1:
        boss["result"] = results.get(keys[0], {}).get("result", "Pas de rapport.")
    else:
        try:
            m = _chat([{"role": "system", "content": "Tu es le PATRON : fais la synthèse des rapports de ton équipe pour "
                                                     "l'utilisateur, en 5 phrases au plus, l'essentiel d'abord. Recopie une "
                                                     "ligne « À CONFIRMER : … » SEULEMENT si un rapport en contient une ; "
                                                     "sinon n'écris jamais ces mots."},
                       {"role": "user", "content": f"Demande : {task}\n\nRapports :\n{reports}"}], None)
            boss["result"] = (m.get("content") or "").strip() or reports
        except Exception:
            boss["result"] = reports
    states = [results.get(k, {}).get("status") for k in keys]
    if "a_confirmer" not in states:  # « À CONFIRMER » vide ajouté par la synthèse : retiré
        boss["result"] = re.sub(r"\s*À CONFIRMER\s*:?\s*$", "", boss["result"], flags=re.I).strip()
    boss["status"] = ("erreur" if all(s == "erreur" for s in states) else
                      "a_confirmer" if "a_confirmer" in states else "fini")
    boss["end"] = _now()
    _step(boss, "Synthèse prête", "done")
    if announce:
        try:
            announce(boss)
        except Exception:
            J.log.exception("Annonce des agents")
    return boss


def state() -> dict:
    with _LOCK:
        jobs = [dict(j) for j in JOBS]
    busy = {j["agent"]: j for j in jobs if j["status"] in ("attente", "en_cours")}
    return {"ok": True, "now": _now(),
            "agents": [{"key": "patron", "name": "Patron", "icon": "crown", "color": "#00d2ff",
                        "desc": "Répartit le travail et fait la synthèse", "busy": "patron" in busy,
                        "current": (busy.get("patron") or {}).get("steps", [{}])[-1].get("text", "") if "patron" in busy else ""}]
            + [{"key": k, "name": a["name"], "icon": a["icon"], "color": a["color"], "desc": a["desc"],
                "tools": a["tools"], "busy": k in busy,
                "current": (busy[k]["steps"][-1]["text"] if k in busy and busy[k]["steps"] else ""),
                # outil utilisé en ce moment (dernière étape « outil » encore récente) : la feuille s'allume dans l'arbre
                "tool": next((s_.get("tool", "") for s_ in reversed(busy[k]["steps"]) if s_.get("kind") == "tool"
                              and _now() - s_["t"] < 8), "") if k in busy else ""}
               for k, a in AGENTS.items()],
            "jobs": list(reversed(jobs))}


def setup(module) -> None:
    global J
    J = module
