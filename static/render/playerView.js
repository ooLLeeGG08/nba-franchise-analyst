// Compact player analytics view. Scoped to whatever a player's team-level
// data actually supports -- there is no league-wide player search index, so
// this only works for players resolvable via a team's roster/leaders/
// advanced-stats (see rag.py's resolve_player). "PIE" is the NBA's own
// impact stat, shown in place of Basketball-Reference's PER (not available
// via this data source).
const PlayerView = (() => {
    let chartCounter = 0;

    function render(container, view, { onNavigateToTeam } = {}) {
        container.innerHTML = '';
        const branding = view.branding;
        const latest = view.current;

        const root = document.createElement('div');
        root.className = 'player-view';
        root.style.setProperty('--team-primary-raw', branding.primary);
        root.style.setProperty('--team-badge-text', TeamColors.contrastText(branding.primary));
        root.style.setProperty('--team-primary', TeamColors.readableOnDark(branding.primary));
        root.style.setProperty('--team-secondary', TeamColors.readableOnDark(branding.secondary));

        root.appendChild(buildHeader(view, latest));
        root.appendChild(buildPrimaryGrid(view, latest));
        root.appendChild(buildAdvancedGrid(latest));
        if (view.history.length > 1) root.appendChild(buildTrend(view));

        if (onNavigateToTeam) {
            const link = document.createElement('button');
            link.type = 'button';
            link.className = 'player-team-link';
            link.textContent = `View ${branding.full_name} dashboard →`;
            link.addEventListener('click', () => onNavigateToTeam(view.team));
            root.appendChild(link);
        }

        container.appendChild(root);
    }

    function buildHeader(view, latest) {
        const header = document.createElement('div');
        header.className = 'player-header';
        header.innerHTML = `
            <div class="player-header-badge">${escapeHtml(view.branding.abbreviation)}</div>
            <div>
                <div class="player-header-name">${escapeHtml(view.name)}</div>
                <div class="player-header-meta">${escapeHtml(view.branding.full_name)}${view.position ? ` &middot; ${escapeHtml(view.position)}` : ''} &middot; ${escapeHtml(latest.season)}</div>
            </div>
        `;
        return header;
    }

    const LEADER_LABELS = { ppg: 'PPG', apg: 'APG', rpg: 'RPG', spg: 'SPG' };

    function buildPrimaryGrid(view, latest) {
        const grid = document.createElement('div');
        grid.className = 'player-kpi-grid';
        const tiles = Object.entries(LEADER_LABELS)
            .filter(([key]) => view.seasonStats[key] != null)
            .map(([key, label]) => ({ label, value: view.seasonStats[key] }));
        tiles.push({ label: 'PIE', value: latest.pie.toFixed(3) });

        tiles.forEach(({ label, value }) => {
            const tile = document.createElement('div');
            tile.className = 'plain-tile';
            tile.innerHTML = `<div class="plain-tile-label">${label}</div><div class="plain-tile-value">${value}</div>`;
            grid.appendChild(tile);
        });
        return grid;
    }

    function buildAdvancedGrid(latest) {
        const grid = document.createElement('div');
        grid.className = 'player-kpi-grid player-kpi-grid-advanced';
        const tiles = [
            { label: 'TS%', value: `${(latest.ts_pct * 100).toFixed(1)}%` },
            { label: 'USG%', value: `${(latest.usg_pct * 100).toFixed(1)}%` },
            { label: 'OFF RTG', value: latest.off_rating },
            { label: 'DEF RTG', value: latest.def_rating },
        ];
        tiles.forEach(({ label, value }) => {
            const tile = document.createElement('div');
            tile.className = 'plain-tile accent-tile';
            tile.innerHTML = `<div class="plain-tile-label">${label}</div><div class="plain-tile-value">${value}</div>`;
            grid.appendChild(tile);
        });
        return grid;
    }

    function buildTrend(view) {
        const section = document.createElement('div');
        section.className = 'chart-card';
        const chartId = 'player-trend-' + (chartCounter++);
        section.innerHTML = `<div class="chart-card-title">PIE by season${view.history.some((h) => h.team !== view.team) ? ' (across teams)' : ''}</div><div class="chart-canvas-wrap"><canvas id="${chartId}"></canvas></div>`;

        requestAnimationFrame(() => {
            const canvas = document.getElementById(chartId);
            if (!canvas) return;
            Charts.createLineChart(canvas, {
                labels: view.history.map((h) => h.season),
                values: view.history.map((h) => h.pie),
                color: TeamColors.readableFillForBranding(view.branding),
                yLabel: 'PIE',
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
