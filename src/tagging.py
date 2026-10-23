"""Smart Tagging del vídeo táctico → DataFrame y reanudaciones (quién saca tras un parón).

    from src.tagging import load_tags, restarts
    tags = load_tags()      # code, team ('H'/'A'/None), type, start, end (frames de vídeo)
    restarts(tags)          # [(frame, HOME/AWAY)] de set pieces con equipo conocido
    set_piece_frames(tags)  # frames de inicio de todos los set pieces (también sin equipo)

Lo contrastado (detalle en notebooks/validate_full_match.py y CONTEXT.md):
  - SET PIECES: el `Team` es el que saca y es fiable; el tag empieza durante el parón, de media
    unos 6.5 s antes de la reanudación. Los saques de banda vienen sin equipo (N/A).
  - Kick Off (After Goal) viene sin equipo, pero saca el rival del último GOALS.
"""

import os
import sys
import xml.etree.ElementTree as ET

import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import asset_paths  # noqa: E402
from src.atd import HOME, AWAY  # noqa: E402

FPS = 25
TEAM_CODE = {"Barcelona": "H", "Atletic Club": "A"}
TEAM_ID = {"H": HOME, "A": AWAY}


def load_tags():
    """Smart Tagging como DataFrame: code, team (H/A/None), type, start, end (frames de vídeo)."""
    path = asset_paths()["smart_tagging"]
    rows = []
    for inst in ET.parse(path).getroot().iter("instance"):
        labels = {lab.findtext("group"): lab.findtext("text") for lab in inst.findall("label")}
        rows.append({
            "code": inst.findtext("code"),
            "team": TEAM_CODE.get(labels.get("Team")),
            "type": labels.get("Type"),
            "start": int(round(float(inst.findtext("start")) * FPS)),
            "end": int(round(float(inst.findtext("end")) * FPS)),
        })
    return pd.DataFrame(rows).sort_values("start", ignore_index=True)


def restarts(tags):
    """[(frame de inicio del tag, HOME/AWAY)] de cada set piece cuyo equipo que saca conocemos."""
    out = []
    last_scorer = None
    for row in tags.itertuples():
        if row.code == "GOALS" and row.team is not None:
            last_scorer = row.team
        if row.code != "SET PIECES":
            continue
        team = row.team
        if team is None and row.type == "Kick Off (After Goal)" and last_scorer is not None:
            team = "A" if last_scorer == "H" else "H"
        if team is not None:
            out.append((row.start, TEAM_ID[team]))
    return out


def set_piece_frames(tags):
    """Frame de inicio de cada SET PIECE, tenga equipo o no (los saques de banda vienen sin él)."""
    return tags.loc[tags.code == "SET PIECES", "start"].to_numpy()
