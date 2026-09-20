// Side-by-side comparison of two teams, driven by the /api/team/<a>/vs/<b>
// bundle. Note: the AI's prose answer above this is only grounded in ONE
// team's context (a backend limitation, not fixed by this view) -- this
// dashboard is the actual side-by-side comparison.
const ComparisonView = (() => {
    let chartCounter = 0;

    function render(container, { teamA, teamB }) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'comparison';
        root.style.setProperty('--team-a-color', TeamColors.readableOnDark(teamA.branding.primary));
        root.style.setProperty('--team-b-color', TeamColors.readableOnDark(teamB.branding.primary));

        root.appendChild(buildSeasonSwitcher(container, teamA, teamB));
        root.appendChild(buildHeaders(teamA, teamB));
        root.appendChild(buildKpiTable(teamA, teamB));
        root.appendChild(buildChart(teamA, teamB));

        container.appendChild(root);
    }

    // Same control as the single-team dashboard: re-fetches both teams for the
    // chosen season and re-renders the whole card.
    function buildSeasonSwitcher(container, teamA, teamB) {
        const wrap = document.createElement('div');
        wrap.className = 'season-switcher';

        const label = document.createElement('span');
        label.className = 'season-switcher-label';
        label.textContent = 'Season';
        wrap.appendChild(label);

        const select = document.createElement('select');
        select.className = 'season-switcher-select';
        (teamA.availableSeasons || [teamA.season]).slice().reverse().forEach((season) => {
            const option = document.createElement('option');
            option.value = season;
            option.textContent = season;
            if (season === teamA.season) option.selected = true;
            select.appendChild(option);
        });

        select.addEventListener('change', () => {
            wrap.classList.add('loading');
            Api.fetchTeamComparison(teamA.team, teamB.team, select.value)
                .then((bundle) => render(container, bundle))
                .catch((e) => {
                    console.error(e);
                    wrap.classList.remove('loading');
                });
        });

        wrap.appendChild(select);
        return wrap;
    }

    function buildHeaders(teamA, teamB) {
        const wrap = document.createElement('div');
        wrap.className = 'comparison-headers';
        [teamA, teamB].forEach((bundle) => {
            const s = bundle.seasonSnapshot;
            const card = document.createElement('div');
            card.className = 'comparison-header-card';
            card.style.setProperty('--team-primary', TeamColors.readableOnDark(bundle.branding.primary));
            card.style.setProperty('--team-secondary', TeamColors.readableOnDark(bundle.branding.secondary));
            card.innerHTML = `
                <div class="comparison-header-name">${escapeHtml(bundle.knowledge.full_name)}</div>
                <div class="comparison-header-record">${s ? `${s.wins}–${s.losses} &middot; ${(s.win_pct * 100).toFixed(1)}%` : '—'}</div>
            `;
            wrap.appendChild(card);
        });
        return wrap;
    }

    const ROWS = [
        { key: 'ppg', label: 'PPG', higherIsBetter: true },
        { key: 'opp_ppg', label: 'Opp. PPG', higherIsBetter: false },
        { key: 'point_diff', label: 'Point Diff', higherIsBetter: true },
        { key: 'win_pct', label: 'Win %', higherIsBetter: true, format: (v) => `${(v * 100).toFixed(1)}%` },
        { key: 'fg_pct', label: 'FG%', higherIsBetter: true, format: (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—') },
        { key: 'fg3_pct', label: '3P%', higherIsBetter: true, format: (v) => (v != null ? `${(v * 100).toFixed(1)}%` : '—') },
    ];

    function buildKpiTable(teamA, teamB) {
        const section = document.createElement('div');
        section.className = 'comparison-table';
        const sA = teamA.seasonSnapshot, sB = teamB.seasonSnapshot;

        const colHeader = document.createElement('div');
        colHeader.className = 'comparison-col-header';
        colHeader.innerHTML = `
            <div class="comparison-col-header-cell a">${escapeHtml(teamA.branding.abbreviation)}</div>
            <div></div>
            <div class="comparison-col-header-cell b">${escapeHtml(teamB.branding.abbreviation)}</div>
        `;
        section.appendChild(colHeader);

        ROWS.forEach((row) => {
            if (!sA || !sB) return;
            const a = sA[row.key], b = sB[row.key];
            const aBetter = row.higherIsBetter ? a > b : a < b;
            const bBetter = row.higherIsBetter ? b > a : b < a;
            const format = row.format || ((v) => v);

            const rowEl = document.createElement('div');
            rowEl.className = 'comparison-row';
            rowEl.innerHTML = `
                <div class="comparison-cell ${aBetter ? 'better' : ''}">${format(a)}</div>
                <div class="comparison-cell-label">${row.label}</div>
                <div class="comparison-cell ${bBetter ? 'better' : ''}">${format(b)}</div>
            `;
            section.appendChild(rowEl);
        });
        return section;
    }

    function buildChart(teamA, teamB) {
        const section = document.createElement('div');
        section.className = 'chart-card';
        const chartId = 'comparison-chart-' + (chartCounter++);
        section.innerHTML = `<div class="chart-card-title">PPG / Opp. PPG / Point Diff</div><div class="chart-canvas-wrap tall"><canvas id="${chartId}"></canvas></div>`;

        requestAnimationFrame(() => {
            const canvas = document.getElementById(chartId);
            if (!canvas || !teamA.seasonSnapshot || !teamB.seasonSnapshot) return;
            Charts.createComparisonBarChart(canvas, {
                labels: ['PPG', 'Opp. PPG', 'Point Diff'],
                seriesA: {
                    label: teamA.branding.abbreviation,
                    color: TeamColors.readableFillForBranding(teamA.branding),
                    values: [teamA.seasonSnapshot.ppg, teamA.seasonSnapshot.opp_ppg, teamA.seasonSnapshot.point_diff],
                },
                seriesB: {
                    label: teamB.branding.abbreviation,
                    color: TeamColors.readableFillForBranding(teamB.branding),
                    values: [teamB.seasonSnapshot.ppg, teamB.seasonSnapshot.opp_ppg, teamB.seasonSnapshot.point_diff],
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
