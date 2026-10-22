"""Step 2: how do tracking signals behave against the public 5-minute ground truth?

Prints aggregates only (rates, medians), never raw tracking rows -- the match data must not leave
this machine.

    python notebooks/explore_public_gt.py
"""

import os
import sys

import numpy as np
import pandas as pd

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from src.atd import load_tracking, HOME, AWAY  # noqa: E402

GT_PATH = os.path.join(ROOT, "evaluation", "gt", "BAR-ATH_possession_gt_public.csv")
FPS = 25


def frame_features(trk):
    ball, players, team = trk["ball"], trk["players"], trk["team"]
    length, width = trk["pitch"]
    bx, by, bs = ball[:, 0], ball[:, 1], ball[:, 2]
    px, py, ps = players[..., 0], players[..., 1], players[..., 2]

    dist = np.hypot(px - bx[:, None], py - by[:, None])
    d_home = np.nanmin(np.where(team == HOME, dist, np.nan), axis=1)
    d_away = np.nanmin(np.where(team == AWAY, dist, np.nan), axis=1)

    margin = 0.5  # metres beyond the line before calling the ball "out"
    return pd.DataFrame({
        "ball_visible": ~np.isnan(bx),
        "ball_speed": bs,
        "ball_out": (bx < -margin) | (bx > length + margin) | (by < -margin) | (by > width + margin),
        "ball_x": bx,
        "nearest_team": np.where(np.isnan(d_home) & np.isnan(d_away), np.nan,
                                 np.where(np.nan_to_num(d_home, nan=1e9) <= np.nan_to_num(d_away, nan=1e9), HOME, AWAY)),
        "nearest_dist": np.fmin(d_home, d_away),
        "n_players": (~np.isnan(px)).sum(axis=1),
        "players_speed": np.nanmean(ps, axis=1),
    })


def main():
    import warnings
    warnings.filterwarnings("ignore", category=RuntimeWarning)

    gt = pd.read_csv(GT_PATH)
    feats = frame_features(load_tracking())
    df = pd.concat([gt, feats], axis=1)
    df = df[df.label != "X"].copy()

    print("== Per ground-truth label (public window, {} frames) ==".format(len(df)))
    vis = df[df.ball_visible]
    table = pd.DataFrame({
        "frames": df.groupby("label").size(),
        "ball_visible_%": 100 * df.groupby("label").ball_visible.mean(),
        "ball_out_%(vis)": 100 * vis.groupby("label").ball_out.mean(),
        "ball_speed_med": vis.groupby("label").ball_speed.median(),
        "nearest_dist_med_m": vis.groupby("label").nearest_dist.median(),
        "players_speed_med": df.groupby("label").players_speed.median(),
        "n_players_med": df.groupby("label").n_players.median(),
    }).round(2)
    print(table.to_string())

    alive = vis[vis.label != "D"]
    agree = (alive.nearest_team == np.where(alive.label == "H", HOME, AWAY))
    print("\nNearest player's team == GT team, alive & ball visible: {:.1%}".format(agree.mean()))
    for lo, hi in ((0, 1), (1, 2), (2, 4), (4, 8), (8, 100)):
        m = (alive.nearest_dist >= lo) & (alive.nearest_dist < hi)
        print("  nearest player {:>2}-{:<3} m: {:>5.1%} of frames, agreement {:.1%}".format(
            lo, hi, m.mean(), agree[m].mean()))

    # Segments and what happens at their boundaries.
    run = (df.label != df.label.shift()).cumsum()
    seg = df.groupby(run).agg(label=("label", "first"), start=("frame", "first"),
                              end=("frame", "last"))
    print("\n== Around each transition (+/- 1 s), aggregated by transition type ==")
    rows = []
    for (_, a), (_, b) in zip(seg.iloc[:-1].iterrows(), seg.iloc[1:].iterrows()):
        t = b.start
        before = df[(df.frame >= t - FPS) & (df.frame < t)]
        after = df[(df.frame >= t) & (df.frame < t + FPS)]
        rows.append({
            "type": "{}->{}".format(a.label, b.label),
            "vis_before_%": 100 * before.ball_visible.mean(),
            "vis_after_%": 100 * after.ball_visible.mean(),
            "out_before_%": 100 * before.ball_out.mean(),
            "pl_speed_before": before.players_speed.median(),
            "pl_speed_after": after.players_speed.median(),
        })
    print(pd.DataFrame(rows).groupby("type").agg(["count", "median"]).round(1)
          .drop(columns=[(c, "count") for c in ("vis_after_%", "out_before_%",
                                                 "pl_speed_before", "pl_speed_after")])
          .to_string())

    # How long does it take the ball to be seen again after it disappears?
    gaps = (~df.ball_visible).astype(int)
    gap_run = (gaps.diff() != 0).cumsum()
    lengths = gaps.groupby(gap_run).agg(["first", "size"])
    lengths = lengths[lengths["first"] == 1]["size"] / FPS
    print("\n== Ball-missing gaps (public window) ==")
    print("  {} gaps; median {:.1f} s, p90 {:.1f} s, max {:.1f} s".format(
        len(lengths), lengths.median(), lengths.quantile(.9), lengths.max()))


if __name__ == "__main__":
    main()
