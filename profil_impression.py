"""Construit le profil complet « Ender 3 + PLA » de PrusaSlicer à partir du fichier fournisseur Creality.ini.

Les profils du fichier fournisseur héritent les uns des autres (clé « inherits », plusieurs parents possibles séparés par
« ; »). PrusaSlicer en ligne de commande ne résout pas toujours bien ces héritages : ici on les résout nous-mêmes et on
écrit UN fichier .ini complet, chargé ensuite avec --load (résultat identique à chaque fois, vérifiable).

    python profil_impression.py            -> écrit ~/.openjarvis/impression3d/ender3_pla.ini
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

VENDOR = Path(r"C:\Program Files\Prusa3D\PrusaSlicer\resources\profiles\Creality.ini")
OUT = Path.home() / ".openjarvis" / "impression3d" / "ender3_pla.ini"
PRINTER = "Creality Ender-3 (0.4 mm nozzle)"
PRINT = "0.20 mm NORMAL (0.4 mm nozzle) @CREALITY"
FILAMENT = "Generic PLA @CREALITY"


def parse(path: Path) -> dict[str, dict[str, str]]:
    sections: dict[str, dict[str, str]] = {}
    cur = None
    for line in path.read_text(encoding="utf-8").splitlines():
        m = re.match(r"^\[(.+)\]\s*$", line)
        if m:
            cur = sections.setdefault(m.group(1), {})
            continue
        if cur is None or not line.strip() or line.lstrip().startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            cur[k.strip()] = v.strip()
    return sections


def resolve(sections: dict, kind: str, name: str, seen: tuple = ()) -> dict[str, str]:
    key = f"{kind}:{name}"
    if key not in sections:
        raise KeyError(f"Profil introuvable : [{key}]")
    if key in seen:
        raise ValueError(f"Héritage en boucle : {key}")
    own = sections[key]
    out: dict[str, str] = {}
    for parent in [p.strip() for p in own.get("inherits", "").split(";") if p.strip()]:
        out.update(resolve(sections, kind, parent, seen + (key,)))
    out.update({k: v for k, v in own.items() if k != "inherits"})
    return out


def build(out: Path = OUT) -> Path:
    s = parse(VENDOR)
    cfg: dict[str, str] = {}
    for kind, name in (("print", PRINT), ("filament", FILAMENT), ("printer", PRINTER)):
        cfg.update(resolve(s, kind, name))
    for k in ("renamed_from", "alias", "compatible_printers", "compatible_printers_condition", "compatible_prints",
              "compatible_prints_condition"):
        cfg.pop(k, None)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text("".join(f"{k} = {v}\n" for k, v in sorted(cfg.items())), encoding="utf-8")
    return out


if __name__ == "__main__":
    p = build(Path(sys.argv[1]) if len(sys.argv) > 1 else OUT)
    print(p)
