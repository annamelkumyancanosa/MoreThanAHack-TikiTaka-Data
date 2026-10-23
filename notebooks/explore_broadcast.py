"""Qué aporta el broadcast (TV) al tactical: alineación, balón y estado de la TV. Solo agregados.

Resultados (s5, v3.9.1; detalle en VERSIONS.md, v4.0):
  - Alineación por colocación de jugadores: táctico = broadcast + 4013 (1ª) / 26919 (2ª),
    jugadores a 0.7-0.8 m de mediana.
  - Balón: el broadcast lo ve en solo 3.7 de los 42.7 min sin balón del táctico.
  - TV en directo vs GT público: P(D | TV en directo) 7%, P(D | TV fuera) 53%.

    python notebooks/explore_broadcast.py
"""

import os
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src.atd import load_tracking  # noqa: E402
from src.broadcast import load_tv_live  # noqa: E402
from src.possession import _runs, ball_out  # noqa: E402
from src.tagging import load_tags, set_piece_frames  # noqa: E402
from run import SECOND_HALF_KICKOFF  # noqa: E402

FPS = 25
GT_PATH = os.path.join(ROOT, "evaluation", "gt", "BAR-ATH_possession_gt_public.csv")


def main(name):
    warnings.simplefilter("ignore", RuntimeWarning)
    blocks = half_video_blocks("BAR-ATH")
    tac, brd = load_tracking(), load_tracking(source="broadcast")
    live, offsets = load_tv_live(tac, blocks, return_offsets=True)
    n = len(tac["ball"])
    graded = np.zeros(n, dtype=bool)
    bidx = np.full(n, -1)
    for half, first, last in blocks:
        graded[first:last + 1] = True
        t = np.arange(first, last + 1)
        b = t - offsets[half]
        ok = (b >= 0) & (b < len(brd["ball"]))
        bidx[t[ok]] = b[ok]
    graded[blocks[1][1]:SECOND_HALF_KICKOFF] = False
    tac_ball = ~np.isnan(tac["ball"][:, 0])
    brd_ball = np.zeros(n, dtype=bool)
    brd_ball[bidx >= 0] = ~np.isnan(brd["ball"][bidx[bidx >= 0], 0])
    brd_ball &= live

    print("== Alineación ==  desfases", offsets, "| TV en directo {:.0%} de los frames puntuados".format(
        live[graded].mean()))
    hidden = graded & ~tac_ball
    print("== Balón ==  sin balón en el táctico {:.1f} min; el broadcast lo ve en {:.1f} min".format(
        hidden.sum() / FPS / 60, (hidden & brd_ball).sum() / FPS / 60))

    gt = pd.read_csv(GT_PATH, dtype={"label": str}).label.to_numpy()
    pub = gt != "X"
    print("== TV vs GT público ==  P(D | TV en directo) {:.0%} | P(D | TV fuera) {:.0%}".format(
        np.mean(gt[pub & live] == "D"), np.mean(gt[pub & ~live] == "D")))
    for a, e in _runs(pub & (gt == "D")):
        print("  parón del GT de {:.1f} s: TV en directo {:.0%} del tiempo".format(
            (e - a) / FPS, live[a:e].mean()))

    lab = pd.read_csv(os.path.join(ROOT, "evaluation", "results", name + ".csv"),
                      dtype={"label": str}).label.to_numpy()
    out, sp = ball_out(tac), set_piece_frames(load_tags())
    print("== {} en el partido ==  P(D | TV en directo) {:.0%} | P(D | TV fuera) {:.0%}".format(
        name, np.mean(lab[graded & live] == "D"), np.mean(lab[graded & ~live] == "D")))
    rows = []
    for a, e in _runs(graded & (lab == "D")):
        rows.append((e - a, live[a:e].mean(), out[max(a - 2 * FPS, 0):e].any(),
                     np.any((sp >= a - 5 * FPS) & (sp < e + 2 * FPS))))
    rows = np.array(rows, dtype=float)
    for lo, hi in ((0, .25), (.25, .5), (.5, .75), (.75, 1.01)):
        m = (rows[:, 1] >= lo) & (rows[:, 1] < hi)
        plain = m & (rows[:, 2] == 0) & (rows[:, 3] == 0)
        print("  parones con TV en directo {:3.0f}-{:3.0f}% del tiempo: {:3d} ({:.1f} min), de ellos "
              "sin balón fuera ni set piece {}".format(100 * lo, 100 * hi, int(m.sum()),
                                                        rows[m, 0].sum() / FPS / 60, int(plain.sum())))


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tikitaka_v3_9_1")
