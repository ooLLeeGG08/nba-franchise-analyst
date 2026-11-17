// Side-by-side comparison of two teams, driven by the /api/team/<a>/vs/<b>
// bundle. The AI's prose answer above this is grounded in both teams'
// context (rag.py's build_context), so this dashboard is a visual companion
// to that answer, not a workaround for a missing half of it.
const ComparisonView = (() => {
    function render(container, { teamA, teamB }) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'comparison';
        root.style.setProperty('--team-a-color', TeamColors.readableOnDark(teamA.branding.primary));
        root.style.setProperty('--team-b-color', TeamColors.readableOnDark(teamB.branding.primary));

        root.appendChild(buildSeasonSwitcher(container, teamA, teamB));
        root.appendChild(buildHeaders(teamA, teamB));
        root.appendChild(buildHeadToHead(teamA, teamB));

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

    const pct = (v) => `${(v * 100).toFixed(1)}%`;
    const pctPts = (d) => `${(d * 100).toFixed(1)} pts`;
    const signed = (v) => `${v > 0 ? '+' : ''}${v.toFixed(1)}`;

    const ROWS = [
        { key: 'ppg', label: 'PPG', domain: 'team_ppg', format: (v) => v.toFixed(1) },
        { key: 'opp_ppg', label: 'Opp. PPG', domain: 'team_opp_ppg', higherIsBetter: false, format: (v) => v.toFixed(1) },
        { key: 'point_diff', label: 'Point Diff', domain: 'team_point_diff', format: signed },
        { key: 'win_pct', label: 'Win %', domain: 'team_win_pct', format: pct, formatDelta: pctPts },
        { key: 'fg_pct', label: 'FG%', domain: 'team_fg_pct', format: pct, formatDelta: pctPts },
        { key: 'fg3_pct', label: '3P%', domain: 'team_fg3_pct', format: pct, formatDelta: pctPts },
    ];

    // Replaces the old KPI table + grouped Chart.js bars with one animated
    // head-to-head block (see headToHead.js).
    function buildHeadToHead(teamA, teamB) {
        const section = document.createElement('div');
        section.className = 'chart-card h2h-card';
        const sA = teamA.seasonSnapshot, sB = teamB.seasonSnapshot;
        if (!sA || !sB) {
            section.innerHTML = '<div class="chart-card-meta">No season stats to compare for this season.</div>';
            return section;
        }
        section.appendChild(HeadToHead.build({
            a: { label: teamA.branding.abbreviation, color: TeamColors.readableFillForBranding(teamA.branding) },
            b: { label: teamB.branding.abbreviation, color: TeamColors.readableFillForBranding(teamB.branding) },
            rows: ROWS.map((row) => ({ ...row, aVal: sA[row.key], bVal: sB[row.key] })),
        }));
        return section;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    return { render };
})();
