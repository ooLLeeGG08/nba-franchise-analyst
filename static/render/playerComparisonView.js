// Side-by-side comparison of two players, driven by the
// /api/player/<a>/vs/<b> bundle. Mirrors comparisonView.js's team comparison
// pattern. PIE stands in for PER, as elsewhere in this app.
const PlayerComparisonView = (() => {
    let chartCounter = 0;

    function render(container, { playerA, playerB }) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'comparison';
        root.style.setProperty('--team-a-color', TeamColors.readableOnDark(playerA.branding.primary));
        root.style.setProperty('--team-b-color', TeamColors.readableOnDark(playerB.branding.primary));

        root.appendChild(buildHeaders(playerA, playerB));
        root.appendChild(buildKpiTable(playerA, playerB));
        root.appendChild(buildChart(playerA, playerB));

        container.appendChild(root);
    }

    function buildHeaders(playerA, playerB) {
        const wrap = document.createElement('div');
        wrap.className = 'comparison-headers';
        [playerA, playerB].forEach((view) => {
            const latest = view.history[view.history.length - 1];
            const card = document.createElement('div');
            card.className = 'comparison-header-card';
            card.style.setProperty('--team-primary', TeamColors.readableOnDark(view.branding.primary));
            card.style.setProperty('--team-secondary', TeamColors.readableOnDark(view.branding.secondary));
            card.innerHTML = `
                <div class="comparison-header-name">${escapeHtml(view.name)}</div>
                <div class="comparison-header-record">${escapeHtml(view.team)}${view.position ? ` &middot; ${escapeHtml(view.position)}` : ''} &middot; ${escapeHtml(latest.season)}</div>
            `;
            wrap.appendChild(card);
        });
        return wrap;
    }

    const LEADER_ROWS = [
        { key: 'ppg', label: 'PPG' },
        { key: 'apg', label: 'APG' },
        { key: 'rpg', label: 'RPG' },
        { key: 'spg', label: 'SPG' },
    ];

    function buildKpiTable(playerA, playerB) {
        const section = document.createElement('div');
        section.className = 'comparison-table';
        const latestA = playerA.history[playerA.history.length - 1];
        const latestB = playerB.history[playerB.history.length - 1];

        const colHeader = document.createElement('div');
        colHeader.className = 'comparison-col-header';
        colHeader.innerHTML = `
            <div class="comparison-col-header-cell a">${escapeHtml(playerA.branding.abbreviation)}</div>
            <div></div>
            <div class="comparison-col-header-cell b">${escapeHtml(playerB.branding.abbreviation)}</div>
        `;
        section.appendChild(colHeader);

        LEADER_ROWS.forEach(({ key, label }) => {
            const a = playerA.seasonStats[key];
            const b = playerB.seasonStats[key];
            if (a == null && b == null) return;
            appendRow(section, label, a ?? '—', b ?? '—', a != null && b != null && a > b, a != null && b != null && b > a);
        });

        appendRow(section, 'TS%', `${(latestA.ts_pct * 100).toFixed(1)}%`, `${(latestB.ts_pct * 100).toFixed(1)}%`, latestA.ts_pct > latestB.ts_pct, latestB.ts_pct > latestA.ts_pct);
        appendRow(section, 'USG%', `${(latestA.usg_pct * 100).toFixed(1)}%`, `${(latestB.usg_pct * 100).toFixed(1)}%`, latestA.usg_pct > latestB.usg_pct, latestB.usg_pct > latestA.usg_pct);
        appendRow(section, 'PIE', latestA.pie.toFixed(3), latestB.pie.toFixed(3), latestA.pie > latestB.pie, latestB.pie > latestA.pie);
        appendRow(section, 'OFF RTG', latestA.off_rating, latestB.off_rating, latestA.off_rating > latestB.off_rating, latestB.off_rating > latestA.off_rating);
        appendRow(section, 'DEF RTG', latestA.def_rating, latestB.def_rating, latestA.def_rating < latestB.def_rating, latestB.def_rating < latestA.def_rating);

        return section;
    }

    function appendRow(section, label, a, b, aBetter, bBetter) {
        const row = document.createElement('div');
        row.className = 'comparison-row';
        row.innerHTML = `
            <div class="comparison-cell ${aBetter ? 'better' : ''}">${a}</div>
            <div class="comparison-cell-label">${label}</div>
            <div class="comparison-cell ${bBetter ? 'better' : ''}">${b}</div>
        `;
        section.appendChild(row);
    }

    function buildChart(playerA, playerB) {
        const section = document.createElement('div');
        section.className = 'chart-card';
        const chartId = 'player-comparison-chart-' + (chartCounter++);
        section.innerHTML = `<div class="chart-card-title">PIE / OFF RTG / DEF RTG</div><div class="chart-canvas-wrap tall"><canvas id="${chartId}"></canvas></div>`;

        requestAnimationFrame(() => {
            const canvas = document.getElementById(chartId);
            if (!canvas) return;
            const latestA = playerA.history[playerA.history.length - 1];
            const latestB = playerB.history[playerB.history.length - 1];
            Charts.createComparisonBarChart(canvas, {
                labels: ['PIE (x100)', 'OFF RTG', 'DEF RTG'],
                seriesA: {
                    label: playerA.name,
                    color: TeamColors.readableOnDark(playerA.branding.primary),
                    values: [latestA.pie * 100, latestA.off_rating, latestA.def_rating],
                },
                seriesB: {
                    label: playerB.name,
                    color: TeamColors.readableOnDark(playerB.branding.primary),
                    values: [latestB.pie * 100, latestB.off_rating, latestB.def_rating],
                },
            });
        });
        return section;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    return { render };
})();
