# Backtest as of November 9, 2021-22 to 2025-26

- 5 seasons x 30 teams = 150 team-seasons, 5,000 simulated seasons each.
- Only what was known on Nov 9 of each season; rating model, game model and sigma_t are fitted with that season left out. Player impact = pre-season prior (no early-season player BPM for past seasons).
- Teams in the same season share a schedule and a league, so the 150 team-seasons aren't independent; treat coverage differences of about +/-3 points as noise, and calibration buckets of 20-40 teams as about +/-8-10 points.

## Choosing sigma_t (shared team-season error)

| sigma_t | Win MAE | Slope | Inside 50% | Inside 80% | RPS (lower better) | Playoff Brier |
|---|---|---|---|---|---|---|
| 0.00 | 7.33 | 0.92 | 43% | 72% | 5.2222 | 0.1801 |
| 0.50 | 7.33 | 0.92 | 43% | 72% | 5.2178 | 0.1794 |
| 1.00 | 7.33 | 0.93 | 45% | 74% | 5.2036 | 0.1784 |
| 1.50 | 7.32 | 0.93 | 46% | 75% | 5.1860 | 0.1774 |
| 2.00 | 7.32 | 0.94 | 47% | 76% | 5.1699 | 0.1762 |
| 2.33 | 7.32 | 0.95 | 49% | 77% | 5.1625 | 0.1758 |
| 2.50 (chosen) | 7.32 | 0.95 | 49% | 78% | 5.1608 | 0.1757 |
| 3.00 | 7.31 | 0.96 | 51% | 81% | 5.1653 | 0.1754 |
| 3.50 | 7.31 | 0.98 | 53% | 85% | 5.1826 | 0.1752 |

Leave-one-season-out choice: 2021-22 2.5, 2022-23 3.0, 2023-24 2.5, 2024-25 2.5, 2025-26 2.0. Held-out results: win MAE 7.32, slope 0.95, inside 50% 50%, inside 80% 78%, playoff Brier 0.1762 (base rate 0.2489).

## Results by season (chosen sigma_t)

| Season | Win MAE | Slope | Inside 50% | Inside 80% | Playoff Brier |
|---|---|---|---|---|---|
| 2021-22 | 7.24 | 0.80 | 60% | 77% | 0.1906 |
| 2022-23 | 4.95 | 0.85 | 63% | 93% | 0.1405 |
| 2023-24 | 7.70 | 1.26 | 50% | 77% | 0.1663 |
| 2024-25 | 7.39 | 1.01 | 47% | 77% | 0.1858 |
| 2025-26 | 9.30 | 0.90 | 27% | 67% | 0.1954 |

## Playoff odds calibration (made the playoffs, incl. play-in)

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 16 | 6% | 0% |
| 10%-30% | 22 | 19% | 32% |
| 30%-50% | 27 | 41% | 37% |
| 50%-70% | 26 | 61% | 58% |
| 70%-90% | 51 | 79% | 78% |
| 90%-100% | 8 | 95% | 100% |

## Playoff odds calibration, sigma_t chosen leave-one-season-out

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 16 | 6% | 0% |
| 10%-30% | 21 | 18% | 33% |
| 30%-50% | 28 | 40% | 36% |
| 50%-70% | 27 | 61% | 59% |
| 70%-90% | 49 | 79% | 78% |
| 90%-100% | 9 | 95% | 100% |

## Top-6 odds calibration

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 31 | 5% | 3% |
| 10%-30% | 29 | 21% | 34% |
| 30%-50% | 27 | 40% | 26% |
| 50%-70% | 44 | 60% | 59% |
| 70%-90% | 15 | 77% | 80% |
| 90%-100% | 4 | 95% | 100% |

## Player-level check

Share of players (500+ minutes) whose full-season BPM landed inside their 50% / 80% predictive interval; below about 45% / 75% would mean player SEs are too small:

- 2021-22: 55% / 83% (351 players)
- 2022-23: 53% / 86% (346 players)
- 2023-24: 52% / 81% (345 players)
- 2024-25: 54% / 82% (345 players)
- 2025-26: 47% / 76% (355 players)

## Model vs Vegas preseason win totals

- Model = as of Nov 9 (knows about 10 games of results); Vegas = preseason lines scaled to 1,230 per season (Basketball-Reference preseason odds pages, crediting sportsoddshistory.com). Vegas and blend playoff odds come from running their totals through the same season simulator; 'model via converter' does the same with the model's totals, to separate better totals from the conversion to odds.

| Measure (150 team-seasons) | Model (Nov 9) | Vegas (preseason, scaled) | Blend (w by fold) |
|---|---|---|---|
| Win-total average error | 7.32 | 7.10 | 7.13 |
| Win-total RMSE | 9.06 | 9.00 | 8.89 |
| Slope of actual on predicted | 0.95 | 0.85 | 0.93 |
| Correlation | 0.68 | 0.69 | 0.69 |
| Playoff Brier | 0.1757 | 0.1518 | 0.1602 |
| Playoff log loss | 0.5160 | 0.4588 | 0.4777 |

- Vegas totals before scaling: average error 7.12.
- Model totals through the same odds converter as Vegas: playoff Brier 0.1762 (so the gap is in the totals, not the conversion).
- 90% intervals from resampling whole seasons:
  - Brier, model - Vegas: +0.0142 to +0.0330
  - Average error, model - Vegas: -0.65 to +1.09
  - Brier, blend - Vegas: +0.0020 to +0.0145
  - Average error, blend - Vegas: -0.42 to +0.50
- Blend weight on the model, fitted leave-one-season-out: 2021-22 0.49, 2022-23 0.40, 2023-24 0.59, 2024-25 0.27, 2025-26 0.61 (all seasons: 0.48).

| Season | Model MAE | Vegas MAE | Blend MAE |
|---|---|---|---|
| 2021-22 | 7.24 | 6.94 | 6.72 |
| 2022-23 | 4.95 | 6.17 | 5.58 |
| 2023-24 | 7.70 | 6.57 | 7.09 |
| 2024-25 | 7.39 | 8.35 | 7.80 |
| 2025-26 | 9.30 | 7.44 | 8.44 |
