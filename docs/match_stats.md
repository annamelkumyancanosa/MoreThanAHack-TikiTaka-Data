# Estadísticas públicas del partido (solo para validar)

FC Barcelona 2-1 Athletic Club, LaLiga 2024-25, jornada 2 (24-ago-2024).

**Fuentes** (consultadas el 2026-10-23):
- Flashscore, página de estadísticas del partido (totales y por partes).
- ESPN, match stats: https://global.espn.com/football/matchstats/_/gameId/704672 (faltas y
  córners; coinciden con Flashscore).

**Uso.** Son estadísticas públicas agregadas, no datos de posesión (no incluimos el % de
posesión). **No entran en el pipeline** (`run.py` no las lee): solo sirven para contrastar
cuántas reanudaciones debería haber frente a los set pieces del Smart Tagging y a nuestros parones.

| | Barça 1ª | Barça 2ª | Barça total | Athletic 1ª | Athletic 2ª | Athletic total |
|---|---|---|---|---|---|---|
| Remates | 5 | 8 | 13 | 5 | 4 | 9 |
| a puerta | 2 | 3 | 5 | 2 | 0 | 2 |
| fuera | 1 | 4 | 5 | 1 | 3 | 4 |
| rechazados | 2 | 1 | 3 | 2 | 1 | 3 |
| Paradas | 1 | 0 | 1 | 1 | 2 | 3 |
| Córners | 4 | 1 | 5 | 4 | 2 | 6 |
| Fueras de juego | 0 | 2 | 2 | 2 | 3 | 5 |
| Faltas cometidas | 4 | 7 | 11 | 5 | 11 | 16 |
| Tiros libres (a favor) | 8 | 16 | 24 | 5 | 8 | 13 |
| Saques de banda | 5 | 13 | 18 | 8 | 11 | 19 |

Goles: Lamine Yamal 24', Sancet 42' (penalti), Lewandowski 75'.

## Lectura

- "Tiros libres" incluye las reanudaciones por falta y por fuera de juego del rival: Athletic 13 =
  faltas del Barça (11) + fueras de juego del Barça (2).
- Saques de puerta: no se publican. Cota inferior = remates fuera del rival (Barça ≥ 4,
  Athletic ≥ 5); también hay saques de puerta tras centros o pases.

## Balance frente al Smart Tagging (zona puntuada)

| reanudación | estadísticas | Smart Tagging | sin tag |
|---|---|---|---|
| Tiros libres | 37 (1ª 13, 2ª 24) | 5 (4, 1) | ~32 |
| Saques de banda | 37 (1ª 13, 2ª 24) | 26 (9, 17) | ~11 |
| Córners | 11 (1ª 8, 2ª 3) | 12 (6, 6) | 0 (el reparto por partes no cuadra) |
| Saques de puerta | ≥ 9 | 10 (4, 6) | ≥ 1 en la 2ª |
| Penalti | 1 | 0 | 1 |

Reanudaciones sin tag esperadas: ~14 en la 1ª parte, ~31 en la 2ª. Nuestros parones sin set piece
cerca (v3.2): 36 y 33. La 2ª parte cuadra; en la 1ª sobran ~22 (ver `VERSIONS.md`, v3.3 descartada).
