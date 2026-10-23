"""Genera nuestra predicción, la valida y la puntúa en la ventana pública.

    python run.py                 # escribe evaluation/results/tikitaka_v1.csv y puntúa
    python run.py --name prueba   # mismo, con otro nombre (para comparar variantes)

Además imprime diagnósticos del partido completo (nº de posesiones, duraciones, y comparación con
el Smart Tagging): no es ground truth, pero sirve para ver si una mejora pública se sostiene.
"""

import argparse
import os
import subprocess
import sys

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src.atd import load_tracking  # noqa: E402
from src.possession import predict  # noqa: E402
from src.tagging import load_tags, restarts  # noqa: E402
from notebooks.validate_full_match import fill_x, summarise  # noqa: E402

RESULTS_DIR = os.path.join(ROOT, "evaluation", "results")
SECOND_HALF_KICKOFF = 113742  # publicado en FAQ.md
FPS = 25


def write_submission(path, labels):
    with open(path, "w") as handle:
        handle.write("frame,label\n")
        handle.writelines("{},{}\n".format(i, label) for i, label in enumerate(labels))


def diagnostics(labels, blocks):
    """Resumen de nuestras posesiones en todo el partido (rachas de H o A)."""
    durations, n_dead = [], 0
    for _, first, last in blocks:
        seg = labels[first:last + 1]
        change = np.flatnonzero(seg[1:] != seg[:-1]) + 1
        bounds = np.r_[0, change, len(seg)]
        for a, b in zip(bounds[:-1], bounds[1:]):
            if seg[a] in "HA":
                durations.append((b - a) / FPS)
            elif seg[a] == "D":
                n_dead += 1
    durations = np.array(durations)
    graded = np.concatenate([labels[f:l + 1] for _, f, l in blocks])
    print("\n== Diagnóstico partido completo (nuestra predicción) ==")
    print("  posesiones: {}  | duración media {:.1f} s, mediana {:.1f} s".format(
        len(durations), durations.mean(), np.median(durations)))
    print("  posesiones < 1 s: {}  | tramos D: {}".format(int((durations < 1).sum()), n_dead))
    print("  reparto frames puntuados: " + "  ".join(
        "{} {:.1%}".format(k, np.mean(graded == k)) for k in "HADX"))


def full_match_check(labels, blocks):
    """Comparación con el Smart Tagging en todo el partido (detalle: notebooks/validate_full_match.py)."""
    row = summarise(fill_x(np.asarray(labels).astype("<U1"), blocks), load_tags(), blocks)
    print("  vs Smart Tagging: equipo coincide {:.1%} | D en fase ofensiva {:.1%} | "
          "set pieces con D cerca {:.1%}, reanuda el equipo del tag {:.1%} | robos {:.0f}/{}".format(
              row["team_agree"], row["phase_D"], row["sp_dead"], row["sp_team"],
              row["steals"] * row["steals_n"], row["steals_n"]))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="tikitaka_v3_5")
    args = parser.parse_args()

    blocks = half_video_blocks("BAR-ATH")
    labels = predict(load_tracking(), blocks, SECOND_HALF_KICKOFF, restarts(load_tags()))

    path = os.path.join(RESULTS_DIR, args.name + ".csv")
    write_submission(path, labels)
    print("escrito", os.path.relpath(path, ROOT))
    diagnostics(labels, blocks)
    full_match_check(labels, blocks)

    sys.stdout.flush()  # que lo nuestro salga antes que la salida de los subprocesos
    py = sys.executable
    subprocess.run([py, os.path.join(ROOT, "evaluation", "validate_submission.py"), path], check=True)
    subprocess.run([py, os.path.join(ROOT, "evaluation", "run_evaluation.py")], check=True)


if __name__ == "__main__":
    main()
