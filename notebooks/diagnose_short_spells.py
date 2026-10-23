"""Diagnóstico de las posesiones cortas de nuestra predicción: ¿se completa algún pase?

Pregunta: ¿una posesión corta en la que el equipo no llega a pasarse el balón (un solo jugador
suyo lo controla) es un toque/rebote y no una posesión? (CONTEXT.md §7, fallo 4). Referencias:
  - Partido completo: equipo de la fase ofensiva del Smart Tagging durante la posesión (aprox.).
  - Ventana pública: si la posesión se solapa con una del GT del mismo equipo (exacto, pocas).
Solo se imprimen agregados por grupo, nunca filas de datos.

    python notebooks/diagnose_short_spells.py --name tikitaka_v3_4
"""

import argparse
import os
import sys
import warnings

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src.atd import load_tracking  # noqa: E402
from src.possession import CONTROL_DIST_M, FPS, PASS_MIN_M  # noqa: E402
from src.tagging import load_tags  # noqa: E402
from notebooks.validate_full_match import (GT_PATH, RESULTS_DIR, load_labels, phase_team,  # noqa: E402
                                           runs)

# (s4) Desde v3.5 un "pase" es real: cambio de jugador con el balón viajando >= PASS_MIN_M.
# Posesiones más largas que esto no entran en el diagnóstico.
SHORT_S = 6.0


def control_slot(trk):
    """Slot del jugador que controla el balón en cada frame, o -1 (misma regla que control_team)."""
    ball, players = trk["ball"], trk["players"]
    dist = np.hypot(players[..., 0] - ball[:, None, 0], players[..., 1] - ball[:, None, 1])
    dist = np.where(np.isnan(dist), np.inf, dist)
    nearest = np.argmin(dist, axis=1)
    near = dist[np.arange(len(dist)), nearest] < CONTROL_DIST_M
    return np.where(near, nearest, -1)


def spell_rows(labels, slot, team, ball, ref, gt, blocks):
    rows = []
    code = {"H": 0, "A": 1}
    for _, first, last in blocks:
        r = runs(labels, first, last)
        for k, (lab, start, end) in enumerate(r):
            if lab not in "HA" or (end - start + 1) / FPS > SHORT_S:
                continue
            prev = r[k - 1][0] if k > 0 else ""
            nxt = r[k + 1][0] if k + 1 < len(r) else ""
            s = slot[start:end + 1]
            idx = np.flatnonzero((s >= 0) & (team[np.maximum(s, 0)] == code[lab]))
            own = s[idx]
            # "Saltos": el control pasa de un jugador del equipo a otro (incluye melés).
            # Pase real (como en src.possession): además el balón recorre >= PASS_MIN_M.
            hand = np.flatnonzero(own[1:] != own[:-1])
            travel = np.hypot(*(ball[start + idx[hand + 1], :2] - ball[start + idx[hand], :2]).T)
            jumps = len(hand)
            passes = int(np.sum(travel >= PASS_MIN_M))
            rival = s[(s >= 0) & (team[np.maximum(s, 0)] != code[lab])]
            ph = ref[start:end + 1]
            g = gt[start:end + 1]
            rows.append({
                "dur_s": (end - start + 1) / FPS,
                "kind": "interrupción" if prev == nxt and prev in "HA" else
                        ("tras D" if prev == "D" else ("antes de D" if nxt == "D" else "cambio")),
                "jumps": jumps,
                "passes": passes,
                "longest_ctrl_s": (np.bincount(own).max() if len(own) else 0) / FPS,
                "own_players": len(np.unique(own)),
                "own_ctrl_s": len(own) / FPS,
                "rival_ctrl_s": len(rival) / FPS,
                "phase_own": float((ph == lab).mean()),
                "phase_rival": float(((ph != lab) & (ph != "")).mean()),
                "public": bool((g != "X").all()),
                "gt_same": float((g == lab).mean()),
            })
    return pd.DataFrame(rows)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="tikitaka_v3_4")
    args = parser.parse_args()
    warnings.simplefilter("ignore", RuntimeWarning)

    blocks = half_video_blocks("BAR-ATH")
    labels = load_labels(os.path.join(RESULTS_DIR, args.name + ".csv"))
    trk = load_tracking()
    ref = phase_team(load_tags(), len(labels))
    gt = load_labels(GT_PATH)
    df = spell_rows(labels, control_slot(trk), trk["team"], trk["ball"], ref, gt, blocks)
    df["pase"] = np.where(df.passes > 0, "con pase", "sin pase")

    print("== Posesiones <= {} s en {}: {} ==".format(SHORT_S, args.name, len(df)))
    print("  phase_own / phase_rival = % de la posesión en fase ofensiva propia / del rival")
    agg = df.groupby(["kind", "pase"]).agg(
        n=("dur_s", "size"), dur_med=("dur_s", "median"), own_ctrl_med=("own_ctrl_s", "median"),
        rival_ctrl_med=("rival_ctrl_s", "median"), phase_own=("phase_own", "mean"),
        phase_rival=("phase_rival", "mean"))
    print(agg.round(2).to_string())

    print("\n== Interrupciones por nº de pases reales (balón >= {} m) ==".format(PASS_MIN_M))
    inter = df[df.kind == "interrupción"]
    print(inter.groupby(inter.passes.clip(upper=3)).agg(
        n=("dur_s", "size"), phase_own=("phase_own", "mean"), phase_rival=("phase_rival", "mean"),
        dur_med=("dur_s", "median"), longest_ctrl=("longest_ctrl_s", "median")).round(2).to_string())
    noise = inter[(inter.jumps > 0) & (inter.passes == 0)]
    print("  saltos de control sin pase real: {} (fase del rival {:.0%})".format(
        len(noise), noise.phase_rival.mean() if len(noise) else float("nan")))

    pub = df[df.public]
    print("\n== Ventana pública: {} posesiones cortas ==".format(len(pub)))
    print(pub.groupby(["kind", "pase"]).agg(
        n=("dur_s", "size"), real=("gt_same", lambda v: int((v > 0.5).sum())),
        dur_med=("dur_s", "median")).to_string())


if __name__ == "__main__":
    main()
