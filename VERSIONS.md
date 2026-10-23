# Versiones del modelo de posesión

Registro de cada versión: qué cambia, por qué y qué resultado da. El código vive en
`src/possession.py`; cada versión se genera con `python run.py --name <nombre>`.

**Cómo leer los resultados.** Las métricas son sobre la **ventana pública** (5 minutos, 17
posesiones reales). Una posesión de más o de menos mueve el spellF1 unos 6 puntos, así que
diferencias < ~0.05 son ruido. El diagnóstico "partido" son *nuestras* predicciones en el
partido completo (no hay ground truth): sirve para detectar fragmentación o exceso de D.

**Desde v3, el criterio principal es el partido completo contra el Smart Tagging**
(`python notebooks/validate_full_match.py`): `equipo` = % de frames de fase ofensiva y predicción
H/A cuyo equipo coincide con el de la fase (techo del GT en la ventana pública: 77.5%);
`D fase` = % de frames de fase ofensiva que predecimos D; `reanuda` = el equipo del set piece es
la primera H/A tras nuestro parón.

Referencia oficial (partido completo, privado): `baseline_smooth50` spellF1 **0.2433**.

## Resumen

| versión | commit | macroF1 | spellF1 | poss (real 17) | vivo/muerto F1 | partido: poss · %D |
|---|---|---|---|---|---|---|
| baseline_smooth50 | — | 0.6207 | 0.3256 | 26 | — | 669 · 36% |
| v1 | `90f4d10` | 0.7352 | 0.3317 | 24 | 0.891 | 363 · 56% |
| v2 | `d9fb43f` | 0.7707 | 0.4615 | 22 | 0.940 | 393 · 43% |
| v2.1 | `bb2b6b7` | 0.7868 | 0.4889 | 19 | 0.937 | 356 · 48% |
| v2.2 | `e0b56c1` | 0.8057 | 0.4889 | 19 | 0.948 | 360 · 47% |
| v3 | `0c3e5dd` | 0.8057 | 0.4889 | 19 | 0.948 | 364 · 47% |
| v3.1 | `000ebec` | 0.7751 | 0.4632 | 21 | 0.938 | 381 · 45% |

Partido completo vs Smart Tagging:

| versión | equipo | D fase | % D (X rellenas) | reanuda |
|---|---|---|---|---|
| baseline_smooth50 | 71.5 | 11.6 | 32.3 | 58.3 |
| v1 | 79.4 | 34.6 | 57.7 | 59.3 |
| v2 | 80.1 | 18.8 | 44.8 | 60.0 |
| v2.1 | 79.7 | 24.4 | 50.0 | 56.0 |
| v2.2 | 79.8 | 22.8 | 48.7 | 56.0 |
| v3 | 80.2 | 22.1 | 48.1 | 88.0* |
| v3.1 | **80.5** | 19.7 | 45.9 | 96.0* |

\* circular: v3 y v3.1 usan esos mismos tags para decidir quién saca; solo confirma que la regla se aplica.

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

### v3 — el set piece decide quién reanuda
- **Motivo** (validación con el partido completo): tras un parón, "reanuda quien controla
  primero" acertaba el equipo del set piece solo el 56%; en córners fallaba 9 de 12 (los
  defensores están más cerca del balón que el que saca). Los goal kicks sí iban bien (8 de 8).
- `src/tagging.py`: carga el Smart Tagging y da `restarts(tags)` = [(frame, equipo)] de los set
  pieces con equipo; en el Kick Off (After Goal) saca el rival del último GOALS.
- `restart_teams`: si un set piece empieza dentro de un parón nuestro (o hasta
  `RESTART_TAG_SLACK` = 2 s antes), el tramo vivo siguiente arranca con ese equipo; la histéresis
  sigue funcionando después. 24 de 27 set pieces con equipo caen dentro de un D nuestro.
- **Resultado**: ventana pública idéntica (sus 2 set pieces ya salían bien). Partido: reanuda
  56 → 88% (circular), equipo 79.8 → 80.2%, X puntuadas 1.5 → 0.9%.
- **Probado y descartado** en esta sesión: considerar "hay juego" si el p90 de la velocidad de
  los jugadores supera 2.5–3.5 m/s. Baja la D en fase ofensiva (22.8 → 17.5%) pero también el
  acierto de equipo (79.8 → 77.9%): se recuperan frames con balón invisible y equipo congelado.
- **Pendiente**: los saques de banda (26) no traen equipo; v2 sigue teniendo menos D que v2.1/v2.2
  en el partido (posible sobreajuste de la unión de parones).

### v3.1 — la unión de parones solo para huecos cortos
- **Motivo**: v2.1/v2.2 subieron la ventana pública pero en el partido completo añadían D sin
  ganar equipo. ¿Sobra la unión? Se probó `MAX_DEAD_MERGE_FRAMES` = 0 / 2.5 / 3 / 4 / 8 s:

  | hueco máx. | poss | % D | equipo | D fase | poss < 3 s entre dos D | spellF1 público |
  |---|---|---|---|---|---|---|
  | 0 s (≈ v2) | 396 | 44.3 | 80.4 | 18.4 | 14 | 0.462 |
  | **3 s** | 381 | 45.9 | 80.5 | 19.7 | 1 | 0.463 |
  | 4 s | 374 | 47.3 | 80.4 | 21.3 | 1 | 0.476 |
  | 8 s (v3) | 364 | 48.1 | 80.2 | 22.1 | 1 | 0.489 |

- Huecos que v3 unía, según el Smart Tagging (referencia: D en ambas 17.5% en fase ofensiva,
  vivo en ambas 62.7%): < 3 s (21 huecos) 12.8% en fase y 34% junto a set piece → parón;
  3–5 s (20) 44% → dudoso; 5–8 s (9) 48%, balón visible 96%, 5% junto a set piece → juego.
  En la ventana pública, los frames que unía v3 eran 66% D en el GT.
- **Cambio**: `MAX_DEAD_MERGE_FRAMES` 8 s → 3 s. Sin unión no vale: 14 posesiones falsas
  dentro de parones, que el spellF1 castiga.
- **Resultado**: partido: D en fase ofensiva 22.1 → 19.7%, equipo 80.2 → 80.5%, % D 48.1 → 45.9.
  Ventana pública: spellF1 0.489 → 0.463 (ruido, < 0.05; justo donde v2.1/v2.2 se sobreajustaron).
