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

Desde v4.0 también contra la TV (src/broadcast.py), que no depende del tracking táctico:
  - D_tv: % de frames con la TV en directo que predecimos D (GT público: 7%).
  - live_tvoff: % de frames con la TV fuera de directo (repetición, primer plano) que predecimos
    vivos (GT público: 47%).
  - susp_D: parones sin balón fuera ni set piece y con la TV en directo >= 50% del tiempo (los que
    quita v4.0: a partir de v4.0 es circular, como `reanuda`).
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
from src.tagging import load_tags, set_piece_frames  # noqa: E402

FPS = 25
RESULTS_DIR = os.path.join(ROOT, "evaluation", "results")
GT_PATH = os.path.join(ROOT, "evaluation", "gt", "BAR-ATH_possession_gt_public.csv")

# Fases en las que el `Team` del tag es el que tiene el balón.
POSSESSION_CODES = ("BUILD UP", "PROGRESSION", "CREATING CHANCES", "LONG BALL",
                    "ATTACKING TRANSITION")
# Margen (frames) alrededor del inicio de un SET PIECE donde buscamos nuestro parón: el tiempo
# del tag puede ir desfasado 3-12 s respecto al vídeo.
SET_PIECE_WINDOW = 12 * FPS
# Margen (frames) alrededor del inicio de un ATTACKING TRANSITION donde buscamos el cambio de
# posesión hacia ese equipo (métrica de robos, s3).
STEAL_WINDOW = 8 * FPS
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


def steal_metrics(labels, tags, mask):
    """Robos: % de ATTACKING TRANSITION con un cambio hacia ese equipo (desde el rival o desde D)
    a ±STEAL_WINDOW de su inicio. Sirve para comparar histéresis sin premiar no cambiar nunca."""
    hits = n = 0
    for row in tags[(tags.code == "ATTACKING TRANSITION") & tags.team.notna()].itertuples():
        if not mask[row.start]:
            continue
        n += 1
        seg = labels[max(row.start - STEAL_WINDOW, 0):row.start + STEAL_WINDOW + 1]
        hits += bool(np.any((seg[1:] == row.team) & (seg[:-1] != row.team)))
    return {"steals_n": n, "steals": hits / max(n, 1)}


def tv_metrics(labels, tv, mask):
    """Métricas contra la TV. `tv` = {"live": tv_live, "out": ball_out, "sp": set_piece_frames}."""
    from src.possession import TV_LIVE_MAX_SHARE, TV_OUT_SLACK, TV_TAG_AFTER, TV_TAG_BEFORE
    live, out, sp = tv["live"], tv["out"], np.asarray(tv["sp"])
    on, off = mask & live, mask & ~live
    suspicious = 0
    dead = np.r_[False, labels == "D", False] & np.r_[False, mask, False]
    edges = np.flatnonzero(np.diff(dead.astype(np.int8)))
    for a, e in zip(edges[::2], edges[1::2]):
        if (not out[max(a - TV_OUT_SLACK, 0):e].any()
                and not np.any((sp >= a - TV_TAG_BEFORE) & (sp < e + TV_TAG_AFTER))
                and live[a:e].mean() >= TV_LIVE_MAX_SHARE):
            suspicious += 1
    return {"D_tv": np.mean(labels[on] == "D"),
            "live_tvoff": np.mean(np.isin(labels[off], ("H", "A"))),
            "susp_D": suspicious}


def load_tv(blocks):
    """Lo que necesita tv_metrics: TV en directo, balón fuera y set pieces."""
    from src.atd import load_tracking
    from src.broadcast import load_tv_live
    from src.possession import ball_out
    trk = load_tracking()
    return {"live": load_tv_live(trk, blocks), "out": ball_out(trk), "sp": set_piece_frames(load_tags())}


def possession_count(labels, blocks):
    return sum(lab in "HA" for _, f, l in blocks for lab, _, _ in runs(labels, f, l))


def summarise(labels, tags, blocks, ref_team=None, mask=None, tv=None):
    """Una fila de métricas para unas etiquetas (ya con las X rellenadas)."""
    if mask is None:
        mask = graded_mask(len(labels), blocks)
    if ref_team is None:
        ref_team = phase_team(tags, len(labels))
    row = {"poss": possession_count(labels, blocks), "D_%": np.mean(labels[mask] == "D")}
    row.update(team_metrics(labels, ref_team, mask))
    row.update(set_piece_metrics(labels, tags, mask))
    row.update(steal_metrics(labels, tags, mask))
    if tv is not None:
        row.update(tv_metrics(labels, tv, mask))
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
                                          "ball_vis", "steals", "D_tv", "live_tvoff")]
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
    print("  steals: % ATTACKING TRANSITION con un cambio hacia ese equipo a ±{} s".format(
        STEAL_WINDOW // FPS))
    print("  sp_dead: % set pieces con un D nuestro a ±{} s; sp_team: reanuda el equipo del tag"
          .format(SET_PIECE_WINDOW // FPS))
    print("  D_tv: % frames con TV en directo que predecimos D (GT público 7%); live_tvoff: % frames con")
    print("  TV fuera que predecimos vivos (GT 47%); susp_D: parones sin balón fuera ni set piece con TV")
    print("  en directo >= 50% (circular desde v4.0)")
    tv = load_tv(blocks)
    table = pd.DataFrame({name: summarise(lab, tags, blocks, ref_team, tv=tv)
                          for name, lab in preds.items()}).T
    print(fmt(table))

    # Techo: lo que saca el propio GT en la ventana pública (las fases no son posesiones exactas).
    gt = load_labels(GT_PATH)
    public = gt != "X"
    pub_blocks = [(1, int(np.flatnonzero(public)[0]), int(np.flatnonzero(public)[-1]))]
    rows = {"GT (techo)": summarise(gt, tags, pub_blocks, ref_team, public, tv)}
    rows.update({name: summarise(lab, tags, pub_blocks, ref_team, public, tv)
                 for name, lab in preds.items()})
    print("\n== Solo ventana pública (referencia; pocas fases → orientativo) ==")
    print(fmt(pd.DataFrame(rows).T.drop(columns=["sp_n", "sp_dead", "sp_team", "steals_n", "steals"])))

    if args.blocks:
        from src.atd import load_tracking
        ball_visible = ~np.isnan(load_tracking()["ball"][:, 0])
        for name in args.blocks:
            print("\n== Por bloque de 5 min: {} ==".format(name))
            print(fmt(block_table(preds[name], tags, blocks, ball_visible)))


if __name__ == "__main__":
    main()
