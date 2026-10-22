# Versiones del modelo de posesión

Registro de cada versión: qué cambia, por qué y qué resultado da. El código vive en
`src/possession.py`; cada versión se genera con `python run.py --name <nombre>`.

**Cómo leer los resultados.** Las métricas son sobre la **ventana pública** (5 minutos, 17
posesiones reales). Una posesión de más o de menos mueve el spellF1 unos 6 puntos, así que
diferencias < ~0.05 son ruido. El diagnóstico "partido" son *nuestras* predicciones en el
partido completo (no hay ground truth): sirve para detectar fragmentación o exceso de D.

Referencia oficial (partido completo, privado): `baseline_smooth50` spellF1 **0.2433**.

## Resumen

| versión | commit | macroF1 | spellF1 | poss (real 17) | vivo/muerto F1 | partido: poss · %D |
|---|---|---|---|---|---|---|
| baseline_smooth50 | — | 0.6207 | 0.3256 | 26 | — | 669 · 36% |
| v1 | `90f4d10` | 0.7352 | 0.3317 | 24 | 0.891 | 363 · 56% |
| v2 | `d9fb43f` | 0.7707 | 0.4615 | 22 | 0.940 | 393 · 43% |
| v2.1 | `bb2b6b7` | 0.7868 | 0.4889 | 19 | 0.937 | 356 · 48% |
| v2.2 | (este) | 0.8057 | 0.4889 | 19 | 0.948 | 360 · 47% |

## Detalle

### v1 — máquina de estados
- **D**: velocidad mediana de los jugadores (suavizada 2 s) < `DEAD_SPEED_MS` (1.5 m/s), o balón
  fuera del campo. Se limpian parones < 3 s y huecos vivos < 2 s.
- **Control**: jugador más cercano a < `CONTROL_DIST_M` (1.5 m) del balón.
- **Posesión**: cambia solo tras `SWITCH_FRAMES` (10 = 0.4 s) de control rival; el cambio se
  fecha al inicio de la racha. Sin control → se mantiene. Tras un D, la posesión es de quien
  controla primero.
- **Fallo**: el Barça circula despacio → jugadores lentos → D falsas que parten posesiones
  largas (~735 frames H marcados D).

### v2 — balón inactivo
- D exige además que el balón no supere `BALL_ACTIVE_MS` (6 m/s) en una ventana de 2 s (o no se
  vea). Motivo: en frames lentos, velocidad máx. del balón ~12 m/s con balón vivo (pases) vs
  ~3 m/s en D. Velocidad del balón calculada de posiciones (`ball_speed`).
- **Resultado**: 0 frames H marcados D; posesiones largas salen enteras.
- **Fallo**: en un parón el balón se mueve (lo recolocan) → D troceados con posesiones falsas.

### v2.1 — no salir del parón sin reanudación
- `merge_dead_gaps`: un hueco vivo ≤ 8 s entre dos D pasa a D si la **mediana** de la velocidad
  de los jugadores en él < `RESTART_SPEED_MS`.
- **Resultado**: parón de 20 s ya no se trocea.
- **Fallo**: demasiado agresivo; se comió una H real de 3.5 s y ~10 s de una A.

### v2.2 — reanudación = alguien alcanza ritmo de juego
- `merge_dead_gaps` usa el **máximo** en vez de la mediana: si en algún momento del hueco la
  velocidad supera el umbral, hubo reanudación y no se une. Sin parámetros nuevos.
- **Resultado**: recupera la posesión larga del Athletic (A 31.8 s vs 35.7 s real).
- **Pendiente**: una H real de 3.5 s justo antes de un parón sigue absorbida; el primer D
  (5.5 s) no se detecta; el último D (14.5 s) sale partido.
