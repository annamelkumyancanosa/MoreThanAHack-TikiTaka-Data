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
| v3.2 | `7a289de` | 0.7916 | 0.4706 | **17** | 0.938 | 260 · 45% |
| v3.4 | `f5cd2e1` | 0.8223 | 0.5000 | 15 | 0.948 | 246 · 46% |
| v3.5 | `6f1d6b6` | **0.8336** | **0.5429** | 11 | 0.948 | 200 · 46% |
| v3.6 | `ff08737` | 0.8336 | 0.5429 | 11 | 0.948 | 200 · 47% |
| v3.8 | `14b9be2` | 0.8593 | 0.5630 | 10 | 0.959 | 196 · 47% |
| v3.9 | `804a79f` | 0.8717 | 0.5926 | 10 | 0.964 | 197 · 47% |
| v3.9.1 | `ff4ef58` | **0.8724** | **0.5926** | 10 | 0.964 | 197 · 47% |
| v4.0 | — | 0.8724 | 0.5926 | 10 | 0.964 | 187 · 42% |

Partido completo vs Smart Tagging:

| versión | equipo | D fase | % D (X rellenas) | reanuda |
|---|---|---|---|---|
| baseline_smooth50 | 71.5 | 11.6 | 32.3 | 58.3 |
| v1 | 79.4 | 34.6 | 57.7 | 59.3 |
| v2 | 80.1 | 18.8 | 44.8 | 60.0 |
| v2.1 | 79.7 | 24.4 | 50.0 | 56.0 |
| v2.2 | 79.8 | 22.8 | 48.7 | 56.0 |
| v3 | 80.2 | 22.1 | 48.1 | 88.0* |
| v3.1 | 80.5 | 19.7 | 45.9 | 96.0* |
| v3.2 | **84.6**† | 19.7 | 45.9 | 96.0* |
| v3.4 | 84.5 | 20.2 | 46.2 | 96.0* |
| v3.5 | 86.5 | 20.2 | 46.2 | 96.0* |
| v3.6 | 86.5 | 20.2 | 47.0 | 96.0* |
| v3.8 | 87.1 | 20.8 | 47.4 | 96.0* |
| v3.9 | 87.8 | 23.0 | 47.4 | 96.2* |
| v4.0 | 85.8 | 16.2 | 42.4 | 96.2* |

\* circular: v3, v3.1 y v3.2 usan esos mismos tags para decidir quién saca; solo confirma que la regla se aplica.

† desde v3.2 `equipo` no sirve para comparar histéresis: sube siempre que cambiamos menos de
equipo (las fases son gruesas). Para eso, `robos` = % de ATTACKING TRANSITION (24 en el partido)
con un cambio hacia ese equipo a ±8 s: v3.1 24/24, v3.2 22/24, v3.4 22/24, v3.5 21/24, v3.9 19/24 (los mismos robos, 1.2 s más tarde: dos pasan de +6.8/+7.2 s a +8.0/+8.4 s) (desde la
s4 lo calcula `validate_full_match.py`, columna `steals`, y lo imprime `run.py`).

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
- **Probado y descartado** (sesión 3): en los saques de banda (sin equipo en el tag), que saque
  el rival del último en posesión. De 26 saques puntuados, 23 caen dentro de un D nuestro y al
  reanudar el balón está en la línea (mediana −0.5 m de la banda): quien lo controla primero
  es el que saca. Contra la fase ofensiva del Smart Tagging en los 10 s siguientes (13 casos con
  fase): "primero que controla tras el D" (lo actual) coincide 13/13; "rival del último en
  posesión" 5/13; "rival del último que toca" 6/13 (en el parón alguien recoge el balón y cuenta
  como toque). Nos quedamos con lo actual: a diferencia de los córners, en un saque de banda no
  hay rivales pegados al balón.

### v3.2 — un toque no es posesión
- **Motivo**: v3.1 tenía 112 posesiones < 3 s en el partido (381 en total). 73 eran
  interrupciones (A‑H‑A) con ~0.7 s de control y el rival a 2 m, el 75% en fase ofensiva del
  rival (posesiones > 15 s: 10%). La definición oficial (CHALLENGE.md) exige posesión
  *controlada*: un toque, un desvío o un duelo aéreo sin control no cambian la posesión. En la
  ventana pública, las 3 interrupciones cortas que predecíamos eran falsas.
- Otras 22 posesiones < 3 s iban justo antes de un parón, 92% en fase del rival: el que recoge
  el balón para sacar antes de que detectemos el D.
- **Cambios**: `SWITCH_FRAMES` 10 → 20 (0.8 s de control del rival); `absorb_pre_dead`: la
  última posesión de un tramo vivo, si dura < `PRE_DEAD_MAX_FRAMES` (3 s), vuelve al equipo
  anterior.
- **Barrido** (con la regla "pre"; robos = ATTACKING TRANSITION capturadas):

  | SWITCH_FRAMES | poss | interrup. < 3 s | robos | público spellF1 · poss |
  |---|---|---|---|---|
  | 10 (v3.1, sin pre) | 381 | 73 | 24/24 | 0.463 · 21 |
  | 15 | 308 | 43 | 23/24 | 0.463 · 21 |
  | **20** | 260 | 21 | 22/24 | 0.471 · 17 |
  | 25 | 242 | 12 | 21/24 | 0.513 · 15 |
  | 30 | 220 | 6 | 20/24 | 0.341 · 10 |

  Elegimos 20 y no 25: 25 pierde otro robo, su spellF1 público es ruido y está pegado al
  precipicio de la ventana pública (25 → 30: de 15 a 10 posesiones). La regla "pre" quita
  10–25 posesiones falsas sin perder robos ni cambiar la ventana pública.
- **Resultado**: partido 381 → 260 posesiones, 0 de < 1 s; ventana pública 17 posesiones (las
  reales), spellF1 0.463 → 0.471, macroF1 0.775 → 0.792.
- **Pendiente**: las posesiones < 3 s que quedan siguen cayendo ~70% en fase del rival (¿falsas,
  o las fases llegan tarde a los robos?). Idea: confirmar el cambio con un pase completado.

### v3.3 (probada y descartada) — parones cortos en mitad de una posesión
- **Idea**: 35 parones sin set piece tienen el mismo equipo antes y después (H‑D‑H). 14 de ellos
  (< 10 s, balón nunca fuera, balón visible ≥ 80%) caen en fase ofensiva de ese equipo un 61%, como
  el juego vivo (62.7%; parones reales 13–19%). Hipótesis: circulación lenta marcada D, que parte
  una posesión en dos. Regla propuesta: rellenarlos con ese equipo.
- **Contra**: una falta sacada rápido también es H‑D‑H, y son dos posesiones (`H H D D H H`), así
  que unirla por error cuesta lo mismo que partir una real.
  - Firma en el tracking (balón quieto ≥ 1 s): juego vivo lento 1%, parones reales 19–22%,
    los 14 sospechosos 21% → se parecen a parones.
  - Estadísticas públicas (`docs/match_stats.md`, Flashscore/ESPN, solo validación): 37 tiros
    libres y 37 saques de banda; el Smart Tagging trae 5 y 26. Reanudaciones sin tag esperadas:
    ~14 en la 1ª parte y ~31 en la 2ª; nuestros parones sin tag: 36 y 33. **La 2ª parte cuadra**
    (el Athletic hizo 11 faltas); en la 1ª sobran ~22, sobre todo en los minutos 10–20.
  - De los 14 sospechosos, 10 están en la 1ª parte y 4 en la 2ª: la regla arreglaría ~8 y
    rompería ~3 faltas reales. Ganancia neta ~4 posesiones de ~260, sin forma de separar los casos.
- **Decisión**: no se implementa. Pista abierta: parones cortos de la 1ª parte (min 10–20) con
  balón visible.

### v3.4 — si entre dos parones nadie acelera, es el mismo parón
- **Motivo**: fallo más caro de v3.2 en la ventana pública: los parones D20.4 y D14.5 salen
  partidos por posesiones falsas (H3.3, H5.5) mientras el balón se recoloca. `merge_dead_gaps`
  solo une huecos ≤ 3 s y actúa antes de quitar los D cortos.
- **Diagnóstico** (`python notebooks/diagnose_dead_gaps.py`): 132 huecos vivos entre dos D en el
  partido. Agrupados por cobertura de fase ofensiva del Smart Tagging, el máximo de
  `players_speed` en el hueco separa bien: sin fase 1.6 m/s de mediana (29 huecos), con fase
  ≥ 50% 3.7 m/s (84). Ventana pública: parones 1.4–2.7, juego ≥ 3.1. Los pases separan peor (al
  recolocar el balón también se golpea: 30 frames rápidos de mediana en huecos sin fase).
- **Cambio**: `merge_quiet_gaps`, al final de `detect_dead`: un hueco entre dos parones ya
  confirmados, de cualquier longitud, pasa a D si el máximo de `players_speed` no llega a
  `QUIET_GAP_SPEED_MS` (= `DEAD_SPEED_MS`, 1.5 m/s; ningún número nuevo).
- **Barrido** del umbral (0 = v3.2):

  | umbral | pública spellF1 | partido poss · tramos D | D fase | frames nuevos D en fase | reanuda |
  |---|---|---|---|---|---|
  | 0 | 0.471 | 260 · 126 | 19.7 | — | 96.0 |
  | **1.5** | **0.500** | 246 · 113 | 20.2 | **20%** (66 s) | 96.0 |
  | 1.7 | 0.500 | 240 · 108 | 20.9 | 31% (102 s) | 96.0 |
  | 1.9 | 0.500 | 236 · 105 | 22.0 | 44% (138 s) | 96.0 |
  | 2.1 | 0.500 | 230 · 102 | 23.9 | — | 88.0 |

  Los frames que pasan a D con 1.5 caen en fase ofensiva un 20%, como los parones reales
  (13–19%); entre 1.5 y 1.7 los añadidos caen un ~52%, como el juego (62%). La ventana pública
  no distingue umbrales. Robos sin cambios en todo el barrido.
- **Resultado**: ventana pública spellF1 0.471 → 0.500, macroF1 0.792 → 0.822, D recall
  0.58 → 0.71, posesiones falsas 19 → 15. El D20.4 sale entero (D17.4). Coste: la H3.5 real
  antes del D18.3 queda dentro del parón (antes salía H6.1, desplazada). Partido: 260 → 246
  posesiones, tramos D 126 → 113 (−7 en cada parte).
- **Pendiente**: el D14.5 sigue partido por H5.5 (máximo 2.7 m/s, por encima del umbral).

### v3.5 — una interrupción sin control demostrado es un toque
- **Motivo**: fallo 4 de v3.2/v3.4: interrupciones falsas (A1.8 parte la H41.6 pública). En el
  partido hay 72 interrupciones A‑H‑A dentro de un mismo tramo vivo. La definición oficial
  (CHALLENGE.md) exige posesión *controlada*: "mantener el balón unos segundos o más de dos pases".
- **Regla final**: `drop_passless_interruptions`, después de `absorb_pre_dead`. Una posesión entre
  dos del rival, de menos de `INTERRUPTION_MAX_FRAMES` (5 s), vuelve al rival si el equipo **no
  demuestra control**: ni `MIN_INTERRUPTION_PASSES` (1) pase real ni un mismo jugador con
  `MIN_INTERRUPTION_CTRL_FRAMES` (2 s) de control. `control_slot` sale de `control_team` (mismo
  criterio, por jugador).
  - **Pase real**: el control pasa de un jugador del equipo a otro y el balón recorre al menos
    `PASS_MIN_M` (5 m) entre el último frame del primero y el primero del segundo.
- **Cómo se llegó** (`python notebooks/diagnose_short_spells.py`). Referencia: fase ofensiva del
  Smart Tagging durante la interrupción. Las fases son gruesas y casi nunca marcan una posesión de
  3 s (las cortas reales del GT público caen en fase propia solo un 17%), así que se compara la
  **fase del rival** con la de las posesiones cortas reales del GT público: **28%**.
  1. *Primer intento, "2 saltos de control"* (cualquier cambio de jugador con el balón): 0 saltos →
     57% en fase del rival; 1 salto → 72%; ≥ 2 → 33%. Con 1 salto salía *peor* que con 0: el control
     salta entre dos compañeros pegados al balón en una melé, no es un pase.
  2. *Revisión del equipo: un pase que llega a un compañero ya es control.* Con pases reales
     (≥ 5 m), interrupciones < 5 s: 0 pases → 68% en fase del rival (26); **1 pase → 33% (5)**,
     como las reales; 2 → 16% (6). Los saltos sin pase real caen en fase del rival un **100%** (5):
     eran el ruido. → basta 1 pase real.
  3. *Revisión del equipo: no siempre hay pase.* Quien recupera tras un despeje o un mal pase puede
     conducir o regatear. De las 26 interrupciones con < 2 saltos, solo 2 llegan a ≥ 2 s de control
     de un mismo jugador y caen en fase propia un 50% (el resto, 8%) → se respetan. El
     desplazamiento del balón no sirve como conducción (los "acarreos" ≥ 5 m caen en fase del
     rival un 78%: balón que pasa junto a un jugador) y la presión del rival no separa.
  4. *Tope de duración*: las interrupciones largas sin pase junto a un robo (ATTACKING TRANSITION)
     son reales (6.5 s, 86% en fase propia). Sin tope, robos 22 → 18/24.
- **Barrido** (regla de saltos, sin conducción; la ventana pública da 0.543 en todas):

  | saltos · tope | partido poss | robos | frames cambiados | en fase del equipo nuevo / antiguo |
  |---|---|---|---|---|
  | 0 (= v3.4) | 246 | 22/24 | — | — |
  | 1 · 5 s | 208 | 21/24 | 42 s | 62% / 6% |
  | 2 · 3 s | 210 | 21/24 | 37 s | 65% / 7% |
  | 2 · 5 s | 200 | 21/24 | 59 s | 69% / 8% |
  | 2 · 8 s | 196 | 20/24 | 71 s | 67% / 14% |
  | 2 · sin tope | 194 | 18/24 | — | — |
  | 2 saltos · 5 s + conducción 2 s | 202 | 21/24 | 54 s | 75% / 0% |
  | **1 pase real · 5 s + conducción 2 s (final)** | **200** | **21/24** | 56 s | **76% / 0%** |

- **Resultado**: ventana pública spellF1 0.500 → 0.543, macroF1 0.822 → 0.834, equipo (ambos
  vivos) 0.899 → 0.917; desaparecen las falsas A1.8 y H2.2. Partido: 246 → 200 posesiones, equipo
  84.5 → 86.5%, robos 22 → 21/24. Ningún frame cambiado cae en fase del equipo al que se le quita.
- **Coste / pendiente**: en la ventana pública predecimos 11 posesiones de 17; las cortas reales
  (H0.8, H1.3, A2.8…) siguen sin salir (no salían antes; un toque sin control no es posesión según
  la definición oficial). El robo perdido es una interrupción sin pases que cae un 58% en fase del
  rival: ambigua.

### v3.6 — ninguna X en zona puntuada
- **Motivo**: hipótesis 6 de CONTEXT.md: frames `X` en zona puntuada que el scorer rellena con la
  etiqueta anterior. Mejor decidirlos nosotros y no depender de esa regla.
- **Diagnóstico**: en v3.5 quedan 8 tramos `X` (1142 frames, 46 s): tramos vivos en los que nadie
  llega a controlar el balón (`assign_possession` no tiene con qué empezar). Los 8 van entre dos D
  (7) o entre un D y el final de una parte (1), con el balón invisible el 100% del tiempo, jugadores
  a 1.5 m/s de mediana, 9% en fase ofensiva (parones reales 13–19%, juego 62%) y ningún set piece
  cerca → son el mismo parón con el balón perdido de vista.
- **Cambio**: en `predict`, lo que queda `X` tras asignar posesión y parones pasa a D (fuera de la
  zona puntuada sigue siendo `X`).
- **Resultado**: 0 frames `X` en zona puntuada; idéntico frame a frame a v3.5 rellenada como el
  scorer, así que la puntuación no cambia (pública 0.8336 / 0.5429). Cambia el CSV (md5), no el
  resultado.

### v3.7 (probada y descartada) — balón invisible
- **Motivo**: punto 3 de la s4. El balón no se ve ~43 de los 104 min puntuados (huecos 5–10 s:
  6 min, 56% D; 10–30 s: 17 min, 83% D; > 30 s: 19 min, 95% D). La ventana pública casi no tiene
  balón invisible y no sirve para decidir.
- **El Smart Tagging no sirve aquí**: es automático (DATA.md) y sin balón casi no marca fases (la
  cobertura de fase cae del 60% con balón a 12–35% sin él). Además, en el GT público los parones
  caen en fase ofensiva un **37%** y el juego un 55%: "D en fase" es una señal débil en general.
- **Validación nueva** (`python notebooks/simulate_hidden_ball.py`): escondemos el balón en
  ventanas de 10 y 20 s dentro de tramos visibles y comparamos con nuestra predicción con balón.
  v3.6: **juego → D 13% (10 s) / 22% (20 s)**, parón → vivo 2%, equipo (ambos vivos) 84% / 78%.
  Sesgo claro: sin balón, la circulación lenta se marca D.
- **Probado**:
  - Umbral de velocidad más bajo solo con el balón oculto (`HIDDEN_DEAD_SPEED_MS`): 1.3 → juego→D
    5% / 11% pero parón→vivo **28%**; 1.2 → 4–6% / 38%; 1.0 → 1–2% / 74%. Pública: 1.3 igual
    (0.543), 1.2 0.514, 1.0 0.459.
  - "Varios jugadores corriendo (> 2 m/s) = juego" con el balón oculto: ≥ 6 corredores → juego→D
    10% / 18%, parón→vivo 7–8%; ≥ 4 → 2–4% / 10–12% y parón→vivo 18–25%. Pública 0.543 en todas.
  - Frame a frame (vivo/muerto sin balón, referencia = predicción con balón): mediana actual F1
    0.777; mejor alternativa (nº de jugadores > 2 m/s) 0.818. Poca separación.
- **Por qué se descarta**: todas las variantes cambian "juego → D" por "parón → vivo" casi uno a
  uno (umbral 1.3: −0.08–0.11 por frame de juego, +0.26 por frame de parón; solo compensa si en los
  huecos reales hay < ~28% de parón). La simulación sale de tramos visibles, que son ~90% juego; en
  los huecos reales el balón suele faltar por un parón (fuera de plano, en manos del que saca) y
  predecimos 85% D con jugadores a 1.0–1.2 m/s. Sin una señal mejor que la velocidad de los
  jugadores, cualquier cambio es una apuesta sobre cuánto parón hay en los huecos.
- **Pendiente**: (a) una señal sin balón que sí separe (¿colocación de jugadores en un saque:
  barrera, jugadores parados en el área, uno junto a la banda?); (b) el equipo con el balón
  oculto (78–84% en la simulación): la posesión se congela y los cambios llegan tarde.

### v3.8 — colocar el balón entre dos parones
- **Motivo**: (d) de la s4: el D14.5 público sale partido (`D3.7 H5.5 D3.4 H13.7`); la H5.5 es del
  mismo equipo que saca después y los jugadores llegan a 2.7 m/s, así que `merge_quiet_gaps` (v3.4)
  no la une.
- **Diagnóstico** (partido completo): 38 tramos vivos ≤ 15 s entre dos parones. De un solo equipo,
  3–10 s y sin control demostrado (criterio de v3.5: ni un pase real ≥ 5 m ni 2 s de un mismo
  jugador): si es el equipo que reanuda después, 4 huecos con 50% en fase ofensiva (los parones del
  GT público, 37%; el juego, 55%) y conducción máxima 0.5–0.8 s; si es el otro equipo, 100% en su
  propia fase (juego real) → no se tocan. Con pases reales también caen en fase propia (97%).
- **Cambio**: `absorb_placing_gaps` tras `drop_passless_interruptions`: el hueco pasa a D. La
  comprobación de pases se saca a `_shows_control`, compartida con v3.5 (salida idéntica, md5).
- **Resultado**: pública **0.8593 / 0.5630** / 10 posesiones (D14.5 → D12.6 entero). Partido: 4
  parones unidos (113 → 109 tramos D), 196 posesiones, robos 21/24 (igual), reanuda 96% (igual).
  Ojo: evidencia fina (4 casos en el partido); se acepta porque aplica el mismo principio que v3.5.
- **(b) de la s4, equipo con balón oculto: descartado por falta de casos.** La anchura de los equipos
  (std de y) separa quién tiene el balón sin verlo (AUC 0.89; logística con 8 rasgos de colocación,
  84–85% validando entre partes), y en la simulación de v3.7 casi todo el error de equipo está en
  ventanas con un cambio dentro (44% de error frente a 2–4%). Pero en el partido real solo hay 6.5 min
  de juego con el balón oculto y **4 casos** con un cambio confirmado justo al reaparecer el balón
  (0.2 min): el resto del balón oculto lo marcamos D. Fechar el cambio dentro del hueco (punto medio o
  CUSUM sobre la anchura) mejora la simulación a 20 s (1804 → 1061 frames mal) pero empeora a 10 s.
- **(a) de la s4, parones sin balón: los parones largos son reales.** Los 22 parones ≥ 40 s (9 de
  más de 60 s, ~17 min) tienen jugadores a 0.6–1.0 m/s (p90 ~1.3) y ninguna ventana de 5 s con ritmo
  de juego; casi todos con gol, córner o saque de puerta al lado. Única duda: 1ª parte, último
  parón (78.6 s, p90 2.9 m/s, 4/15 ventanas activas). El número de parones cuadra con las
  estadísticas (1ª 55 frente a ~42 reanudaciones, 2ª 57 frente a ~58).

### v3.9 — fechar los cambios cuando se gana el control
- **Motivo**: (c) de la s4 (posesiones cortas). Mirando las cortas reales del GT público, el equipo
  que tiene la posesión casi no aparece controlando en el tracking (H1.3: 0.0 s de control propio y
  0.9 s del rival). Cruzando el control con el GT a distintos desfases, cerca de los cambios H↔A
  coincide mejor el control de **30 frames antes** (0.789 frente a 0.733 sin desfase). La
  sincronización tracking↔vídeo es exacta por partes (`games.py`), así que es la definición:
  CHALLENGE.md fecha el cambio cuando el rival **gana el control**, no en el primer contacto.
- **Medidas**: en el partido, del primer contacto del rival a la confirmación del cambio pasan 29
  frames de mediana (154 cambios; p25 19, p75 56). En la ventana pública nuestros cambios H↔A
  emparejados van 33–40 frames antes que el GT y las reanudaciones 22–46 frames antes (ball_active
  usa una ventana centrada de 2 s: el balón "se activa" 1 s antes del golpeo). Los inicios de parón no
  van adelantados.
- **Probado**: (1) retraso global de todas las etiquetas: macroF1 máx. en 25 frames (0.8654), spellF1
  0.593 en 30–40; también mejora el baseline (0.326 → 0.381). (2) Por tipo: retrasar el inicio del
  parón empeora; reanudación 25–40 frames → macroF1 0.873; H↔A 20/30 → spellF1 0.578/0.593 (una
  posesión que cruza un umbral de IoU: no se elige con esto, se elige 30 por la mediana del partido).
  (3) Fechar el cambio directamente en la confirmación (sin llevarlo atrás): pública 0.480 y robos
  19/24, porque acorta las posesiones antes de las reglas v3.2/v3.5. (4) Reanudar en el primer
  frame con el balón rápido en vez de 25 fijos: igual.
- **Cambio**: `delay_transitions` al final de `predict`: H↔A +`HANDOVER_DELAY_FRAMES` (30), D → H/A
  +`RESTART_DELAY_FRAMES` (`BALL_ACTIVE_WINDOW // 2` = 25), sin comerse más de la mitad del tramo
  que empieza.
- **Resultado**: pública **0.8717 / 0.5926** / 10 posesiones, vivo/muerto F1 0.964, equipo 91.7%.
  Partido: 197 posesiones, 110 tramos D; robos 19/24 por la ventana de ±8 s (ver nota †); D en fase
  ofensiva 20.8 → 23.0% porque el parón dura 1 s más (las fases automáticas empiezan antes).

### v3.9.1 — saques de cada parte sin retraso, y revisión de v3.9
- **Fallo**: `delay_transitions` se aplicaba antes de recortar la zona puntuada y empujaba 5 frames
  del D previo al saque inicial dentro de la 1ª parte (`D0.2 A12.3…`). Los saques de cada parte son
  exactos: ahora el retraso se aplica por bloque puntuado y antes de forzar el D previo al saque de
  la 2ª parte. Cambian 4 frames; pública 0.8724 / 0.5926, partido igual.
- **¿Retrasar también el inicio de los parones?** No. Con el balón fuera del campo, nuestro D empieza
  3 frames (mediana; p25 1, p75 14) tras el cruce de línea (26 parones del partido). En la ventana
  pública los inicios no tienen un sesgo constante (+53, −208, 0 frames): desplazarlos ±25/50 no
  mejora (macroF1 0.865–0.868 frente a 0.872).
- **`merge_dead_gaps` / `absorb_pre_dead` con las etiquetas desplazadas**: sin cambios. El retraso es
  posterior a todas las reglas, que siguen decidiendo con los cambios fechados al primer contacto
  (decisiones idénticas a v3.8); en el CSV una posesión de 3–4 s antes de un parón sale 1.2 s más
  corta. 0 posesiones < 1 s.

### v4.0 — la TV dice cuándo no hay parón
- **Motivo**: análisis de la s5 para una v4. El broadcast trae su propio tracking, sin alinear
  (DATA.md). Alineado por la colocación de los jugadores, cada parte tiene un desfase constante
  (táctico = broadcast + 4013 / 26919; jugadores a 0.7–0.8 m). El balón del broadcast casi no
  ayuda (3.7 de los 42.7 min sin balón del táctico), pero **el estado de la TV sí**: si los
  jugadores del broadcast no coinciden con los del táctico, la TV está en una repetición o un
  primer plano, cosa que la realización hace en los parones.
- **Contraste con el GT público**: P(D | TV en directo) **7%**, P(D | TV fuera) 53%; los 4 parones
  tienen la TV en directo un 14–41% del tiempo. En el partido (v3.9.1) predecíamos D en el **24%**
  de los frames con la TV en directo. Hay 30 parones sin balón fuera, sin set piece y con la TV en
  directo ≥ 50% (5.4 min, mediana 7 s): caen en fase ofensiva un **69%** (parones del GT 37%, juego
  55%) y 19 son de la 1ª parte, donde el balance con las estadísticas ya decía que sobran ~22
  parones (v3.3). Tres fuentes independientes apuntan a lo mismo: juego lento marcado como parón.
- **Cambio**: `src/broadcast.py` (alineación medida en código y cacheada; máscara `tv_live`);
  `drop_tv_live_stoppages` tras `detect_dead`: quita esos parones (`TV_LIVE_MAX_SHARE` 0.5, balón
  fuera desde 2 s antes, set piece de 5 s antes a 2 s después). Al final de cada parón quitado
  reanuda quien controla primero (`resets` en `assign_possession`): sin eso la posesión seguía
  congelada, 1421 frames vivos cambiaban de equipo y se perdía un robo. `run.py --no-tv` reproduce
  v3.9.1 (mismo md5).
- **Validación nueva** (`validate_full_match.py`, la imprime `run.py`): `D_tv` = % de frames con la
  TV en directo que predecimos D (GT público 7%), `live_tvoff` = % de frames con la TV fuera que
  predecimos vivos (GT 47%), `susp_D` = parones como los de arriba (circular desde v4.0).
  `notebooks/explore_broadcast.py` imprime la alineación, la cobertura y el reparto por parones.
- **Resultado**: pública igual (0.8724 / 0.5926; ahí no hay parones así). Partido: 109 → 79 tramos
  D, 187 posesiones, D en fase ofensiva 23.0 → 16.2%, D con TV en directo 24.4 → 16.6%, robos 19/24
  (igual), reanuda 96.2%. Los frames recuperados (5.8 min) tienen fase ofensiva el 52% del tiempo
  (como el juego) y el equipo coincide con ella un 70% (flojo entre dos posesiones del Athletic,
  31%); en los frames que ya eran vivos cambia el equipo en 795 (coincidencia 87.8 → 87.2%).
- **Pendiente**: el otro lado de la señal, tramos vivos con la TV fuera > 10 s (vivo con TV fuera
  20.6% frente al 47% del GT: aquí no parece que sobre juego); el equipo en los tramos recuperados.
