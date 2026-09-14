const EmptyState = (() => {
    const SUGGESTIONS = [
        'Analyze the Lakers',
        'Compare the Celtics and Thunder',
        'Explain the Nets decline',
        'Who led the Nuggets in scoring?',
        'Why do the Spurs sustain success?',
        'Compare the Warriors and Kings',
    ];

    function render(container, { onSuggestionClick }) {
        container.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'empty-state';
        wrap.innerHTML = `
            <div class="empty-state-mark">NBA AI</div>
            <h1 class="empty-state-title">Your NBA analyst</h1>
            <p class="empty-state-subtitle">Ask about teams, players, games and the numbers behind the NBA.</p>
            <div class="suggestion-grid"></div>
        `;
        const grid = wrap.querySelector('.suggestion-grid');
        SUGGESTIONS.forEach((text) => {
            const card = document.createElement('button');
            card.type = 'button';
            card.className = 'suggestion-card';
            card.textContent = text;
            card.addEventListener('click', () => onSuggestionClick(text));
            grid.appendChild(card);
        });
        container.appendChild(wrap);
    }

    return { render };
})();
