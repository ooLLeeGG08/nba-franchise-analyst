// Interactive cross-team leaders table, wired to GET /api/leaders. Shown as
// the default "visual answer" when a chat message resolves no specific team
// -- so every assistant reply gets a data companion, not just team questions.
const LeadersTable = (() => {
    const TABS = [
        { key: 'ppg', label: 'Scoring', window: '2015-16 to 2025-26' },
        { key: 'apg', label: 'Assists', window: '2015-16 to 2025-26' },
        { key: 'rpg', label: 'Rebounds', window: '2015-16 to 2025-26' },
        { key: 'spg', label: 'Steals', window: '2015-16 to 2025-26' },
        { key: 'pie', label: 'Efficiency (PIE)', window: '2025-26' },
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
            const tab = TABS.find((t) => t.key === activeKey);
            const entries = data[activeKey] || [];
            body.innerHTML = `<div class="leaders-table-window">${escapeHtml(tab.window)}</div>`;
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
