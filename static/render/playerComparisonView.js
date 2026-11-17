// Side-by-side comparison of two players, driven by the
// /api/player/<a>/vs/<b> bundle. Mirrors comparisonView.js's team comparison
// pattern. PIE stands in for PER, as elsewhere in this app.
const PlayerComparisonView = (() => {
    function render(container, { playerA, playerB }) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'comparison';
        root.style.setProperty('--team-a-color', TeamColors.readableOnDark(playerA.branding.primary));
        root.style.setProperty('--team-b-color', TeamColors.readableOnDark(playerB.branding.primary));

        root.appendChild(buildHeaders(playerA, playerB));
        root.appendChild(buildHeadToHead(playerA, playerB));

        container.appendChild(root);
    }

    function buildHeaders(playerA, playerB) {
        const wrap = document.createElement('div');
        wrap.className = 'comparison-headers';
        [playerA, playerB].forEach((view) => {
            const latest = view.current;
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

    // "LeBron James" -> "James"; "Jaren Jackson Jr." -> "Jackson" (a bare
    // last-word split would give "Jr."). Team abbreviation was ambiguous when
    // comparing two players on the same team, and didn't say who was who at
    // a glance -- the player's own name does.
    const _NAME_SUFFIXES = new Set(['jr', 'jr.', 'sr', 'sr.', 'ii', 'iii', 'iv', 'v']);

    function lastName(fullName) {
        const parts = fullName.trim().split(/\s+/);
        if (parts.length > 1 && _NAME_SUFFIXES.has(parts[parts.length - 1].toLowerCase())) {
            return parts[parts.length - 2];
        }
        return parts[parts.length - 1];
    }

    const pct = (v) => `${(v * 100).toFixed(1)}%`;
    const pctPts = (d) => `${(d * 100).toFixed(1)} pts`;
    const one = (v) => v.toFixed(1);

    // Replaces the old KPI table + PIE / ratings bar charts with one animated
    // head-to-head block (see headToHead.js). A missing per-game stat shows
    // "—" with no bar and isn't counted in the "leads N of M" summary.
    function buildHeadToHead(playerA, playerB) {
        const section = document.createElement('div');
        section.className = 'chart-card h2h-card';
        const sA = playerA.seasonStats || {}, sB = playerB.seasonStats || {};
        const cA = playerA.current || {}, cB = playerB.current || {};
        const rows = [
            { label: 'PPG', aVal: sA.ppg, bVal: sB.ppg, domain: 'player_ppg', format: one },
            { label: 'APG', aVal: sA.apg, bVal: sB.apg, domain: 'player_apg', format: one },
            { label: 'RPG', aVal: sA.rpg, bVal: sB.rpg, domain: 'player_rpg', format: one },
            { label: 'SPG', aVal: sA.spg, bVal: sB.spg, domain: 'player_spg', format: one },
            { label: 'TS%', aVal: cA.ts_pct, bVal: cB.ts_pct, domain: 'player_ts_pct', format: pct, formatDelta: pctPts },
            { label: 'USG%', aVal: cA.usg_pct, bVal: cB.usg_pct, domain: 'player_usg_pct', format: pct, formatDelta: pctPts },
            { label: 'PIE', aVal: cA.pie, bVal: cB.pie, domain: 'player_pie', format: (v) => v.toFixed(3), formatDelta: (d) => d.toFixed(3) },
            { label: 'Off. Rating', aVal: cA.off_rating, bVal: cB.off_rating, domain: 'player_rating', format: one },
            { label: 'Def. Rating', aVal: cA.def_rating, bVal: cB.def_rating, domain: 'player_rating', higherIsBetter: false, format: one },
        ].filter((row) => row.aVal != null || row.bVal != null);

        section.appendChild(HeadToHead.build({
            a: { label: lastName(playerA.name), color: TeamColors.readableFillForBranding(playerA.branding) },
            b: { label: lastName(playerB.name), color: TeamColors.readableFillForBranding(playerB.branding) },
            rows,
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
