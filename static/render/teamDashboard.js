// Full team analytics dashboard, driven entirely by the /api/team/<team>
// bundle -- never hardcoded per team. Team identity (colors/abbreviation)
// comes from bundle.branding; the app shell around this stays neutral/dark.
const TeamDashboard = (() => {
    let chartCounter = 0;

    function render(container, bundle) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'dashboard';
        root.style.setProperty('--team-primary-raw', bundle.branding.primary);
        root.style.setProperty('--team-primary', TeamColors.readableOnDark(bundle.branding.primary));
        root.style.setProperty('--team-secondary', TeamColors.readableOnDark(bundle.branding.secondary));

        root.appendChild(buildHero(bundle));
        root.appendChild(buildKpiGrid(bundle));
        if (bundle.seasonSnapshot) root.appendChild(buildSeasonSnapshot(bundle.seasonSnapshot));
        if (bundle.recentGames && bundle.recentGames.length) {
            root.appendChild(buildTimeline(bundle.recentGames));
            root.appendChild(buildScoringTrends(bundle.recentGames));
        }
        if (bundle.leaders) root.appendChild(buildLeaders(bundle.leaders));

        container.appendChild(root);
    }

    function buildHero(bundle) {
        const { branding, knowledge, season, seasonSnapshot } = bundle;
        const hero = document.createElement('div');
        hero.className = 'dash-hero';
        const record = seasonSnapshot ? `${seasonSnapshot.wins}–${seasonSnapshot.losses}` : '—';
        const winPct = seasonSnapshot ? `${(seasonSnapshot.win_pct * 100).toFixed(1)}% win rate` : '';
        const margin = seasonSnapshot ? `${seasonSnapshot.point_diff >= 0 ? '+' : ''}${seasonSnapshot.point_diff} avg margin` : '';

        hero.innerHTML = `
            <div class="dash-hero-eyebrow">NBA Performance Dashboard</div>
            <h2 class="dash-hero-title">${escapeHtml(knowledge.full_name.toUpperCase())}</h2>
            <div class="dash-hero-season">${escapeHtml(season)} Regular Season</div>
            <p class="dash-hero-summary">${escapeHtml(knowledge.summary)}</p>
            <div class="dash-hero-pills">
                <span class="dash-pill">${record}</span>
                ${winPct ? `<span class="dash-pill accent">${winPct}</span>` : ''}
                ${margin ? `<span class="dash-pill">${margin}</span>` : ''}
            </div>
        `;
        return hero;
    }

    function buildKpiGrid(bundle) {
        const s = bundle.seasonSnapshot;
        const wrap = document.createElement('div');
        wrap.className = 'kpi-grid';
        if (!s) return wrap;

        const tiles = [
            { label: 'Wins', value: s.wins, icon: ICONS.trophy, accent: 'secondary' },
            { label: 'Losses', value: s.losses, icon: ICONS.shield, accent: 'primary' },
            { label: 'Win %', value: `${(s.win_pct * 100).toFixed(1)}%`, icon: ICONS.trend, accent: 'secondary' },
            { label: 'PPG', value: s.ppg, sub: 'points scored', icon: ICONS.target, accent: 'secondary' },
            { label: 'Opp. PPG', value: s.opp_ppg, sub: 'points allowed', icon: ICONS.pulse, accent: 'secondary' },
            { label: 'Point Diff', value: `${s.point_diff >= 0 ? '+' : ''}${s.point_diff}`, sub: 'per game', icon: ICONS.scale, accent: 'secondary' },
        ];

        tiles.forEach((tile) => wrap.appendChild(buildKpiTile(tile)));
        return wrap;
    }

    function buildKpiTile({ label, value, sub, icon, accent }) {
        const tile = document.createElement('div');
        tile.className = `kpi-tile accent-${accent}`;
        tile.innerHTML = `
            <div class="kpi-tile-top">
                <span class="kpi-tile-label">${escapeHtml(label)}</span>
                <span class="kpi-tile-icon">${icon}</span>
            </div>
            <div class="kpi-tile-value">${value}</div>
            ${sub ? `<div class="kpi-tile-sub">${escapeHtml(sub)}</div>` : ''}
        `;
        return tile;
    }

    function buildSeasonSnapshot(snapshot) {
        const section = document.createElement('div');
        section.className = 'dash-section';
        section.innerHTML = `<h3 class="dash-section-title">Season Snapshot</h3><p class="dash-section-subtitle">Averages across all ${snapshot.games_played} regular-season games.</p>`;

        const grid = document.createElement('div');
        grid.className = 'snapshot-grid';
        const tiles = [
            { label: 'FG%', value: snapshot.fg_pct != null ? `${(snapshot.fg_pct * 100).toFixed(1)}%` : '—' },
            { label: '3P%', value: snapshot.fg3_pct != null ? `${(snapshot.fg3_pct * 100).toFixed(1)}%` : '—' },
            { label: 'FT%', value: snapshot.ft_pct != null ? `${(snapshot.ft_pct * 100).toFixed(1)}%` : '—' },
            { label: 'Rebounds', value: snapshot.reb },
            { label: 'Assists', value: snapshot.ast },
            { label: 'Turnovers', value: snapshot.tov },
        ];
        tiles.forEach(({ label, value }) => {
            const tile = document.createElement('div');
            tile.className = 'plain-tile';
            tile.innerHTML = `<div class="plain-tile-label">${label}</div><div class="plain-tile-value">${value}</div>`;
            grid.appendChild(tile);
        });
        section.appendChild(grid);
        return section;
    }

    function buildTimeline(games) {
        const section = document.createElement('div');
        section.className = 'dash-section';
        const wins = games.filter((g) => g.result === 'W').length;
        const losses = games.length - wins;
        section.innerHTML = `
            <h3 class="dash-section-title">Win / Loss Timeline</h3>
            <p class="dash-section-subtitle">Every game of the season, month by month. Green = win, red = loss.</p>
        `;

        const card = document.createElement('div');
        card.className = 'timeline-card';
        card.innerHTML = `
            <div class="timeline-card-header">
                <div class="timeline-card-title">Game-by-game results</div>
                <div class="timeline-card-subtitle">${wins} wins &middot; ${losses} losses</div>
            </div>
        `;

        const months = groupByMonth(games);
        months.forEach(({ label, games: monthGames }) => {
            const row = document.createElement('div');
            row.className = 'timeline-row';
            const rowLabel = document.createElement('div');
            rowLabel.className = 'timeline-row-label';
            rowLabel.textContent = label;
            row.appendChild(rowLabel);

            const squares = document.createElement('div');
            squares.className = 'timeline-squares';
            monthGames.forEach((g) => {
                const sq = document.createElement('span');
                sq.className = 'timeline-square ' + (g.result === 'W' ? 'win' : 'loss');
                sq.title = `${g.date} vs ${g.opponent}: ${g.result} ${g.pts_for}-${g.pts_against}`;
                squares.appendChild(sq);
            });
            row.appendChild(squares);
            card.appendChild(row);
        });

        const legend = document.createElement('div');
        legend.className = 'timeline-legend';
        legend.innerHTML = `
            <span><span class="timeline-square win"></span> Win &middot; ${wins}</span>
            <span><span class="timeline-square loss"></span> Loss &middot; ${losses}</span>
        `;
        card.appendChild(legend);

        section.appendChild(card);
        return section;
    }

    function buildScoringTrends(games) {
        const section = document.createElement('div');
        section.className = 'dash-section';
        section.innerHTML = `
            <h3 class="dash-section-title">Scoring Trends</h3>
            <p class="dash-section-subtitle">Points scored versus points allowed across the season, with a 5-game rolling average.</p>
        `;

        const card = document.createElement('div');
        card.className = 'chart-card';
        const chartId = 'scoring-trend-' + (chartCounter++);
        card.innerHTML = `<div class="chart-card-title">Points scored vs. points allowed</div><div class="chart-canvas-wrap tall"><canvas id="${chartId}"></canvas></div>`;
        section.appendChild(card);

        const diffCard = document.createElement('div');
        diffCard.className = 'chart-card';
        const diffChartId = 'point-diff-' + (chartCounter++);
        diffCard.innerHTML = `<div class="chart-card-title">Point differential by game</div><div class="chart-canvas-wrap tall"><canvas id="${diffChartId}"></canvas></div>`;
        section.appendChild(diffCard);

        requestAnimationFrame(() => {
            const labels = games.map((g) => formatShortDate(g.date));
            const scored = games.map((g) => g.pts_for);
            const allowed = games.map((g) => g.pts_against);
            const diff = games.map((g) => g.pts_for - g.pts_against);

            const scoringCanvas = document.getElementById(chartId);
            if (scoringCanvas) Charts.createScoringTrendChart(scoringCanvas, { labels, scored, allowed });

            const diffCanvas = document.getElementById(diffChartId);
            if (diffCanvas) Charts.createDiffBarChart(diffCanvas, { labels, values: diff });
        });

        return section;
    }

    function buildLeaders(leaders) {
        const section = document.createElement('div');
        section.className = 'dash-section';
        section.innerHTML = `<h3 class="dash-section-title">Team Leaders</h3>`;

        const grid = document.createElement('div');
        grid.className = 'leaders-grid-full';
        const categoryLabels = { ppg: 'Scoring', apg: 'Assists', rpg: 'Rebounds', spg: 'Steals' };
        Object.entries(categoryLabels).forEach(([key, label]) => {
            const entries = (leaders[key] || []).slice().sort((a, b) => b.value - a.value);
            if (!entries.length) return;
            const col = document.createElement('div');
            col.className = 'leaders-col';
            col.innerHTML = `<div class="leaders-col-title">${label}</div>` + entries
                .map((e, i) => `<div class="leaders-col-row"><span class="leaders-col-rank">${i + 1}</span><span class="leaders-col-name">${escapeHtml(e.player)}</span><span class="leaders-col-value">${e.value}</span></div>`)
                .join('');
            grid.appendChild(col);
        });
        section.appendChild(grid);
        return section;
    }

    function groupByMonth(games) {
        const map = new Map();
        games.forEach((g) => {
            const d = new Date(g.date);
            const key = `${d.getFullYear()}-${d.getMonth()}`;
            if (!map.has(key)) {
                map.set(key, { label: d.toLocaleString('en-US', { month: 'short', year: 'numeric' }).toUpperCase(), games: [] });
            }
            map.get(key).games.push(g);
        });
        return Array.from(map.values());
    }

    function formatShortDate(dateStr) {
        const d = new Date(dateStr);
        return `${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    const ICONS = {
        trophy: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M4 3h8v3a4 4 0 01-8 0V3z" stroke="currentColor" stroke-width="1.3"/><path d="M4 4H2v1a3 3 0 003 3M12 4h2v1a3 3 0 01-3 3M6.5 10.5V12h3v-1.5" stroke="currentColor" stroke-width="1.3"/><path d="M5 13.5h6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round"/></svg>',
        shield: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2l5 1.8v3.7c0 3-2 5.3-5 6.5-3-1.2-5-3.5-5-6.5V3.8L8 2z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>',
        trend: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 12l4-4 3 3 5-6" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/><path d="M10 5h4v4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        target: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><circle cx="8" cy="8" r="5.5" stroke="currentColor" stroke-width="1.3"/><circle cx="8" cy="8" r="2.5" stroke="currentColor" stroke-width="1.3"/></svg>',
        pulse: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M2 8h3l1.5-4L9 12l1.5-4H14" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
        scale: '<svg width="14" height="14" viewBox="0 0 16 16" fill="none"><path d="M8 2v12M4 5l-2 4h4l-2-4zM12 5l-2 4h4l-2-4zM4 14h8" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>',
    };

    return { render };
})();
