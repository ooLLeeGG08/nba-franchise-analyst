// Front page shown when the active thread has no messages yet: an animated
// aurora backdrop (pure CSS, see .aurora in style.css), a staggered headline,
// a strip of live data facts, and the suggestion prompts as a list.
const EmptyState = (() => {
    const SUGGESTIONS = [
        'Analyze the Lakers',
        'Compare the Celtics and Thunder',
        'Explain the Nets decline',
        'Who led the Nuggets in scoring?',
        'Why do the Spurs sustain success?',
        'Compare the Warriors and Kings',
    ];

    // Fetched once per page load and reused on every re-render (New chat,
    // switching threads), so the front page never flashes empty numbers twice.
    let statsPromise = null;

    function loadStats() {
        if (!statsPromise) {
            statsPromise = Promise.all([
                Api.fetchTeams().catch(() => null),
                Api.fetchMeta().catch(() => null),
            ]).then(([teams, meta]) => ({
                teams: Array.isArray(teams) ? teams.length : null,
                season: meta && meta.dataThroughSeason ? meta.dataThroughSeason : null,
                factsAsOf: meta && meta.factsAsOf ? new Date(meta.factsAsOf) : null,
            }));
        }
        return statsPromise;
    }

    function render(container, { onSuggestionClick }) {
        container.innerHTML = '';
        const wrap = document.createElement('section');
        wrap.className = 'empty-state';
        wrap.innerHTML = `
            <div class="aurora" aria-hidden="true">
                <span class="aurora-band one"></span>
                <span class="aurora-band two"></span>
                <span class="aurora-band three"></span>
            </div>
            <div class="empty-state-inner">
                <div class="eyebrow">NBA · Franchise Analyst</div>
                <h1 class="hero-title">
                    <span class="hero-line">Ask the numbers</span>
                    <span class="hero-line indent">behind every</span>
                    <span class="hero-line indent-sm">franchise.</span>
                </h1>
                <div class="hero-meta">
                    <p class="hero-subtitle">Teams, players, trades and the history behind them, answered from real NBA data with a dashboard next to every reply.</p>
                    <dl class="hero-stats">
                        <div class="hero-stat"><dt>Teams</dt><dd data-stat="teams">30</dd></div>
                        <div class="hero-stat"><dt>Latest season</dt><dd data-stat="season">—</dd></div>
                        <div class="hero-stat"><dt>Facts updated</dt><dd data-stat="facts">—</dd></div>
                    </dl>
                </div>
                <div class="suggestion-block">
                    <div class="eyebrow">Try asking</div>
                    <div class="suggestion-list"></div>
                </div>
            </div>
        `;

        const list = wrap.querySelector('.suggestion-list');
        SUGGESTIONS.forEach((text) => {
            const row = document.createElement('button');
            row.type = 'button';
            row.className = 'suggestion-row';
            row.innerHTML = `<span class="suggestion-text"></span><svg class="suggestion-arrow" width="16" height="16" viewBox="0 0 16 16" fill="none" aria-hidden="true"><path d="M3 8h10M9 4l4 4-4 4" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
            row.querySelector('.suggestion-text').textContent = text;
            row.addEventListener('click', () => onSuggestionClick(text));
            list.appendChild(row);
        });

        container.appendChild(wrap);

        loadStats().then(({ teams, season, factsAsOf }) => {
            if (teams) wrap.querySelector('[data-stat="teams"]').textContent = teams;
            if (season) wrap.querySelector('[data-stat="season"]').textContent = season.replace('-', '–');
            if (factsAsOf && !isNaN(factsAsOf)) {
                wrap.querySelector('[data-stat="facts"]').textContent =
                    factsAsOf.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
            }
        });
    }

    return { render };
})();
