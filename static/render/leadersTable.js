// Interactive cross-team leaders table, wired to GET /api/leaders. Shown as
// the default "visual answer" when a chat message resolves no specific team
// -- so every assistant reply gets a data companion, not just team questions.
const LeadersTable = (() => {
    // No hardcoded season here -- the backend tells us which one it used
    // (data.season), so this stays correct across every season refresh.
    const TABS = [
        { key: 'ppg', label: 'Scoring' },
        { key: 'apg', label: 'Assists' },
        { key: 'rpg', label: 'Rebounds' },
        { key: 'spg', label: 'Steals' },
        { key: 'pie', label: 'Efficiency (PIE)' },
    ];

    function render(container, data, { onNavigateToTeam } = {}) {
        container.innerHTML = '';
        const root = document.createElement('div');
        root.className = 'leaders-table';

        const tabBar = document.createElement('div');
        tabBar.className = 'leaders-tab-bar';
        const body = document.createElement('div');
        body.className = 'leaders-tab-body';

        let activeKey = TABS[0].key;

        function renderTabs() {
            tabBar.innerHTML = '';
            TABS.forEach((tab) => {
                const btn = document.createElement('button');
                btn.type = 'button';
                btn.className = 'leaders-tab' + (tab.key === activeKey ? ' active' : '');
                btn.textContent = tab.label;
                btn.addEventListener('click', () => {
                    activeKey = tab.key;
                    renderTabs();
                    renderBody();
                });
                tabBar.appendChild(btn);
            });
        }

        function renderBody() {
            const entries = data[activeKey] || [];
            const window = `${data.season || 'current season'}, min. 20 GP / 15 MPG`;
            body.innerHTML = `<div class="leaders-table-window">${escapeHtml(window)}</div>`;

            // The backend falls back to the last season with enough games
            // played rather than show an empty board for the first few weeks
            // of a new season -- surface that so "2025-26" doesn't read as
            // the current season by mistake.
            if (data.latestSeason && data.season && data.season !== data.latestSeason) {
                const note = document.createElement('div');
                note.className = 'leaders-table-fallback-note';
                note.textContent = `${data.latestSeason} just started — showing ${data.season}'s leaders until enough games are played.`;
                body.appendChild(note);
            }

            if (entries.length === 0) {
                const empty = document.createElement('div');
                empty.className = 'leaders-table-empty';
                empty.textContent = "Not enough games played yet for anyone to qualify.";
                body.appendChild(empty);
                return;
            }

            const list = document.createElement('div');
            list.className = 'leaders-table-list';
            entries.forEach((entry, i) => {
                const row = document.createElement('button');
                row.type = 'button';
                row.className = 'leaders-table-row';
                row.innerHTML = `
                    <span class="leaders-table-rank">${i + 1}</span>
                    <span class="leaders-table-player">${escapeHtml(entry.player)}</span>
                    <span class="leaders-table-team">${escapeHtml(entry.team)}</span>
                    <span class="leaders-table-value">${entry.value}</span>
                `;
                if (onNavigateToTeam) {
                    row.addEventListener('click', () => onNavigateToTeam(entry.team));
                } else {
                    row.disabled = true;
                }
                list.appendChild(row);
            });
            body.appendChild(list);
        }

        renderTabs();
        renderBody();

        root.appendChild(tabBar);
        root.appendChild(body);
        container.appendChild(root);
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    return { render };
})();
