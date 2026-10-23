"""Diagnóstico de los huecos vivos entre dos parones (D-H-D / D-A-D) de nuestra predicción.

Pregunta: ¿qué separa un hueco que es juego real de uno que es el balón recolocándose durante un
parón? (fallo 1 de v3.2 en CONTEXT.md §7). Referencias:
  - Partido completo: % del hueco cubierto por una fase ofensiva del Smart Tagging (aprox.).
  - Ventana pública: % del hueco que el GT marca D (exacto, pero solo unos pocos huecos).
Solo se imprimen agregados por grupo (cuantiles, conteos), nunca filas de datos.

    python notebooks/diagnose_dead_gaps.py                  # sobre TikiTaka-Data.csv
    python notebooks/diagnose_dead_gaps.py --name tikitaka_v3_2
"""

import argparse
import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import half_video_blocks  # noqa: E402
from src.atd import load_tracking  # noqa: E402
from src.possession import ball_speed, ball_out, control_team, NOBODY, FPS  # noqa: E402
from src.tagging import load_tags  # noqa: E402
from notebooks.validate_full_match import (GT_PATH, RESULTS_DIR, load_labels, phase_team,  # noqa: E402
                                           runs)

# Velocidad del balón (m/s) a partir de la cual lo contamos como pase/golpeo.
PASS_MS = 8.0


def gaps(labels, blocks):
    """[(start, end_inclusive)] de tramos no-D con un D justo antes y justo después."""
    out = []
    for _, first, last in blocks:
        r = runs(labels, first, last)
        # Agrupamos rachas consecutivas no-D (puede haber H y A dentro del mismo hueco).
        i = 0
        while i < len(r):
            if r[i][0] == "D":
                i += 1
                continue
            j = i
            while j + 1 < len(r) and r[j + 1][0] != "D":
                j += 1
            if i > 0 and j + 1 < len(r):
                out.append((r[i][1], r[j][2]))
            i = j + 1
    return out


def features(trk, control, bspeed, out, raw_speed, start, end):
    ball = trk["ball"]
    sl = slice(start, end + 1)
    vis = ~np.isnan(ball[sl, 0])
    bs = np.nan_to_num(bspeed[sl], nan=0.0)
    ctrl = control[sl]
    owners = ctrl[ctrl != NOBODY]
    switches = int(np.sum(owners[1:] != owners[:-1])) if len(owners) else 0
    # Desplazamiento del balón: última posición visible antes del hueco → primera tras el hueco.
    before = np.flatnonzero(~np.isnan(ball[max(start - 10 * FPS, 0):start, 0]))
    after = np.flatnonzero(~np.isnan(ball[end + 1:end + 1 + 10 * FPS, 0]))
    disp = np.nan
    if len(before) and len(after):
        p0 = ball[max(start - 10 * FPS, 0) + before[-1], :2]
        p1 = ball[end + 1 + after[0], :2]
        disp = float(np.hypot(*(p1 - p0)))
    return {
        "dur_s": (end - start + 1) / FPS,
        "ball_vis": vis.mean(),
        "fast_frames": int((bs > PASS_MS).sum()),
        "ball_max_ms": float(bs.max()),
        "pl_max_ms": float(np.nanmax(raw_speed[sl])),
        "pl_med_ms": float(np.nanmedian(raw_speed[sl])),
        "out": bool(out[sl].any()),
        "ctrl_frac": float((ctrl != NOBODY).mean()),
        "ctrl_switch": switches,
        "disp_m": disp,
    }


def summary(df, by):
    cols = ["dur_s", "ball_vis", "fast_frames", "ball_max_ms", "pl_max_ms", "pl_med_ms",
            "ctrl_frac", "ctrl_switch", "disp_m"]
    rows = []
    for name, g in df.groupby(by, observed=True):
        row = {by: name, "n": len(g), "out_%": 100 * g.out.mean()}
        for c in cols:
            q = g[c].quantile([0.25, 0.5, 0.75]).to_numpy()
            row[c] = "{:.1f}/{:.1f}/{:.1f}".format(*q)
        rows.append(row)
    return pd.DataFrame(rows).set_index(by).T.to_string()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--name", default="TikiTaka-Data")
    args = parser.parse_args()

    blocks = half_video_blocks("BAR-ATH")
    labels = load_labels(os.path.join(RESULTS_DIR, args.name + ".csv"))
    trk = load_tracking()
    tags = load_tags()
    ref = phase_team(tags, len(labels))
    gt = load_labels(GT_PATH)

    control = control_team(trk)
    bspeed = ball_speed(trk)
    out = ball_out(trk)
    with np.errstate(all="ignore"):
        import warnings
        warnings.simplefilter("ignore", RuntimeWarning)
        raw_speed = np.nanmedian(trk["players"][..., 2], axis=1)

    rows = []
    for start, end in gaps(labels, blocks):
        row = features(trk, control, bspeed, out, raw_speed, start, end)
        row["phase"] = float((ref[start:end + 1] != "").mean())
        g = gt[start:end + 1]
        row["public"] = bool((g != "X").all())
        row["gt_D"] = float((g == "D").mean()) if row["public"] else np.nan
        rows.append(row)
    df = pd.DataFrame(rows)
    df["grupo"] = pd.cut(df.phase, [-0.01, 0.0, 0.5, 1.0],
                         labels=["sin fase", "fase <50%", "fase >=50%"])

    print("== Huecos D-x-D en {}: {} (cuantiles 25/50/75) ==".format(args.name, len(df)))
    print("  grupo = % del hueco cubierto por fase ofensiva del Smart Tagging")
    print(summary(df, "grupo"))

    print("\n== Por duración ==")
    df["dur"] = pd.cut(df.dur_s, [0, 6, 10, 20, 1e9], labels=["<6s", "6-10s", "10-20s", ">20s"])
    print(pd.crosstab(df.dur, df.grupo, margins=True).to_string())

    pub = df[df.public]
    print("\n== Ventana pública: {} huecos; % GT D en cada uno (orden temporal): {}".format(
        len(pub), ", ".join("{:.0f}".format(100 * v) for v in pub.gt_D)))
    if len(pub):
        pub = pub.assign(grupo=np.where(pub.gt_D > 0.5, "GT parón", "GT juego"))
        print(summary(pub, "grupo"))

    # Reglas candidatas: cuántos huecos de cada grupo marcaría como parón.
    print("\n== Reglas candidatas: nº de huecos que pasarían a D, por grupo ==")
    rules = {
        "sin pase (fast=0)": df.fast_frames == 0,
        "fast<=2": df.fast_frames <= 2,
        "pl_max<2.0": df.pl_max_ms < 2.0,
        "pl_max<2.5": df.pl_max_ms < 2.5,
        "fast<=2 & pl_max<2.5": (df.fast_frames <= 2) & (df.pl_max_ms < 2.5),
        "fast<=2 & dur<10": (df.fast_frames <= 2) & (df.dur_s < 10),
        "disp<5": df.disp_m < 5,
        "disp<10 & fast<=2": (df.disp_m < 10) & (df.fast_frames <= 2),
    }
    table = pd.DataFrame({k: df[v].groupby(df.grupo, observed=False).size() for k, v in rules.items()}).T
    table["total"] = table.sum(axis=1)
    if df.public.any():
        table["pub GT parón"] = [int((v & df.public & (df.gt_D > 0.5)).sum()) for v in rules.values()]
        table["pub GT juego"] = [int((v & df.public & (df.gt_D <= 0.5)).sum()) for v in rules.values()]
    print("  (huecos por grupo: {})".format(dict(df.grupo.value_counts(sort=False))))
    print(table.to_string())


if __name__ == "__main__":
    main()
