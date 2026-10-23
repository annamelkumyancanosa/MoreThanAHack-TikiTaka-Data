"""Máquina de estados de posesión a partir del tracking. Versión actual: v3.2.

Idea general (en lenguaje de fútbol):
  1. Balón muerto (D): jugadores lentos Y balón inactivo durante unos segundos, o balón fuera
     del campo. No se sale del parón sin una reanudación clara (los jugadores aceleran).
  2. Control: un jugador "tiene" el balón si está pegado a él (< CONTROL_DIST_M).
  3. La posesión solo cambia si el rival controla el balón de forma sostenida
     (SWITCH_FRAMES frames). Toques sueltos, rebotes y balones divididos no la cambian.
  4. Si nadie controla (balón suelto, por el aire o invisible), se mantiene la posesión anterior.
  5. Tras un parón con set piece en el Smart Tagging, reanuda el equipo del tag.
  6. Una posesión corta justo antes de un parón es el que recoge el balón: no cuenta.

Todo lo ajustable está en el bloque PARÁMETROS. Cada regla es una función independiente.

Historial (detalle y resultados en VERSIONS.md):
  v1   D = jugadores lentos o balón fuera; control < CONTROL_DIST_M; histéresis SWITCH_FRAMES.
  v2   D exige además balón inactivo (ball_active): el Barça circula despacio y no es parón.
  v2.1 merge_dead_gaps: une trozos de un mismo parón si los jugadores siguen lentos (mediana).
  v2.2 merge_dead_gaps usa el máximo: si alguien alcanza ritmo de juego, hubo reanudación.
  v3   restart_teams: si un set piece (Smart Tagging) cae dentro de un parón, su equipo reanuda.
  v3.1 merge_dead_gaps solo une huecos <= 3 s: los de 5-8 s eran juego en el partido completo.
  v3.2 SWITCH_FRAMES 10 -> 20 (un toque no es posesión) y absorb_pre_dead.
"""

import numpy as np

from src.atd import HOME, AWAY

NOBODY = -1
FPS = 25

# ---------------------------------------------------------------------------------------------
# PARÁMETROS
# ---------------------------------------------------------------------------------------------

# --- Balón muerto ---
# Velocidad mediana de los jugadores (m/s) por debajo de la cual consideramos que el juego está
# parado. En la ventana pública: ~1.2 m/s en D frente a 2.0-2.5 m/s con balón vivo.
DEAD_SPEED_MS = 1.5
# Ventana (frames) del promedio móvil de esa velocidad, para no reaccionar a un frame suelto.
SPEED_SMOOTH_FRAMES = 2 * FPS
# Un tramo D más corto que esto se descarta (los parones reales duran 5-20 s).
MIN_DEAD_FRAMES = 3 * FPS
# Un tramo "vivo" más corto que esto entre dos tramos D se considera parte del parón.
MIN_ALIVE_GAP_FRAMES = 2 * FPS
# Metros más allá de la línea para decir que el balón está fuera (el tracking tiene ruido).
OUT_MARGIN_M = 1.0
# v2: jugadores lentos no basta (el Barça circula despacio). Exigimos además que el balón esté
# "inactivo": que en una ventana de BALL_ACTIVE_WINDOW frames no supere BALL_ACTIVE_MS (un pase
# viaja a >8 m/s; un balón que se coloca para sacar, a pocos m/s) o que no se vea.
# Ventana pública, frames lentos: velocidad máx. del balón en 2 s ~3 m/s en D vs ~12 m/s vivo.
BALL_ACTIVE_MS = 6.0
BALL_ACTIVE_WINDOW = 2 * FPS
# v2.1: durante un parón el balón se mueve (lo recolocan, se lo pasan al que saca) y eso parte
# el D en trozos. Un hueco "vivo" entre dos tramos D de hasta MAX_DEAD_MERGE_FRAMES se considera
# parte del mismo parón si los jugadores siguen lentos en él (mediana de players_speed por debajo
# de RESTART_SPEED_MS): tras una reanudación real, el equipo se activa.
# v3.1: 8 s -> 3 s. En el partido completo, los huecos unidos < 3 s parecen parón (12.8% en fase
# ofensiva del Smart Tagging, como los D) y los de 3-8 s parecen juego (44-48%, balón visible).
# Sin unión salen 14 posesiones falsas < 3 s entre dos D; con 3 s, 1.
MAX_DEAD_MERGE_FRAMES = 3 * FPS
RESTART_SPEED_MS = DEAD_SPEED_MS

# --- Control del balón ---
# Distancia máxima (m) jugador-balón para considerar que lo controla.
# Con < 1 m el equipo del más cercano acierta el 91%; con 1-2 m el 83%.
CONTROL_DIST_M = 1.5

# --- Cambio de posesión (histéresis) ---
# Frames de control del rival necesarios para cambiar la posesión (20 = 0.8 s).
# Los frames sin control (balón suelto/invisible) no suman ni resetean el contador;
# un frame de control del equipo actual sí lo resetea.
# v3.2: 10 -> 20. Con 10, 73 posesiones < 3 s en el partido eran interrupciones (A-H-A) con ~0.7 s
# de control, 75% en fase ofensiva del rival: toques, no posesión controlada (CHALLENGE.md). Con 20
# quedan 21 y se siguen capturando 22 de 24 robos (ATTACKING TRANSITION); con 30 la ventana
# pública se hunde (17 -> 10 posesiones).
SWITCH_FRAMES = 20

# v3.2: una posesión de menos de PRE_DEAD_MAX_FRAMES justo antes de un parón vuelve al equipo
# anterior: suele ser quien recoge el balón para sacar antes de que detectemos el D (en el partido,
# 92% de esas posesiones caen en fase ofensiva del rival). La H real de 3.5 s antes del parón de la
# ventana pública queda fuera del umbral.
PRE_DEAD_MAX_FRAMES = 3 * FPS

# --- Reanudación (v3) ---
# Un set piece cuenta para un parón si su inicio cae dentro del D o hasta RESTART_TAG_SLACK
# frames antes (el tiempo del tag puede ir algo desfasado). En el partido, 24 de 27 set pieces
# con equipo empiezan dentro de un D nuestro, de media 6.5 s antes de que acabe.
RESTART_TAG_SLACK = 2 * FPS


# ---------------------------------------------------------------------------------------------
# REGLAS
# ---------------------------------------------------------------------------------------------

def _runs(mask):
    """Lista de (inicio, fin_exclusivo) de cada tramo seguido de True en `mask`."""
    edges = np.flatnonzero(np.diff(np.r_[0, mask.astype(np.int8), 0]))
    return list(zip(edges[::2], edges[1::2]))


def players_speed(trk):
    """Velocidad mediana de los jugadores visibles en cada frame, suavizada en el tiempo."""
    speed = np.nanmedian(trk["players"][..., 2], axis=1)
    # Rellenamos huecos (frames sin jugadores) con el valor anterior antes de suavizar.
    speed = _ffill(speed)
    kernel = np.ones(SPEED_SMOOTH_FRAMES) / SPEED_SMOOTH_FRAMES
    return np.convolve(speed, kernel, mode="same")


def ball_out(trk):
    """True donde el balón es visible y está fuera del rectángulo de juego."""
    length, width = trk["pitch"]
    bx, by = trk["ball"][:, 0], trk["ball"][:, 1]
    with np.errstate(invalid="ignore"):
        return ((bx < -OUT_MARGIN_M) | (bx > length + OUT_MARGIN_M)
                | (by < -OUT_MARGIN_M) | (by > width + OUT_MARGIN_M))


def ball_speed(trk):
    """Velocidad del balón (m/s) calculada de posiciones consecutivas; NaN si no se ve.

    El campo de velocidad del tracking viene vacío en ~91% de frames, por eso la calculamos.
    """
    ball = trk["ball"]
    step = np.hypot(np.diff(ball[:, 0], prepend=np.nan), np.diff(ball[:, 1], prepend=np.nan))
    return step * FPS


def ball_active(trk):
    """True si en la ventana centrada de BALL_ACTIVE_WINDOW frames el balón supera BALL_ACTIVE_MS.

    Un balón invisible cuenta como no activo (velocidad 0) en esa ventana.
    """
    fast = np.nan_to_num(ball_speed(trk), nan=0.0) > BALL_ACTIVE_MS
    # Máximo móvil sobre una máscara booleana = "hay algún frame rápido en la ventana".
    counts = np.convolve(fast.astype(np.int32), np.ones(BALL_ACTIVE_WINDOW, dtype=np.int32),
                         mode="same")
    return counts > 0


def detect_dead(trk):
    """Máscara de balón muerto, limpiada por duración.

    v1: jugadores lentos o balón fuera.
    v2: (jugadores lentos Y balón inactivo) o balón fuera.
    v2.1: además, no se sale del parón sin reanudación clara (ver merge_dead_gaps).
    """
    speed = players_speed(trk)
    slow = speed < DEAD_SPEED_MS
    dead = (slow & ~ball_active(trk)) | ball_out(trk)

    # 1) Rellenar huecos "vivos" cortos dentro de un parón (p. ej. alguien trota para sacar).
    for start, end in _runs(~dead):
        if end - start < MIN_ALIVE_GAP_FRAMES and start > 0 and end < len(dead):
            dead[start:end] = True
    # 1b) Unir trozos de un mismo parón separados por huecos donde nadie acelera.
    dead = merge_dead_gaps(dead, speed)
    # 2) Quitar parones demasiado cortos para ser reales.
    for start, end in _runs(dead):
        if end - start < MIN_DEAD_FRAMES:
            dead[start:end] = False
    return dead


def merge_dead_gaps(dead, speed):
    """Convierte en D los huecos vivos cortos entre dos D si los jugadores siguen lentos.

    `speed` es players_speed (ya suavizada). Solo huecos con D a ambos lados y de longitud
    <= MAX_DEAD_MERGE_FRAMES; el criterio es la mediana de `speed` en el hueco.
    """
    dead = dead.copy()
    for start, end in _runs(~dead):
        if start == 0 or end == len(dead) or end - start > MAX_DEAD_MERGE_FRAMES:
            continue
        # v2.2: máximo en lugar de mediana. Si en algún momento del hueco el equipo alcanza ritmo
        # de juego, hubo reanudación y no unimos (la v2.1 con mediana se comió una posesión real).
        if np.max(speed[start:end]) < RESTART_SPEED_MS:
            dead[start:end] = True
    return dead


def absorb_pre_dead(poss, dead):
    """Devuelve al equipo anterior la última posesión de un tramo vivo si dura < PRE_DEAD_MAX_FRAMES.

    Solo si el tramo vivo acaba en un parón y antes de esa posesión hubo otra del rival.
    """
    poss = poss.copy()
    for start, end in _runs(~dead):
        if end == len(dead):
            continue
        seg = poss[start:end]
        change = np.flatnonzero(seg[1:] != seg[:-1]) + 1
        if len(change) == 0:
            continue
        last = change[-1]
        if end - (start + last) < PRE_DEAD_MAX_FRAMES and seg[last - 1] != NOBODY:
            poss[start + last:end] = seg[last - 1]
    return poss


def control_team(trk):
    """Equipo que controla el balón en cada frame (HOME/AWAY), o NOBODY.

    NOBODY si el balón no se ve o si nadie está a menos de CONTROL_DIST_M.
    """
    ball, players, team = trk["ball"], trk["players"], trk["team"]
    dist = np.hypot(players[..., 0] - ball[:, None, 0], players[..., 1] - ball[:, None, 1])
    dist = np.where(np.isnan(dist), np.inf, dist)

    nearest = np.argmin(dist, axis=1)
    nearest_dist = dist[np.arange(len(dist)), nearest]
    out = np.where(nearest_dist < CONTROL_DIST_M, team[nearest], NOBODY)
    return out.astype(np.int8)


def restart_teams(dead, restarts):
    """{primer frame vivo tras un parón: equipo que reanuda} según los set pieces del tagging.

    `restarts` es [(frame, HOME/AWAY)] de src.tagging.restarts. Si varios caen en el mismo parón,
    manda el último (el más cercano a la reanudación).
    """
    out = {}
    for start, end in _runs(dead):
        for frame, team in restarts:
            if start - RESTART_TAG_SLACK <= frame < end and end < len(dead):
                out[end] = team
    return out


def assign_possession(control, dead, restart_team=None):
    """Recorre cada tramo vivo y decide la posesión con histéresis.

    `restart_team`: {primer frame vivo: equipo} (ver restart_teams); sin él, reanuda quien
    controla primero. Devuelve un array de HOME/AWAY/NOBODY (NOBODY = muerto o sin información).
    """
    poss = np.full(len(control), NOBODY, dtype=np.int8)
    restart_team = restart_team or {}

    for start, end in _runs(~dead):
        controlled = np.flatnonzero(control[start:end] != NOBODY)
        if start in restart_team:
            # v3: el set piece dice quién saca. Arrancamos con ese equipo desde el primer frame;
            # la histéresis cambia la posesión si el rival la gana después.
            current = restart_team[start]
            controlled = np.r_[0, controlled]
        elif len(controlled) == 0:
            continue
        else:
            # Tras un parón, quien primero controla el balón es quien reanuda: esa es la posesión
            # inicial del tramo (también para los frames anteriores a ese primer control).
            current = control[start + controlled[0]]
        poss[start:start + controlled[0]] = current

        challenger_count = 0
        challenger_since = None  # primer frame de la racha del rival, para fechar el cambio
        for f in range(start + controlled[0], end):
            c = control[f]
            if c == current:
                challenger_count, challenger_since = 0, None
            elif c != NOBODY:
                if challenger_since is None:
                    challenger_since = f
                challenger_count += 1
                if challenger_count >= SWITCH_FRAMES:
                    # Cambio confirmado: lo fechamos al inicio de la racha del rival.
                    current = c
                    poss[challenger_since:f] = current
                    challenger_count, challenger_since = 0, None
            poss[f] = current
    return poss


# ---------------------------------------------------------------------------------------------
# PIPELINE
# ---------------------------------------------------------------------------------------------

def predict(trk, graded_blocks, second_half_kickoff=None, restarts=None):
    """Etiquetas finales por frame ('H'/'A'/'D'/'X').

    graded_blocks: [(half, first_frame, last_frame), ...] de games.half_video_blocks.
    second_half_kickoff: frame del saque de la 2ª parte; antes de él todo es D (dato publicado).
    restarts: [(frame, HOME/AWAY)] de src.tagging.restarts (v3); None = sin Smart Tagging.
    """
    dead = detect_dead(trk)
    control = control_team(trk)
    poss = assign_possession(control, dead, restart_teams(dead, restarts or []))
    poss = absorb_pre_dead(poss, dead)  # v3.2

    labels = np.full(len(poss), "X", dtype="<U1")
    labels[poss == HOME] = "H"
    labels[poss == AWAY] = "A"
    labels[dead] = "D"

    if second_half_kickoff is not None:
        half2_start = [b for b in graded_blocks if b[0] == 2][0][1]
        labels[half2_start:second_half_kickoff] = "D"

    # Fuera de las partes no se puntúa: X.
    graded = np.zeros(len(labels), dtype=bool)
    for _, first, last in graded_blocks:
        graded[first:last + 1] = True
    labels[~graded] = "X"
    return labels


def _ffill(values):
    """Rellena NaN con el último valor válido (y al principio, con el primero válido)."""
    values = values.copy()
    mask = np.isnan(values)
    idx = np.where(~mask, np.arange(len(values)), 0)
    np.maximum.accumulate(idx, out=idx)
    values = values[idx]
    first_valid = np.flatnonzero(~np.isnan(values))
    if len(first_valid):
        values[:first_valid[0]] = values[first_valid[0]]
    return values
