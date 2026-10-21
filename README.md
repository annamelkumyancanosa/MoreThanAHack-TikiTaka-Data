# More than a Hack 2027 - Phase 1: Ball Possession

Team: **TIKITAKA-DATA**

Goal: for every frame of a full LaLiga match, predict which team has the ball
(`H` home, `A` away, `D` dead ball, `X` abstain). Scored on `spellF1`.

Challenge details: https://github.com/metrica-sports/more-than-a-hack-2027

## Repository structure

```
.
├── data/            Match data (tracking, tagging, homography, video).
│                    NOT versioned. Each member downloads it locally.
├── src/             Final, reusable code.
├── notebooks/       Exploration and experiments
├── submissions/     Generated possession CSVs.
├── docs/            Technical document delivered to the organizers.
├── evaluation/      Official scorer and validator (from the organizers' repo).
├── starter/         Official loaders and example notebooks (from the organizers' repo).
├── games.py         Official per-match constants (from the organizers' repo).
├── requirements.txt Pinned Python dependencies.
└── README.md        This file.
```

## Getting started

```bash
git clone git@github.com:annamelkumyancanosa/MoreThanAHack-TikiTaka-Data.git
cd MoreThanAHack-TikiTaka-Data
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
```

1. Register at https://landing.mobileworldcapital.com/more-than-a-hack-2027
   and download the data into `data/`.
2. Run the official scorer: `python evaluation/run_evaluation.py`
3. Validate a file before submitting:
   `python evaluation/validate_submission.py submissions/<team_name>.csv`

## Deadlines

- Submission: **November 17, 2026**
- Deliverables: possession CSV, public code repository, short technical document