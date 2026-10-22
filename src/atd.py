"""Load the tactical ATD into dense numpy arrays, indexed by video frame.

Parsing the 190 MB text file takes a while, so the result is cached as an .npz next to the data
(data/ is gitignored, so the cache never reaches the repository).

    from src.atd import load_tracking
    trk = load_tracking()
    trk["ball"]      # (n_frames, 3)  x [m], y [m], speed [m/s]; NaN where missing
    trk["players"]   # (n_frames, n_slots, 3)  same, per track slot
    trk["team"]      # (n_slots,)  0 home, 1 away
    trk["pitch"]     # (length, width) in metres
"""

import os
import sys
import xml.etree.ElementTree as ET

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import GAME, GAMES, require, source_frames  # noqa: E402

HOME, AWAY = 0, 1


def _team_of_each_track(meta_path):
    """0 for home slots, 1 for away. The first team in the metadata is the home side."""
    root = ET.parse(meta_path).getroot()
    home_id = [team.get("id") for team in root.iter("Team")][0]
    return np.array([HOME if p.get("teamId") == home_id else AWAY for p in root.iter("Player")],
                    dtype=np.int8)


def _parse_group(group):
    if group[0] == "N":
        return (np.nan, np.nan, np.nan)
    x, y, s = group.split(",")
    return (float(x), float(y), float(s))


def _parse(raw_path, n_frames, n_slots):
    ball = np.full((n_frames, 3), np.nan, dtype=np.float32)
    players = np.full((n_frames, n_slots, 3), np.nan, dtype=np.float32)
    with open(raw_path) as handle:
        for line in handle:
            frame_id, slots, ball_group = line.rstrip("\n").split(":")
            row = int(frame_id) - 1  # ATD counts from 1, video frames from 0
            ball[row] = _parse_group(ball_group)
            players[row] = [_parse_group(g) for g in slots.split(";")]
    return ball, players


def load_tracking(game=GAME, data_dir=None, source="tactical", use_cache=True):
    """Tracking as arrays in metres. Cached to data/<source>/<game>_<source>_atd.npz."""
    meta_path, raw_path = require(["atd_meta", "atd_raw"], game, data_dir, source)
    cache = os.path.splitext(raw_path)[0] + ".npz"
    length, width = GAMES[game]["pitch"]

    if use_cache and os.path.exists(cache):
        data = np.load(cache)
        ball, players, team = data["ball"], data["players"], data["team"]
    else:
        team = _team_of_each_track(meta_path)
        ball, players = _parse(raw_path, source_frames(source, game), len(team))
        # Normalised 0-1 coordinates to metres; speed is already m/s.
        for arr in (ball[..., 0], players[..., 0]):
            arr *= length
        for arr in (ball[..., 1], players[..., 1]):
            arr *= width
        np.savez(cache, ball=ball, players=players, team=team)

    return {"ball": ball, "players": players, "team": team, "pitch": (length, width)}
