// NBA Trade Simulator front end (Stage 3: landing, team selection, team analysis).
// Plain JavaScript, hash routes: #/  #/teams  #/team/OKC  #/trade/OKC
(function () {
    "use strict";

    const app = document.getElementById("app");
    const cache = {};

    // --- helpers -----------------------------------------------------------------------------

    function esc(value) {
        return String(value).replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" })[c]);
    }

    function pct(x) {
        return `${Math.round(x * 100)}%`;
    }

    function money(x) {
        return `${x < 0 ? "-" : ""}$${(Math.abs(x) / 1e6).toFixed(1)}M`;
    }

    function signed(x, digits = 1) {
        return `${x >= 0 ? "+" : ""}${x.toFixed(digits)}`;
    }

    function ordinal(n) {
        const s = ["th", "st", "nd", "rd"], v = n % 100;
        return n + (s[(v - 20) % 10] || s[v] || s[0]);
    }

    // Readable text on a team color: dark text on light colors, white on dark ones.
    function inkFor(hex) {
        const h = hex.replace("#", "");
        const [r, g, b] = [0, 2, 4].map((i) => parseInt(h.slice(i, i + 2), 16) / 255);
        const lum = 0.2126 * r + 0.7152 * g + 0.0722 * b;
        return lum > 0.55 ? "#111" : "#fff";
    }

    function badge(team, size = "") {
        const bg = team.colors.primary;
        const ring = bg.toLowerCase() === "#000000" ? "#3a3f47" : "transparent";
        return `<span class="badge ${size}" style="--team-bg:${bg};--team-ink:${inkFor(bg)};--team-ring:${ring}" aria-hidden="true">${esc(team.code)}</span>`;
    }

    async function getJSON(url) {
        if (cache[url]) return cache[url];
        const res = await fetch(url);
        if (!res.ok) throw new Error(`${res.status} ${url}`);
        cache[url] = await res.json();
        return cache[url];
    }

    function render(html) {
        app.innerHTML = html;
        window.scrollTo(0, 0);
    }

    function showError(err) {
        render(`<div class="error">Couldn't load this page. ${esc(err.message)}</div>
                <p style="text-align:center"><a class="button secondary" href="#/teams">Back to teams</a></p>`);
    }

    // --- screen 1: landing ----------------------------------------------------------------------

    function landing() {
        render(`
            <section class="landing">
                <div class="landing-mark" aria-hidden="true">TS</div>
                <h1>NBA Trade Simulator</h1>
                <p class="lead">Pick a team, find its weak spots, test trades against the 2026-27 cap rules, and see how the season plays out.</p>
                <div><a class="button" href="#/teams">Begin</a></div>
                <p class="fineprint">Rosters and stats as of Nov 9, 2026 · 10,000 simulated seasons</p>
            </section>`);
    }

    // --- screen 2: team selection ---------------------------------------------------------------

    let conference = sessionStorageGet("conference") || "East";

    function sessionStorageGet(key) {
        try { return sessionStorage.getItem(key); } catch (e) { return null; }
    }

    function sessionStorageSet(key, value) {
        try { sessionStorage.setItem(key, value); } catch (e) { /* private mode: fine */ }
    }

    async function teams() {
        render(`<div class="loading">Loading teams…</div>`);
        let data;
        try {
            data = await getJSON("/api/sim/teams");
        } catch (err) {
            return showError(err);
        }
        const draw = () => {
            const list = data.conferences[conference];
            render(`
                <div class="topbar"><a class="back" href="#/">‹ Home</a></div>
                <h1>Choose a team</h1>
                <div class="segmented" role="group" aria-label="Conference">
                    ${["East", "West"].map((c) => `<button type="button" data-conf="${c}" aria-pressed="${c === conference}">${c}ern</button>`).join("")}
                </div>
                <div class="team-grid">
                    ${list.map((t) => `
                        <a class="team-card" href="#/team/${t.code}" style="--team:${t.colors.primary === "#000000" ? "#5a606a" : t.colors.primary}">
                            ${badge(t)}
                            <span class="name">${esc(t.name)}</span>
                            <span class="meta">${t.mean_wins.toFixed(1)} wins<br>${pct(t.playoff_pct)} playoffs</span>
                        </a>`).join("")}
                </div>`);
            app.querySelectorAll("[data-conf]").forEach((b) => b.addEventListener("click", () => {
                conference = b.dataset.conf;
                sessionStorageSet("conference", conference);
                draw();
            }));
        };
        draw();
    }

    // --- screen 3: team analysis ----------------------------------------------------------------

    function projectionCard(t) {
        const p = t.projection;
        return `
            <section class="card">
                <div class="card-head"><h2>2026-27 projection</h2><span class="note">±${p.mcse_wins.toFixed(2)} wins (simulation error)</span></div>
                <div class="projection-row">
                    <div class="big-number">${p.mean_wins.toFixed(1)}<small>avg wins</small></div>
                    <div class="range-pill"><strong>${p.range_10_90[0]}–${p.range_10_90[1]}</strong>wins in 80% of seasons</div>
                </div>
                <div class="stats">
                    <div class="stat"><div class="value">${pct(p.playoff_pct)}</div><div class="label">Make playoffs</div></div>
                    <div class="stat"><div class="value">${pct(p.play_in_pct)}</div><div class="label">Play-in</div></div>
                    <div class="stat"><div class="value">${pct(p.top_seed_pct)}</div><div class="label">#1 seed</div></div>
                </div>
            </section>`;
    }

    function needsCard(t) {
        const rows = t.positions.map((p) => `
            <div class="position-row">
                <span>${esc(p.group)}</span>
                <div class="meter" role="img" aria-label="${esc(p.group)} rank ${p.rank} of 30"><span class="fill-${p.verdict}" style="width:${((31 - p.rank) / 30) * 100}%"></span></div>
                <span class="rank verdict-${p.verdict}">#${p.rank}</span>
            </div>`).join("");
        const worst = t.positions.find((p) => p.group === t.needs[0]);
        const headline = t.needs_type === "need"
            ? `Biggest need: <strong>${esc(t.needs.join(", ").toLowerCase())}</strong>. ${esc(worst.group)} rank ${ordinal(worst.rank)} of 30 once injuries are counted.`
            : `No glaring hole. Weakest spot: <strong>${esc(worst.group.toLowerCase())}</strong> (${ordinal(worst.rank)} of 30).`;
        const weak = t.weak_links.map((w) => `<span class="chip">${esc(w.name)} · ${esc(w.position)} · ${signed(w.impact)}</span>`).join("");
        const injured = t.long_injuries.map((i) => `<span class="chip bad">${esc(i.name)} out${i.return_date ? ` to ~${esc(formatDate(i.return_date))}` : ""}</span>`).join("");
        return `
            <section class="card">
                <div class="card-head"><h2>Where they need help</h2><span class="note">rank of 30</span></div>
                <div class="positions">${rows}</div>
                <p class="callout">${headline}</p>
                ${weak ? `<div class="chip-label">Weakest regulars (impact per 100 possessions)</div><div class="chips">${weak}</div>` : ""}
                ${injured ? `<div class="chip-label">Out long-term</div><div class="chips">${injured}</div>` : ""}
            </section>`;
    }

    function formatDate(iso) {
        const d = new Date(`${iso}T12:00:00`);
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: d.getFullYear() > 2027 ? "numeric" : undefined });
    }

    function capCard(t) {
        const c = t.cap, th = c.thresholds;
        const lo = 140e6;
        const hi = Math.max(th.second_apron * 1.06, c.team_salary * 1.03);
        const pos = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
        const markers = [["Cap", th.salary_cap], ["Tax", th.tax_line], ["1st", th.first_apron], ["2nd", th.second_apron]]
            .map(([label, x]) => `<div class="marker" style="left:${pos(x)}%"><span>${label}</span></div>`).join("");
        const next = Object.entries({ "the tax line": th.tax_line, "the first apron": th.first_apron, "the second apron": th.second_apron })
            .find(([, x]) => x > c.team_salary);
        const hardCap = c.hard_cap ? `Hard-capped at the ${c.hard_cap === "first_apron" ? "first" : "second"} apron.` : "Not hard-capped.";
        return `
            <section class="card">
                <div class="card-head"><h2>Payroll</h2><span class="status">${esc(c.status)}</span></div>
                <div class="payroll-figures"><span class="amount">${money(c.team_salary)}</span><span class="note">${c.standard_contracts} standard contracts</span></div>
                <div class="payroll-bar" role="img" aria-label="Team salary ${money(c.team_salary)} against the cap, tax line and aprons">
                    <div class="fill" style="width:${pos(c.team_salary)}%"></div>${markers}
                </div>
                <div class="cap-lines">
                    <span>${next ? `${money(next[1] - c.team_salary)} below ${next[0]}.` : `${money(c.team_salary - th.second_apron)} above the second apron.`} ${hardCap}</span>
                </div>
            </section>`;
    }

    function ideasCard(t) {
        const ideas = [1, 2, 3, 4].map((i) => `<div class="idea"><span>Trade idea ${i}</span><span>Coming soon</span></div>`).join("");
        return `
            <section class="card">
                <div class="card-head"><h2>Trade ideas</h2><span class="note">${esc(t.suggestions.message)}</span></div>
                <div class="ideas">${ideas}</div>
            </section>`;
    }

    function rosterCard(t) {
        const rows = t.roster.map((p) => `
            <div class="roster-row">
                <span class="who">${esc(p.name)}${p.long_injury ? `<span class="inj">OUT</span>` : ""}<small>${esc(p.position || "")}${p.age ? ` · ${Math.round(p.age)}` : ""} · ${money(p.salary)}</small></span>
                <span class="num">${signed(p.impact)}</span>
                <span class="num">${p.minutes.toFixed(0)} min</span>
            </div>`).join("");
        return `
            <section class="card">
                <details class="roster">
                    <summary>Roster</summary>
                    <p style="font-size:13px;margin-top:8px">Impact = points per 100 possessions vs an average player. Minutes when everyone is healthy.</p>
                    <div class="roster-list">${rows}</div>
                </details>
            </section>`;
    }

    async function team(code) {
        render(`<div class="loading">Loading ${esc(code)}…</div>`);
        let t;
        try {
            t = await getJSON(`/api/sim/team/${encodeURIComponent(code)}`);
        } catch (err) {
            return showError(err);
        }
        render(`
            <div class="topbar"><a class="back" href="#/teams">‹ Teams</a></div>
            <header class="team-head">
                ${badge(t, "large")}
                <div><h1>${esc(t.name)}</h1><div class="sub">${esc(t.conference)}ern Conference · projected ${ordinal(t.projection.conference_rank)}</div></div>
            </header>
            ${projectionCard(t)}
            ${needsCard(t)}
            ${ideasCard(t)}
            ${capCard(t)}
            ${rosterCard(t)}
            <div class="action-bar"><div class="inner"><a class="button wide" href="#/trade/${t.code}">Propose a trade</a></div></div>`);
    }

    // --- trade machine placeholder (Stage 4) ------------------------------------------------------

    function trade(code) {
        render(`
            <div class="topbar"><a class="back" href="#/team/${esc(code)}">‹ Back</a></div>
            <section class="placeholder">
                <h1>Trade machine</h1>
                <p>Build a trade, check it against the cap rules and save it. Arrives in the next stage.</p>
                <a class="button secondary" href="#/team/${esc(code)}">Back to team</a>
            </section>`);
    }

    // --- router -----------------------------------------------------------------------------------

    function route() {
        const parts = (location.hash.replace(/^#\/?/, "") || "").split("/");
        if (parts[0] === "teams") return teams();
        if (parts[0] === "team" && parts[1]) return team(parts[1].toUpperCase());
        if (parts[0] === "trade" && parts[1]) return trade(parts[1].toUpperCase());
        return landing();
    }

    window.addEventListener("hashchange", route);
    route();
})();
