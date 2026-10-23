"""Simulación de balón invisible: esconde el balón en tramos donde sí se ve y mide el pipeline.

En el partido el balón no se ve ~43 de los 104 min puntuados y ahí no hay referencia: la ventana
pública casi no tiene balón invisible y el Smart Tagging es automático (sin balón apenas marca
fases). Aquí la referencia es nuestra propia predicción con el balón visible (vivo/muerto F1 0.95
en la ventana pública): escondemos el balón en ventanas de L s dentro de tramos visibles, volvemos
a pasar el pipeline y comparamos. Solo se imprimen agregados.

Ojo: los tramos visibles son sobre todo juego (~10% D), y los huecos reales seguramente tienen más
parón (balón fuera de plano, en manos del que saca). La simulación mide bien "juego → D", y mal el
coste de perder parones reales.

    python notebooks/simulate_hidden_ball.py
"""

import os
import sys
import warnings

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src import possession  # noqa: E402
from src.atd import load_tracking  # noqa: E402
from src.tagging import load_tags, restarts  # noqa: E402
from run import SECOND_HALF_KICKOFF  # noqa: E402

FPS = 25
# Margen (frames) entre la ventana escondida y el borde del tramo visible, y entre ventanas.
MARGIN = 10 * FPS
WINDOW_LENGTHS_S = (10, 20)


def windows(visible, graded, length):
    """Ventanas de `length` frames dentro de tramos visibles, con MARGIN a cada lado."""
    out = []
    for a, e in possession._runs(visible & graded):
        s = a + MARGIN
        while s + length + MARGIN <= e:
            out.append((s, s + length))
            s += length + 2 * MARGIN
    return out


def simulate(trk, blocks, rs, base, graded, length):
    visible = ~np.isnan(trk["ball"][:, 0])
    mask = np.zeros(len(base), dtype=bool)
    win = windows(visible, graded, length)
    for a, e in win:
        mask[a:e] = True
    hidden = dict(trk, ball=trk["ball"].copy())
    hidden["ball"][mask] = np.nan
    lab = possession.predict(hidden, blocks, SECOND_HALF_KICKOFF, rs)
    ref, got = base[mask], lab[mask]
    live = ref != "D"
    both = live & (got != "D")
    return {
        "ventanas": len(win), "min": mask.sum() / FPS / 60,
        "ref_D": np.mean(~live), "pred_D": np.mean(got == "D"),
        "vivo_a_D": np.mean(got[live] == "D"), "D_a_vivo": np.mean(got[~live] != "D"),
        "equipo_ok": np.mean(got[both] == ref[both]),
    }


def main():
    warnings.simplefilter("ignore", RuntimeWarning)
    blocks = half_video_blocks("BAR-ATH")
    trk = load_tracking()
    rs = restarts(load_tags())
    base = possession.predict(trk, blocks, SECOND_HALF_KICKOFF, rs)
    graded = np.zeros(len(base), dtype=bool)
    for _, f, l in blocks:
        graded[f:l + 1] = True
    graded[blocks[1][1]:SECOND_HALF_KICKOFF] = False  # antes del saque de la 2ª parte: D forzado

    print("== Balón escondido en tramos visibles (referencia: predicción con balón) ==")
    for seconds in WINDOW_LENGTHS_S:
        r = simulate(trk, blocks, rs, base, graded, seconds * FPS)
        print("  {:2d} s: {} ventanas ({:.1f} min) | D ref {:.2f} → pred {:.2f} | juego→D {:.2f} "
              "parón→vivo {:.2f} | equipo (ambos vivos) {:.2f}".format(
                  seconds, r["ventanas"], r["min"], r["ref_D"], r["pred_D"], r["vivo_a_D"],
                  r["D_a_vivo"], r["equipo_ok"]))


if __name__ == "__main__":
    main()
