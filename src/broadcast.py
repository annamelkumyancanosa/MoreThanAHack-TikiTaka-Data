"""Broadcast (realización de TV) → ¿está la TV mostrando el juego en directo en cada frame táctico?

El broadcast trae su propio tracking (mismo formato, coordenadas de campo) pero no está alineado
con el vídeo táctico (DATA.md). Lo alineamos por la colocación de los jugadores: para un frame del
broadcast buscamos el frame táctico cuyos jugadores de cada equipo quedan más cerca. En cada parte
el desfase es constante (táctico = broadcast + desfase): las repeticiones sustituyen imagen en
directo, no la insertan.

Con la alineación, un frame táctico tiene "TV en directo" si en el frame de broadcast que le toca
los jugadores visibles coinciden con los del táctico. Si no coinciden, la TV está en una
repetición, un primer plano o la grada: en el GT público eso pasa en el 59-86% de cada parón y
solo el 16% del juego (P(D | TV en directo) = 7%, P(D | TV fuera) = 53%).

    from src.broadcast import load_tv_live
    tv_live = load_tv_live(trk, blocks)      # bool por frame táctico
    python -m src.broadcast                  # imprime desfases y calidad del ajuste (agregados)

La alineación tarda ~20 s y se cachea en data/broadcast/ (gitignored); la caché no cambia la salida.
"""

import os
import sys

import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
from games import require  # noqa: E402
from src.atd import load_tracking  # noqa: E402

FPS = 25

# ---------------------------------------------------------------------------------------------
# PARÁMETROS
# ---------------------------------------------------------------------------------------------

# Coste de un emparejamiento = distancia media (m) de cada jugador visible del broadcast al
# jugador táctico más cercano de su equipo, con cada distancia topada en MATCH_CAP_M (un jugador
# mal detectado no debe dominar).
MATCH_CAP_M = 10.0
# Menos jugadores visibles que esto en el broadcast: no hay con qué comparar (plano cerrado).
MIN_PLAYERS = 4
# Búsqueda gruesa: un frame de broadcast cada COARSE_SAMPLE, contra frames tácticos cada
# COARSE_STEP. Un emparejamiento es fiable si su coste < RELIABLE_COST_M y el mejor fuera de
# ±2 s es al menos el doble (sin ambigüedad).
COARSE_SAMPLE = 1000
COARSE_STEP = 5
RELIABLE_COST_M = 1.0
# Afinado: desfases a ±FINE_RANGE del grueso, con un frame de broadcast cada FINE_SAMPLE; gana
# el de menor coste mediano.
FINE_RANGE = 2 * COARSE_STEP
FINE_SAMPLE = 400
# TV en directo: coste del frame alineado < LIVE_MATCH_M (con la alineación buena la mediana es
# 0.7-0.8 m). Los tramos "fuera" más cortos que MIN_OFF_FRAMES se ignoran (un frame con pocos
# jugadores detectados no es un cambio de plano).
LIVE_MATCH_M = 1.5
MIN_OFF_FRAMES = 2 * FPS


# ---------------------------------------------------------------------------------------------
# ALINEACIÓN
# ---------------------------------------------------------------------------------------------

def _costs(brd_players, brd_team, tac_players, tac_team):
    """Coste por par (frame de broadcast i, frame táctico i): arrays (n, slots, 2) emparejados.

    NaN si el frame de broadcast tiene menos de MIN_PLAYERS jugadores visibles.
    """
    total = np.zeros(len(brd_players))
    count = np.zeros(len(brd_players))
    for team in (0, 1):
        q = brd_players[:, brd_team == team]
        p = tac_players[:, tac_team == team]
        d = np.hypot(q[:, :, None, 0] - p[:, None, :, 0], q[:, :, None, 1] - p[:, None, :, 1])
        d = np.where(np.isnan(d), np.inf, d).min(axis=2)
        seen = ~np.isnan(q[..., 0])
        total += np.where(seen, np.minimum(d, MATCH_CAP_M), 0).sum(axis=1)
        count += seen.sum(axis=1)
    return np.where(count >= MIN_PLAYERS, total / np.maximum(count, 1), np.nan)


def _coarse_matches(tac, brd):
    """[(frame de broadcast, mejor frame táctico)] de los emparejamientos fiables."""
    tac_sub = tac["players"][::COARSE_STEP, :, :2]
    out = []
    for b in range(0, len(brd["ball"]), COARSE_SAMPLE):
        rep = np.repeat(brd["players"][b:b + 1, :, :2], len(tac_sub), axis=0)
        cost = _costs(rep, brd["team"], tac_sub, tac["team"])
        if np.all(np.isnan(cost)):
            continue
        cost = np.where(np.isnan(cost), np.inf, cost)
        best = int(np.argmin(cost))
        far = np.abs(np.arange(len(cost)) - best) > 2 * FPS // COARSE_STEP
        if cost[best] < RELIABLE_COST_M and cost[far].min() > 2 * cost[best]:
            out.append((b, best * COARSE_STEP))
    return out


def align(tac, brd, blocks):
    """{parte: desfase} con táctico = broadcast + desfase, medido con los jugadores."""
    matches = _coarse_matches(tac, brd)
    offsets = {}
    for half, first, last in blocks:
        cand = np.array([t - b for b, t in matches if first <= t <= last])
        coarse = int(np.median(cand))
        # Afinado con frames de broadcast que caen dentro de la parte.
        b_frames = np.arange(max(first - coarse, 0), min(last - coarse, len(brd["ball"])), FINE_SAMPLE)
        best, best_cost = coarse, np.inf
        for k in range(coarse - FINE_RANGE, coarse + FINE_RANGE + 1):
            cost = np.nanmedian(_costs(brd["players"][b_frames, :, :2], brd["team"],
                                       tac["players"][b_frames + k, :, :2], tac["team"]))
            if cost < best_cost:
                best, best_cost = k, cost
        offsets[half] = best
    return offsets


def tv_live_mask(tac, brd, blocks, offsets):
    """True en los frames tácticos de las partes cuyo frame de broadcast muestra el juego."""
    n = len(tac["ball"])
    cost = np.full(n, np.nan)
    for half, first, last in blocks:
        t = np.arange(first, last + 1)
        b = t - offsets[half]
        ok = (b >= 0) & (b < len(brd["ball"]))
        t, b = t[ok], b[ok]
        for s in range(0, len(t), 5000):
            cost[t[s:s + 5000]] = _costs(brd["players"][b[s:s + 5000], :, :2], brd["team"],
                                         tac["players"][t[s:s + 5000], :, :2], tac["team"])
    live = cost < LIVE_MATCH_M
    # Tramos "fuera" muy cortos: no es un cambio de plano.
    edges = np.flatnonzero(np.diff(np.r_[0, (~live).astype(np.int8), 0]))
    for a, e in zip(edges[::2], edges[1::2]):
        if e - a < MIN_OFF_FRAMES:
            live[a:e] = True
    return live


def _params():
    return np.array([MATCH_CAP_M, MIN_PLAYERS, COARSE_SAMPLE, COARSE_STEP, RELIABLE_COST_M,
                     FINE_RANGE, FINE_SAMPLE, LIVE_MATCH_M, MIN_OFF_FRAMES], dtype=float)


def load_tv_live(tac, blocks, use_cache=True, return_offsets=False):
    """Máscara de TV en directo por frame táctico (cacheada junto al tracking del broadcast)."""
    _, raw_path = require(["atd_meta", "atd_raw"], source="broadcast")
    cache = os.path.splitext(raw_path)[0] + "_tv_live.npz"
    if use_cache and os.path.exists(cache):
        data = np.load(cache)
        if np.array_equal(data["params"], _params()) and len(data["live"]) == len(tac["ball"]):
            offsets = dict(zip(data["halves"].tolist(), data["offsets"].tolist()))
            return (data["live"], offsets) if return_offsets else data["live"]
    brd = load_tracking(source="broadcast")
    offsets = align(tac, brd, blocks)
    live = tv_live_mask(tac, brd, blocks, offsets)
    np.savez(cache, live=live, params=_params(), halves=np.array(list(offsets)),
             offsets=np.array(list(offsets.values())))
    return (live, offsets) if return_offsets else live


if __name__ == "__main__":
    import warnings
    from games import half_video_blocks
    warnings.simplefilter("ignore", RuntimeWarning)
    blocks = half_video_blocks("BAR-ATH")
    tac = load_tracking()
    live, offsets = load_tv_live(tac, blocks, use_cache=False, return_offsets=True)
    brd = load_tracking(source="broadcast")
    for half, first, last in blocks:
        b = np.arange(first, last + 1, FINE_SAMPLE) - offsets[half]
        b = b[(b >= 0) & (b < len(brd["ball"]))]
        cost = _costs(brd["players"][b, :, :2], brd["team"], tac["players"][b + offsets[half], :, :2],
                      tac["team"])
        print("parte {}: desfase {} | coste mediano {:.2f} m | TV en directo {:.0%}".format(
            half, offsets[half], np.nanmedian(cost), live[first:last + 1].mean()))
