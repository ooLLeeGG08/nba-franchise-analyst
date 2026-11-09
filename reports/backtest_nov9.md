# Backtest as of November 9, 2021-22 to 2025-26

- 5 seasons x 30 teams = 150 team-seasons, 5,000 simulated seasons each.
- Only what was known on Nov 9 of each season; rating model, game model and sigma_t are fitted with that season left out. Player impact = pre-season prior (no early-season player BPM for past seasons).
- Teams in the same season share a schedule and a league, so the 150 team-seasons aren't independent; treat coverage differences of about +/-3 points as noise, and calibration buckets of 20-40 teams as about +/-8-10 points.

## Choosing sigma_t (shared team-season error)

| sigma_t | Win MAE | Slope | Inside 50% | Inside 80% | RPS (lower better) | Playoff Brier |
|---|---|---|---|---|---|---|
| 0.00 | 7.27 | 0.92 | 46% | 71% | 5.1904 | 0.1778 |
| 0.50 | 7.27 | 0.92 | 46% | 72% | 5.1855 | 0.1772 |
| 1.00 | 7.27 | 0.93 | 47% | 73% | 5.1722 | 0.1763 |
| 1.50 | 7.27 | 0.93 | 47% | 75% | 5.1556 | 0.1752 |
| 2.00 | 7.27 | 0.94 | 49% | 76% | 5.1419 | 0.1746 |
| 2.33 | 7.27 | 0.95 | 50% | 77% | 5.1372 | 0.1745 |
| 2.50 (chosen) | 7.26 | 0.95 | 50% | 78% | 5.1359 | 0.1741 |
| 3.00 | 7.26 | 0.96 | 52% | 81% | 5.1408 | 0.1737 |
| 3.50 | 7.26 | 0.98 | 53% | 84% | 5.1589 | 0.1733 |

Leave-one-season-out choice: 2021-22 2.5, 2022-23 3.0, 2023-24 2.5, 2024-25 2.5, 2025-26 2.0. Held-out results: win MAE 7.26, slope 0.95, inside 50% 51%, inside 80% 78%, playoff Brier 0.1746 (base rate 0.2489).

## Results by season (chosen sigma_t)

| Season | Win MAE | Slope | Inside 50% | Inside 80% | Playoff Brier |
|---|---|---|---|---|---|
| 2021-22 | 7.25 | 0.79 | 60% | 77% | 0.1940 |
| 2022-23 | 5.04 | 0.84 | 63% | 90% | 0.1425 |
| 2023-24 | 7.65 | 1.26 | 50% | 77% | 0.1667 |
| 2024-25 | 7.19 | 1.02 | 47% | 77% | 0.1742 |
| 2025-26 | 9.19 | 0.90 | 30% | 70% | 0.1930 |

## Playoff odds calibration (made the playoffs, incl. play-in)

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 16 | 6% | 0% |
| 10%-30% | 22 | 19% | 32% |
| 30%-50% | 27 | 40% | 37% |
| 50%-70% | 28 | 62% | 57% |
| 70%-90% | 49 | 80% | 80% |
| 90%-100% | 8 | 95% | 100% |

## Playoff odds calibration, sigma_t chosen leave-one-season-out

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 16 | 6% | 0% |
| 10%-30% | 22 | 19% | 32% |
| 30%-50% | 28 | 41% | 39% |
| 50%-70% | 26 | 62% | 58% |
| 70%-90% | 49 | 79% | 78% |
| 90%-100% | 9 | 95% | 100% |

## Top-6 odds calibration

| Predicted | Teams | Avg predicted | Actual |
|---|---|---|---|
| 0%-10% | 29 | 4% | 3% |
| 10%-30% | 33 | 20% | 27% |
| 30%-50% | 24 | 40% | 33% |
| 50%-70% | 42 | 59% | 57% |
| 70%-90% | 18 | 76% | 78% |
| 90%-100% | 4 | 95% | 100% |

## Player-level check

Share of players (500+ minutes) whose full-season BPM landed inside their 50% / 80% predictive interval; below about 45% / 75% would mean player SEs are too small:

- 2021-22: 55% / 83% (351 players)
- 2022-23: 53% / 86% (346 players)
- 2023-24: 52% / 81% (345 players)
- 2024-25: 54% / 82% (345 players)
- 2025-26: 47% / 76% (355 players)

## Model vs Vegas preseason win totals

- Model = as of Nov 9 (knows about 10 games of results); Vegas = preseason lines (Basketball-Reference preseason odds pages, which credit sportsoddshistory.com). Vegas playoff odds are derived by running the totals through the same season simulator.

| Measure (150 team-seasons) | Model (Nov 9) | Vegas (preseason) |
|---|---|---|
| Win-total average error | 7.26 | 7.12 |
| Win-total RMSE | 9.03 | 9.02 |
| Slope of actual on predicted | 0.95 | 0.84 |
| Correlation | 0.68 | 0.69 |
| Playoff Brier | 0.1741 | 0.1518 |
| Playoff log loss | 0.5123 | 0.4585 |
| Top-6 Brier | 0.1795 | 0.1666 |
| Slope, 90% interval (resampling seasons) | 0.85 to 1.07 | 0.73 to 1.01 |

| Season | Model MAE | Vegas MAE |
|---|---|---|
| 2021-22 | 7.25 | 6.93 |
| 2022-23 | 5.04 | 6.27 |
| 2023-24 | 7.65 | 6.57 |
| 2024-25 | 7.19 | 8.37 |
| 2025-26 | 9.19 | 7.47 |
