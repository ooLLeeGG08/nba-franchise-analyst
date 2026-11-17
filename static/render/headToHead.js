// Animated head-to-head bars shared by the team and player comparison views.
//
// One row per stat: A's value | bar growing left from a center line | bar
// growing right | B's value, with the stat label underneath. Each bar's
// length shows how good that value is within a fixed, realistic range for
// the stat (DOMAINS below) -- not each side's share of the total, which made
// 111 vs 114.6 look identical. For lower-is-better stats the scale is
// flipped, so the longer bar always belongs to the better side.
const HeadToHead = (() => {
    // [min, max] each stat is scaled against. Values outside are clamped.
    const DOMAINS = {
        // Teams (per-game / 0-1 fractions, as the API returns them)
        team_ppg: [100, 125],
        team_opp_ppg: [100, 125],
        team_point_diff: [-15, 15],
        team_win_pct: [0, 1],
        team_fg_pct: [0.42, 0.52],
        team_fg3_pct: [0.30, 0.40],
        // Players
        player_ppg: [0, 35],
        player_apg: [0, 12],
        player_rpg: [0, 15],
        player_spg: [0, 2.5],
        player_ts_pct: [0.45, 0.70],
        player_usg_pct: [0.10, 0.40],
        player_pie: [0, 0.25],
        player_rating: [95, 130],
    };

    const MIN_BAR = 0.04; // a value never disappears entirely
    const STAGGER_MS = 60;
    const COUNT_MS = 700;

    const reducedMotion = () =>
        window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

    function barLength(value, domain, higherIsBetter) {
        const [min, max] = domain;
        let t = (value - min) / (max - min);
        t = Math.min(1, Math.max(0, t));
        if (!higherIsBetter) t = 1 - t;
        return Math.max(MIN_BAR, t);
    }

    // rows: [{ label, aVal, bVal, domain: 'team_ppg' | [min,max],
    //          higherIsBetter = true, format(v) -> string,
    //          formatDelta(d) -> string }]
    // a / b: { label, color }
    function build({ a, b, rows }) {
        const root = document.createElement('div');
        root.className = 'h2h';
        root.style.setProperty('--h2h-a', a.color);
        root.style.setProperty('--h2h-b', b.color);

        let aWins = 0, bWins = 0, counted = 0;
        const rowEls = [];

        rows.forEach((row, index) => {
            const higherIsBetter = row.higherIsBetter !== false;
            const format = row.format || ((v) => String(v));
            const formatDelta = row.formatDelta || ((d) => d.toFixed(1));
            const domain = Array.isArray(row.domain) ? row.domain : DOMAINS[row.domain];
            const hasA = row.aVal != null && !Number.isNaN(row.aVal);
            const hasB = row.bVal != null && !Number.isNaN(row.bVal);
            const both = hasA && hasB;

            let winner = null;
            if (both && row.aVal !== row.bVal) {
                const aBetter = higherIsBetter ? row.aVal > row.bVal : row.aVal < row.bVal;
                winner = aBetter ? 'a' : 'b';
            }
            if (both) {
                counted += 1;
                if (winner === 'a') aWins += 1;
                if (winner === 'b') bWins += 1;
            }

            let deltaText = '';
            if (both) {
                if (!winner) {
                    deltaText = 'Even';
                } else {
                    const leader = winner === 'a' ? a.label : b.label;
                    const d = formatDelta(Math.abs(row.aVal - row.bVal));
                    deltaText = higherIsBetter ? `${leader} +${d}` : `${leader} ${d} lower`;
                }
            }

            const el = document.createElement('div');
            el.className = 'h2h-row' + (winner ? ` winner-${winner}` : both ? ' tie' : '');
            el.style.setProperty('--i', index);
            el.tabIndex = 0;
            el.setAttribute('role', 'group');
            el.setAttribute('aria-label',
                `${row.label}: ${a.label} ${hasA ? format(row.aVal) : 'no data'}, ` +
                `${b.label} ${hasB ? format(row.bVal) : 'no data'}` +
                (deltaText ? `. ${deltaText}` : ''));

            const lenA = hasA ? barLength(row.aVal, domain, higherIsBetter) : 0;
            const lenB = hasB ? barLength(row.bVal, domain, higherIsBetter) : 0;

            el.innerHTML = `
                <div class="h2h-val a" aria-hidden="true">${hasA ? format(row.aVal) : '—'}</div>
                <div class="h2h-track a" aria-hidden="true"><span class="h2h-bar a" style="--len:${lenA}"></span></div>
                <div class="h2h-track b" aria-hidden="true"><span class="h2h-bar b" style="--len:${lenB}"></span></div>
                <div class="h2h-val b" aria-hidden="true">${hasB ? format(row.bVal) : '—'}</div>
                <div class="h2h-label" aria-hidden="true">
                    <span class="h2h-label-name">${escapeHtml(row.label)}${higherIsBetter ? '' : '<span class="h2h-hint"> · lower is better</span>'}</span>
                    <span class="h2h-label-delta">${escapeHtml(deltaText)}</span>
                </div>
            `;
            // Phones have no hover: a tap toggles the gap readout instead.
            el.addEventListener('click', () => el.classList.toggle('active'));

            rowEls.push({ el, row, format, hasA, hasB });
            root.appendChild(el);
        });

        root.prepend(buildSummary(a, b, aWins, bWins, counted));
        animateWhenVisible(root, rowEls);
        return root;
    }

    function buildSummary(a, b, aWins, bWins, counted) {
        const summary = document.createElement('div');
        summary.className = 'h2h-summary';
        let text;
        if (!counted) {
            text = 'No overlapping stats to compare';
        } else if (aWins === bWins) {
            text = `Even split, ${aWins}–${bWins}`;
        } else {
            const side = aWins > bWins ? 'a' : 'b';
            const lead = side === 'a' ? a : b;
            const wins = Math.max(aWins, bWins);
            text = `<span class="h2h-summary-lead ${side}">${escapeHtml(lead.label)}</span> leads ${wins} of ${counted} categories`;
        }
        summary.innerHTML = `
            <div class="h2h-summary-text">${text}</div>
            <div class="h2h-legend">
                <span class="h2h-legend-item a">${escapeHtml(a.label)}</span>
                <span class="h2h-legend-item b">${escapeHtml(b.label)}</span>
            </div>
        `;
        return summary;
    }

    // Bars grow and numbers count up the first time the block scrolls into
    // view; with reduced motion everything is simply drawn.
    function animateWhenVisible(root, rowEls) {
        const start = () => {
            root.classList.add('in-view');
            if (reducedMotion()) return;
            rowEls.forEach(({ el, row, format, hasA, hasB }, i) => {
                const delay = i * STAGGER_MS;
                if (hasA) countUp(el.querySelector('.h2h-val.a'), row.aVal, row.domain, format, delay);
                if (hasB) countUp(el.querySelector('.h2h-val.b'), row.bVal, row.domain, format, delay);
            });
        };

        if (reducedMotion() || !('IntersectionObserver' in window)) {
            root.classList.add('in-view');
            return;
        }
        const observer = new IntersectionObserver((entries) => {
            if (entries.some((e) => e.isIntersecting)) {
                observer.disconnect();
                start();
            }
        }, { threshold: 0.25 });
        observer.observe(root);
    }

    function countUp(node, target, domainKey, format, delay) {
        const domain = Array.isArray(domainKey) ? domainKey : DOMAINS[domainKey];
        // Count from the bottom of the stat's range (or 0 when 0 is in range),
        // so a 111 PPG doesn't spend most of the animation passing 0..100.
        const from = domain && domain[0] <= 0 && domain[1] >= 0 ? 0 : (domain ? domain[0] : 0);
        const begin = performance.now() + delay;
        node.textContent = format(from);
        const tick = (now) => {
            const t = Math.min(1, Math.max(0, (now - begin) / COUNT_MS));
            const eased = 1 - Math.pow(1 - t, 3);
            node.textContent = format(t >= 1 ? target : from + (target - from) * eased);
            if (t < 1) requestAnimationFrame(tick);
        };
        requestAnimationFrame(tick);
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = String(str);
        return div.innerHTML;
    }

    return { build, DOMAINS };
})();
