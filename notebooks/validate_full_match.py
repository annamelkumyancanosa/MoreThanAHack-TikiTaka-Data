"""Validación indirecta con TODO el partido usando el Smart Tagging como referencia aproximada.

No hay ground truth del partido completo, pero el Smart Tagging dice qué equipo ataca en cada
fase y dónde hay balón parado. Comparamos nuestras predicciones con eso. Solo se imprimen
agregados (porcentajes, conteos), nunca filas de datos.

    python notebooks/validate_full_match.py                    # todas las de evaluation/results
    python notebooks/validate_full_match.py --blocks tikitaka_v2_2   # + detalle por bloque de 5 min

Qué sabemos del Smart Tagging (contrastado con el GT público):
  - Las fases "DEFENDING IN …" son copia exacta de las ofensivas con el equipo al revés, y
    "DEFENSIVE TRANSITION" es el espejo de "ATTACKING TRANSITION" → solo usamos las ofensivas.
  - Las fases de zona (BALL IN FINAL THIRD, BALL IN THE BOX, PLAYERS IN THE BOX) no indican
    quién tiene el balón (coinciden con el GT un 30-45%) → no se usan.
  - Ni el GT coincide al 100% con las fases (las fases son gruesas, incluyen pérdidas cortas y
    parones). Por eso se imprime también el "techo" que saca el GT en la ventana pública.
  - SET PIECES: el equipo es fiable, el tiempo va desfasado unos segundos (de ahí la ventana
    SET_PIECE_WINDOW). Los saques de banda vienen sin equipo (N/A).
"""

import argparse
import glob
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src.tagging import load_tags  # noqa: E402

FPS = 25
RESULTS_DIR = os.path.join(ROOT, "evaluation", "results")
GT_PATH = os.path.join(ROOT, "evaluation", "gt", "BAR-ATH_possession_gt_public.csv")

# Fases en las que el `Team` del tag es el que tiene el balón.
POSSESSION_CODES = ("BUILD UP", "PROGRESSION", "CREATING CHANCES", "LONG BALL",
                    "ATTACKING TRANSITION")
# Margen (frames) alrededor del inicio de un SET PIECE donde buscamos nuestro parón: el tiempo
# del tag puede ir desfasado 3-12 s respecto al vídeo.
SET_PIECE_WINDOW = 12 * FPS
# Tamaño de bloque para el detalle (igual que la tabla de % balón visible de CONTEXT.md).
BLOCK_FRAMES = 5 * 60 * FPS


def graded_mask(n_frames, blocks):
    mask = np.zeros(n_frames, dtype=bool)
    for _, first, last in blocks:
        mask[first:last + 1] = True
    return mask


def fill_x(labels, blocks):
    """Como el scorer: una X repite la última etiqueta de esa parte (X inicial se queda X)."""
    out = labels.copy()
    for _, first, last in blocks:
        last_label = "X"
        for i in range(first, last + 1):
            if out[i] == "X":
                out[i] = last_label
            else:
                last_label = out[i]
    return out


def phase_team(tags, n_frames):
    """Equipo con balón según las fases ofensivas, por frame ('' si no hay fase o se contradicen)."""
    has_h = np.zeros(n_frames, dtype=bool)
    has_a = np.zeros(n_frames, dtype=bool)
    for row in tags[tags.code.isin(POSSESSION_CODES) & tags.team.notna()].itertuples():
        (has_h if row.team == "H" else has_a)[row.start:row.end + 1] = True
    team = np.full(n_frames, "", dtype="<U1")
    team[has_h & ~has_a] = "H"
    team[has_a & ~has_h] = "A"
    return team


def runs(labels, first, last):
    """[(label, start, end)] de rachas dentro de [first, last]."""
    seg = labels[first:last + 1]
    change = np.flatnonzero(seg[1:] != seg[:-1]) + 1
    bounds = np.r_[0, change, len(seg)]
    return [(seg[a], first + a, first + b - 1) for a, b in zip(bounds[:-1], bounds[1:])]


def team_metrics(labels, ref_team, mask):
    """Coincidencia de equipo en frames con fase ofensiva y predicción viva."""
    in_phase = mask & (ref_team != "")
    alive = in_phase & np.isin(labels, ("H", "A"))
    agree = alive & (labels == ref_team)
    return {
        "team_agree": agree.sum() / max(alive.sum(), 1),
        "phase_D": (in_phase & (labels == "D")).sum() / max(in_phase.sum(), 1),
    }


def set_piece_metrics(labels, tags, mask):
    """¿Hay un parón nuestro junto a cada set piece? ¿Reanuda el equipo correcto?

    Para cada SET PIECE miramos [start - SET_PIECE_WINDOW, start + SET_PIECE_WINDOW]: si hay
    algún D nuestro, cuenta como acierto de parón; el equipo que reanuda es la primera etiqueta
    H/A tras el último D de esa ventana.
    """
    hits, team_ok, team_n, n = 0, 0, 0, 0
    for row in tags[tags.code == "SET PIECES"].itertuples():
        lo, hi = max(row.start - SET_PIECE_WINDOW, 0), min(row.start + SET_PIECE_WINDOW, len(labels) - 1)
        if not mask[row.start]:
            continue
        n += 1
        dead = np.flatnonzero(labels[lo:hi + 1] == "D")
        if len(dead) == 0:
            continue
        hits += 1
        if row.team is None or row.type == "Kick Off (Start)":
            continue
        after = labels[lo + dead[-1] + 1:]
        alive = np.flatnonzero(np.isin(after, ("H", "A")))
        if len(alive):
            team_n += 1
            team_ok += after[alive[0]] == row.team
    return {"sp_n": n, "sp_dead": hits / max(n, 1), "sp_team": team_ok / max(team_n, 1)}


def possession_count(labels, blocks):
    return sum(lab in "HA" for _, f, l in blocks for lab, _, _ in runs(labels, f, l))


def summarise(labels, tags, blocks, ref_team=None, mask=None):
    """Una fila de métricas para unas etiquetas (ya con las X rellenadas)."""
    if mask is None:
        mask = graded_mask(len(labels), blocks)
    if ref_team is None:
        ref_team = phase_team(tags, len(labels))
    row = {"poss": possession_count(labels, blocks), "D_%": np.mean(labels[mask] == "D")}
    row.update(team_metrics(labels, ref_team, mask))
    row.update(set_piece_metrics(labels, tags, mask))
    return row


def block_table(labels, tags, blocks, ball_visible):
    """Detalle por bloque de 5 min: dónde nos hundimos y si cuadra con el balón invisible."""
    ref_team = phase_team(tags, len(labels))
    rows = []
    for half, first, last in blocks:
        for k, lo in enumerate(range(first, last + 1, BLOCK_FRAMES)):
            hi = min(lo + BLOCK_FRAMES - 1, last)
            mask = np.zeros(len(labels), dtype=bool)
            mask[lo:hi + 1] = True
            sub = [(half, lo, hi)]
            row = {"half": half, "min": "{}-{}".format(5 * k, 5 * k + 5),
                   "ball_vis": ball_visible[lo:hi + 1].mean(),
                   "poss": possession_count(labels, sub),
                   "D_%": np.mean(labels[lo:hi + 1] == "D")}
            row.update(team_metrics(labels, ref_team, mask))
            rows.append(row)
    return pd.DataFrame(rows)


def load_labels(path):
    return pd.read_csv(path, dtype={"label": str}).label.to_numpy().astype("<U1")


def fmt(df):
    pct = [c for c in df.columns if c in ("D_%", "team_agree", "phase_D", "sp_dead", "sp_team",
                                          "ball_vis")]
    out = df.copy()
    for c in pct:
        out[c] = (100 * out[c]).map("{:.1f}".format)
    return out.to_string()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--blocks", nargs="*", default=[],
                        help="nombres (sin .csv) para imprimir el detalle por bloque de 5 min")
    args = parser.parse_args()

    blocks = half_video_blocks("BAR-ATH")
    tags = load_tags()
    paths = sorted(glob.glob(os.path.join(RESULTS_DIR, "*.csv")))
    preds = {os.path.basename(p)[:-4]: fill_x(load_labels(p), blocks) for p in paths}
    n_frames = len(next(iter(preds.values())))
    ref_team = phase_team(tags, n_frames)

    print("== Partido completo vs Smart Tagging ==")
    print("  team_agree: % frames con fase ofensiva y predicción H/A cuyo equipo coincide")
    print("  phase_D: % de frames de fase ofensiva que predecimos D")
    print("  sp_dead: % set pieces con un D nuestro a ±{} s; sp_team: reanuda el equipo del tag"
          .format(SET_PIECE_WINDOW // FPS))
    table = pd.DataFrame({name: summarise(lab, tags, blocks, ref_team) for name, lab in preds.items()}).T
    print(fmt(table))

    # Techo: lo que saca el propio GT en la ventana pública (las fases no son posesiones exactas).
    gt = load_labels(GT_PATH)
    public = gt != "X"
    pub_blocks = [(1, int(np.flatnonzero(public)[0]), int(np.flatnonzero(public)[-1]))]
    rows = {"GT (techo)": summarise(gt, tags, pub_blocks, ref_team, public)}
    rows.update({name: summarise(lab, tags, pub_blocks, ref_team, public) for name, lab in preds.items()})
    print("\n== Solo ventana pública (referencia; pocas fases → orientativo) ==")
    print(fmt(pd.DataFrame(rows).T.drop(columns=["sp_n", "sp_dead", "sp_team"])))

    if args.blocks:
        from src.atd import load_tracking
        ball_visible = ~np.isnan(load_tracking()["ball"][:, 0])
        for name in args.blocks:
            print("\n== Por bloque de 5 min: {} ==".format(name))
            print(fmt(block_table(preds[name], tags, blocks, ball_visible)))


if __name__ == "__main__":
    main()
