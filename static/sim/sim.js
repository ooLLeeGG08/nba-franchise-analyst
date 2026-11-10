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
                <p class="fineprint">${dataStatus && dataStatus.as_of ? `Rosters, contracts and stats as of ${esc(formatDate(dataStatus.as_of, true))}` : "Rosters, contracts and stats"} · 10,000 simulated seasons</p>
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
        const injured = t.long_injuries.map((i) => `<span class="chip bad">${esc(i.name)} ${i.out_for_season ? "out for the season" : `out${i.return_date ? ` to ~${esc(formatDate(i.return_date))}` : ""}`}</span>`).join("");
        return `
            <section class="card">
                <div class="card-head"><h2>Where they need help</h2><span class="note">rank of 30</span></div>
                <div class="positions">${rows}</div>
                <p class="callout">${headline}</p>
                ${weak ? `<div class="chip-label">Weakest regulars (impact per 100 possessions)</div><div class="chips">${weak}</div>` : ""}
                ${injured ? `<div class="chip-label">Out long-term</div><div class="chips">${injured}</div>` : ""}
            </section>`;
    }

    function formatDate(iso, withYear = false) {
        const d = new Date(`${iso}T12:00:00`);
        return d.toLocaleDateString("en-US", { month: "short", day: "numeric", year: withYear || d.getFullYear() > 2027 ? "numeric" : undefined });
    }

    // How old league.json's data is (/api/sim/status); a bar on every screen when it's stale.
    let dataStatus = null;

    async function loadDataStatus() {
        try {
            dataStatus = await getJSON("/api/sim/status");
        } catch (err) {
            return;
        }
        const bar = document.getElementById("data-warning");
        if (dataStatus.stale) {
            bar.textContent = dataStatus.as_of
                ? `Data is ${dataStatus.age_days} day${dataStatus.age_days === 1 ? "" : "s"} old (as of ${formatDate(dataStatus.as_of, true)}). Trades, signings and injuries since then aren't included.`
                : "The data's date is unknown, so it may be out of date.";
            bar.hidden = false;
        }
        if (!location.hash || location.hash === "#/") landing();
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
        return `
            <section class="card" id="ideas">
                <div class="card-head"><h2>Trade ideas</h2><span class="note">legal under the cap rules</span></div>
                <div class="ideas"><p class="searching">Searching the league for players who fit… about 10 seconds the first time.</p>
                ${[1, 2, 3, 4].map(() => `<div class="idea skeleton"></div>`).join("")}</div>
            </section>`;
    }

    function playerLine(p, from) {
        return `<li><span>${esc(p.name)} <small>${esc(p.position || "")} · ${money(p.salary)}${from ? ` · from ${esc(from)}` : ""}</small></span><span class="amt">${signed(p.impact)}</span></li>`;
    }

    function suggestionCard(s, code) {
        const link = `#/trade/${code}/${s.partner}?m=${encodeMoves(s.moves)}`;
        const picks = s.picks_out.map((p) => `<li><span>${esc(p.label)} pick</span><span class="amt">pick</span></li>`).join("");
        const ex = s.explanation;
        return `
            <article class="suggestion">
                <div class="suggestion-head">
                    <span class="gain">${signed(s.win_change)} wins</span>
                    <span class="note">80% of seasons: ${signed(s.win_change_80[0], 0)} to ${signed(s.win_change_80[1], 0)}</span>
                    <span class="pill ok">✓ Works</span>
                </div>
                <span class="match ${s.match === "fits the need" ? "fit" : ""}">${esc(s.match[0].toUpperCase() + s.match.slice(1))}</span>
                <div class="sides compact">
                    <div><h3>${esc(code)} gets</h3><ul class="moves">${s.gets.map((g) => playerLine(g, s.partner)).join("")}</ul></div>
                    <div><h3>${esc(code)} sends</h3><ul class="moves">${s.sends.map((x) => playerLine(x)).join("")}${picks}</ul></div>
                </div>
                <p class="facts">Playoffs ${pct(s.playoff_before)} → ${pct(s.playoff_after)} · ${esc(s.cap.team.status_after)} · ${esc(s.partner)} ${signed(s.partner_win_change)} wins</p>
                <p class="explain">${esc(ex.text)} <span class="source">${ex.source === "ai" ? "AI summary, checked against the numbers" : "Summary from the numbers"}</span></p>
                <a class="button secondary wide" href="${link}">Open in trade machine</a>
            </article>`;
    }

    async function loadIdeas(t) {
        const box = document.getElementById("ideas");
        let data;
        try {
            data = await getJSON(`/api/sim/team/${t.code}/suggestions`);
        } catch (err) {
            if (box) box.querySelector(".ideas").innerHTML = `<p class="error">Couldn't load trade ideas.</p>`;
            return;
        }
        if (!document.getElementById("ideas") || !location.hash.startsWith(`#/team/${t.code}`)) return;
        const n = data.needs;
        const needLine = `<p class="needs-line">Looking for <strong>${n.positions.map((p) => ({ G: "guards", F: "forwards", C: "centers" })[p]).join(" and ")}</strong>
            with <strong>${esc(n.skills.join(", "))}</strong> <span class="source">${n.source === "ai" ? "AI read of the numbers" : "from the numbers"}</span></p>`;
        const rules = data.rules.max_partner_loss_wins != null
            ? `Only trades that add ${data.rules.min_win_gain}+ wins without costing the partner more than ${data.rules.max_partner_loss_wins} wins.` : "";
        const body = data.suggestions.length
            ? data.suggestions.map((s) => suggestionCard(s, t.code)).join("")
            : `<p class="empty">No trade found that fits. ${esc(rules)}</p>`;
        box.innerHTML = `
            <div class="card-head"><h2>Trade ideas</h2><span class="note">${data.searched.candidates} players searched · ${data.searched.legal_balanced} legal and balanced</span></div>
            ${needLine}${n.note ? `<p class="note">${esc(n.note)}</p>` : ""}
            <div class="ideas">${body}</div>
            ${data.suggestions.length && rules ? `<p class="note" style="margin-top:10px">${esc(rules)}</p>` : ""}`;
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
            <div class="action-bar"><div class="inner two">
                <a class="button secondary" href="#/trade/${t.code}">Propose a trade</a>
                <a class="button" href="#/select/${t.code}">Choose trades</a></div></div>`);
        loadIdeas(t);
    }

    // --- screen 4: trade machine ----------------------------------------------------------------
    // State lives in the URL (#/trade/ATL/PHI?m=player:id:FROM:TO,...) so a trade can be shared
    // or reopened. All cap rules run on the server (/api/sim/trade/check).

    const MAX_TEAMS = 4;
    const SAVED_KEY = "tradesim.saved";
    let tm = null;

    function encodeMoves(moves) {
        return moves.map((m) => [m.type, m.type === "cash" ? m.amount : m.id, m.from, m.to].map(encodeURIComponent).join(":")).join(",");
    }

    function decodeMoves(text) {
        if (!text) return [];
        return text.split(",").map((part) => {
            const [type, value, from, to] = part.split(":").map(decodeURIComponent);
            return type === "cash" ? { type, amount: Number(value), from, to } : { type, id: value, from, to };
        }).filter((m) => m.from && m.to);
    }

    function tradeHash() {
        const q = tm.moves.length ? `?m=${encodeMoves(tm.moves)}` : "";
        return `#/trade/${tm.teams.join("/")}${q}`;
    }

    function syncUrl() {
        history.replaceState(null, "", tradeHash());
    }

    function loadSaved() {
        try { return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]"); } catch (e) { return []; }
    }

    function storeSaved(list) {
        try { localStorage.setItem(SAVED_KEY, JSON.stringify(list)); return true; } catch (e) { return false; }
    }

    function teamOf(code) {
        return tm.assets[code];
    }

    function inTrade(type, id) {
        return tm.moves.some((m) => m.type === type && m.id === id);
    }

    async function trade(codes, moves) {
        render(`<div class="loading">Loading trade machine…</div>`);
        try {
            const assets = await Promise.all(codes.map((c) => getJSON(`/api/sim/trade/assets/${c}`)));
            tm = { teams: codes, active: codes[0], moves, assets: {}, result: null, panel: "roster",
                   showRules: false, picker: false, chooseFor: null, message: "" };
            assets.forEach((a) => { tm.assets[a.code] = a; });
            if (codes.length === 1) tm.picker = true;  // pick a partner first
        } catch (err) {
            return showError(err);
        }
        drawTrade();
        runCheck();
    }

    let checkTimer = null, checkSeq = 0;

    function runCheck() {
        clearTimeout(checkTimer);
        checkTimer = setTimeout(async () => {
            const seq = ++checkSeq;
            try {
                const res = await fetch("/api/sim/trade/check", {
                    method: "POST", headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ moves: tm.moves }),
                });
                const data = await res.json();
                if (seq !== checkSeq) return;  // a newer check is on its way
                tm.result = res.ok ? data : { works: false, errors: [data.error || "Check failed."], teams: {} };
            } catch (err) {
                tm.result = { works: false, errors: ["Couldn't reach the checker."], teams: {} };
            }
            drawTrade();
        }, 120);
    }

    function changed() {
        syncUrl();
        tm.message = "";
        drawTrade();
        runCheck();
    }

    function addAsset(type, id, from, to) {
        if (type !== "cash" && inTrade(type, id)) return;
        tm.moves.push(type === "cash" ? { type, amount: id, from, to } : { type, id, from, to });
        tm.chooseFor = null;
        changed();
    }

    function removeMove(index) {
        tm.moves.splice(index, 1);
        changed();
    }

    async function addTeam(code) {
        if (tm.teams.includes(code) || tm.teams.length >= MAX_TEAMS) return;
        try {
            tm.assets[code] = await getJSON(`/api/sim/trade/assets/${code}`);
        } catch (err) {
            return showError(err);
        }
        tm.teams.push(code);
        tm.active = code;
        tm.picker = false;
        changed();
    }

    function removeTeam(code) {
        if (tm.teams.length <= 1) return;
        tm.teams = tm.teams.filter((c) => c !== code);
        tm.moves = tm.moves.filter((m) => m.from !== code && m.to !== code);
        if (tm.active === code) tm.active = tm.teams[0];
        changed();
    }

    // --- pieces ---

    function statusBanner() {
        const r = tm.result;
        if (!r) return `<div class="verdict pending">Checking…</div>`;
        if (r.empty || !tm.moves.length) {
            return `<div class="verdict pending">${tm.teams.length < 2 ? "Add a partner team to start." : "Add players, picks or cash to build a trade."}</div>`;
        }
        if (r.errors && r.errors.length) {
            return `<div class="verdict bad"><strong>Doesn't work</strong><ul>${r.errors.map((e) => `<li>${esc(e)}</li>`).join("")}</ul></div>`;
        }
        const failing = Object.entries(r.teams).filter(([, t]) => !t.works);
        const notChecked = Object.values(r.teams).reduce((n, t) => n + t.counts.not_checked, 0);
        const reasons = failing.map(([code, t]) => `<li><strong>${esc(code)}:</strong> ${esc(t.failures[0])}${t.failures.length > 1 ? ` <span class="more">+${t.failures.length - 1} more</span>` : ""}</li>`).join("");
        const rulesCount = Object.values(r.teams).reduce((n, t) => n + t.rules.length, 0);
        return `
            <div class="verdict ${r.works ? "good" : "bad"}">
                <strong>${r.works ? "✓ Works" : "✗ Doesn't work"}</strong>
                ${r.works ? `<p>Every team passes the cap rules${notChecked ? ` (${notChecked} rule${notChecked > 1 ? "s" : ""} couldn't be checked with the data we have)` : ""}.</p>` : `<ul>${reasons}</ul>`}
                <button type="button" class="link" data-action="rules">${tm.showRules ? "Hide" : "Show"} every rule checked (${rulesCount})</button>
            </div>`;
    }

    const RULE_ICON = { pass: "✓", fail: "✗", not_checked: "?" };

    function rulesPanel() {
        if (!tm.showRules || !tm.result || !tm.result.teams) return "";
        return `<section class="card rules">${Object.entries(tm.result.teams).map(([code, t]) => `
            <h3>${esc(t.name)} <span class="note">${t.counts.pass} pass · ${t.counts.fail} fail · ${t.counts.not_checked} not checked</span></h3>
            <ul>${t.rules.map((rule) => `
                <li class="rule ${rule.status}"><span class="icon" aria-label="${rule.status}">${RULE_ICON[rule.status] || "?"}</span>
                    <span><strong>${esc(rule.label)}</strong> ${esc(rule.detail)}</span></li>`).join("")}</ul>`).join("")}
        </section>`;
    }

    function payrollBar(before, after, th) {
        const lo = 140e6, hi = Math.max(th.second_apron * 1.06, before * 1.03, after * 1.03);
        const pos = (x) => Math.max(0, Math.min(100, ((x - lo) / (hi - lo)) * 100));
        const markers = [["Cap", th.salary_cap], ["Tax", th.tax_line], ["1st", th.first_apron], ["2nd", th.second_apron]]
            .map(([label, x]) => `<div class="marker" style="left:${pos(x)}%"><span>${label}</span></div>`).join("");
        return `<div class="payroll-bar" role="img" aria-label="Payroll ${money(before)} before, ${money(after)} after">
                    <div class="fill" style="width:${pos(after)}%"></div>
                    <div class="before-mark" style="left:${pos(before)}%"></div>${markers}</div>`;
    }

    function moveLabel(m) {
        if (m.type === "cash") return { name: `Cash`, amount: money(m.amount) };
        if (m.type === "player") {
            const p = teamOf(m.from).roster.find((x) => x.id === m.id);
            return { name: p ? p.name : m.id, amount: p ? money(p.salary) : "" };
        }
        const pk = teamOf(m.from).picks.find((x) => x.id === m.id);
        return { name: pk ? pk.label : m.id, amount: "pick" };
    }

    function moveList(code, side) {
        const items = tm.moves.map((m, i) => ({ m, i })).filter(({ m }) => (side === "send" ? m.from : m.to) === code);
        if (!items.length) return `<p class="empty">Nothing yet.</p>`;
        return `<ul class="moves">${items.map(({ m, i }) => {
            const l = moveLabel(m);
            const other = side === "send" ? `to ${m.to}` : `from ${m.from}`;
            return `<li><span>${esc(l.name)} <small>${esc(other)}</small></span><span class="amt">${esc(l.amount)}</span>
                    <button type="button" class="x" data-remove="${i}" aria-label="Remove ${esc(l.name)}">×</button></li>`;
        }).join("")}</ul>`;
    }

    function teamPanel() {
        const code = tm.active, a = teamOf(code);
        const t = tm.result && tm.result.teams ? tm.result.teams[code] : null;
        const before = a.team_salary, after = t ? t.salary_after : before;
        const delta = after - before;
        const statusAfter = t ? t.status_after : a.status;
        return `
            <section class="card">
                <div class="team-line">${badge(a)}<div><h2>${esc(a.name)}</h2>
                    <div class="note">${esc(a.status)}${statusAfter !== a.status ? ` → <strong>${esc(statusAfter)}</strong>` : ""}</div></div>
                    ${t ? `<span class="pill ${t.works ? "ok" : "no"}">${t.works ? "Passes" : "Fails"}</span>` : ""}
                </div>
                <div class="payroll-figures"><span class="amount">${money(before)}${delta ? ` → ${money(after)}` : ""}</span>
                    <span class="note">${delta ? `${delta > 0 ? "+" : ""}${money(delta)}` : "payroll"}</span></div>
                ${payrollBar(before, after, a.thresholds)}
                ${t && t.exception_used ? `<p class="note">Uses the ${esc(t.exception_used.label)}.</p>` : ""}
                <div class="sides">
                    <div><h3>${esc(code)} sends</h3>${moveList(code, "send")}</div>
                    <div><h3>${esc(code)} gets</h3>${moveList(code, "get")}</div>
                </div>
            </section>`;
    }

    function destinations(code) {
        return tm.teams.filter((c) => c !== code);
    }

    function addButton(type, id, disabled, label = "Add") {
        if (disabled) return `<span class="note">${esc(disabled)}</span>`;
        const dests = destinations(tm.active);
        if (!dests.length) return `<span class="note">Add a team first</span>`;
        if (dests.length === 1) {
            return `<button type="button" class="add" data-add="${type}" data-id="${esc(id)}" data-to="${dests[0]}">${label} → ${dests[0]}</button>`;
        }
        if (tm.chooseFor === `${type}:${id}`) {
            return `<span class="dest">${dests.map((d) => `<button type="button" class="add" data-add="${type}" data-id="${esc(id)}" data-to="${d}">${d}</button>`).join("")}</span>`;
        }
        return `<button type="button" class="add" data-choose="${type}:${esc(id)}">${label} →</button>`;
    }

    function assetsPanel() {
        const a = teamOf(tm.active);
        const tabs = [["roster", "Roster"], ["picks", "Picks"], ["extras", "Exceptions & cash"]]
            .map(([k, l]) => `<button type="button" data-panel="${k}" aria-pressed="${tm.panel === k}">${l}</button>`).join("");
        let body = "";
        if (tm.panel === "roster") {
            body = a.roster.filter((p) => !inTrade("player", p.id)).map((p) => {
                const flags = [p.no_trade_clause ? "no-trade clause" : "", p.bird_veto ? "can veto" : "",
                               p.tradeable_from ? `signed this summer · from ${formatDate(p.tradeable_from)}` : ""].filter(Boolean);
                return `<li><span class="who">${esc(p.name)} <small>${esc(p.position || "")} · ${money(p.salary)}${flags.length ? ` · <em>${esc(flags.join(" · "))}</em>` : ""}</small></span>
                        ${addButton("player", p.id)}</li>`;
            }).join("");
        } else if (tm.panel === "picks") {
            body = a.picks.filter((pk) => !inTrade("pick", pk.id)).map((pk) => `
                <li><span class="who">${esc(pk.label)}${pk.kind === "conditional" ? `<small>${esc(pk.text)}</small>` : ""}</span>
                    ${addButton("pick", pk.id, pk.tradeable ? "" : "frozen")}</li>`).join("");
        } else {
            const ex = a.exceptions.length
                ? a.exceptions.map((e) => `<li><span class="who">${money(e.amount)} exception <small>from the ${esc(e.source)} trade · expires ${esc(formatDate(e.expires))}</small></span></li>`).join("")
                : `<li><span class="who"><small>No trade exceptions on file for ${esc(a.code)}.</small></span></li>`;
            body = `${ex}
                <li class="explain"><small>Exceptions can't be traded; the checker uses one automatically when salaries don't match.</small></li>
                <li><span class="who">Send cash <small>up to ${money(a.cash_limit)} a season</small></span>
                    <span class="cash"><input type="number" inputmode="decimal" min="0.1" step="0.1" max="${a.cash_limit / 1e6}" placeholder="$M" id="cashInput" aria-label="Cash in millions">
                    ${addButton("cash", "cash", "", "Add")}</span></li>`;
        }
        return `
            <section class="card">
                <div class="segmented three" role="group" aria-label="Assets">${tabs}</div>
                <ul class="assets">${body || `<li><span class="who"><small>Nothing left to add.</small></span></li>`}</ul>
            </section>`;
    }

    function teamPicker() {
        if (!tm.picker) return "";
        const all = Object.values(cache["/api/sim/teams"] ? cache["/api/sim/teams"].conferences : {}).flat();
        const options = all.filter((t) => !tm.teams.includes(t.code));
        return `
            <section class="card picker">
                <div class="card-head"><h2>Add a team</h2>${tm.teams.length > 1 ? `<button type="button" class="link" data-action="close-picker">Cancel</button>` : ""}</div>
                <div class="picker-grid">${options.map((t) => `<button type="button" class="pick-team" data-team="${t.code}">${badge(t)}<span>${esc(t.name)}</span></button>`).join("")}</div>
            </section>`;
    }

    function savedList() {
        const saved = loadSaved();
        if (!saved.length) return "";
        return `
            <section class="card">
                <div class="card-head"><h2>Saved trades (${saved.length})</h2><span class="note">on this device</span></div>
                <ul class="saved">${saved.map((s, i) => `
                    <li><a href="#/trade/${s.teams.join("/")}?m=${encodeMoves(s.moves)}">${esc(s.summary)}</a>
                        <button type="button" class="x" data-delete-saved="${i}" aria-label="Delete saved trade">×</button></li>`).join("")}</ul>
            </section>`;
    }

    function summarize() {
        return tm.teams.map((code) => {
            const names = tm.moves.filter((m) => m.to === code).map((m) => moveLabel(m).name);
            return `${code} gets ${names.length ? names.join(", ") : "nothing"}`;
        }).join(" · ");
    }

    function saveTrade() {
        if (!tm.result || !tm.result.works) return;
        const saved = loadSaved();
        const key = encodeMoves(tm.moves);
        if (saved.some((s) => encodeMoves(s.moves) === key)) {
            tm.message = "Already saved.";
        } else {
            saved.push({ teams: [...tm.teams], moves: tm.moves.map((m) => ({ ...m })), summary: summarize(), savedAt: new Date().toISOString() });
            tm.message = storeSaved(saved) ? `Saved. ${saved.length} trade${saved.length > 1 ? "s" : ""} in your list.` : "Couldn't save on this device.";
        }
        drawTrade();
    }

    function drawTrade() {
        const back = tm.teams[0];
        const tabs = tm.teams.map((c) => {
            const a = teamOf(c);
            return `<span class="tab ${c === tm.active ? "active" : ""}" style="--team:${a.colors.primary === "#000000" ? "#5a606a" : a.colors.primary}">
                        <button type="button" data-tab="${c}">${esc(c)}</button>
                        ${tm.teams.length > 1 ? `<button type="button" class="x" data-remove-team="${c}" aria-label="Remove ${esc(c)}">×</button>` : ""}</span>`;
        }).join("");
        const canAdd = tm.teams.length < MAX_TEAMS;
        const works = tm.result && tm.result.works && tm.moves.length;
        const scrollY = window.scrollY;
        app.innerHTML = `
            <div class="topbar"><a class="back" href="#/team/${back}">‹ ${esc(back)}</a><h2 class="title">Trade machine</h2></div>
            <div class="team-tabs">${tabs}${canAdd ? `<button type="button" class="tab add-team" data-action="picker" aria-label="Add a team">+</button>` : ""}</div>
            ${teamPicker()}
            ${tm.teams.length > 1 ? statusBanner() + rulesPanel() + teamPanel() + assetsPanel() : ""}
            ${savedList()}
            <div class="action-bar"><div class="inner">
                ${tm.message ? `<p class="toast">${esc(tm.message)}</p>` : ""}
                <button type="button" class="button wide" data-action="save" ${works ? "" : "disabled"}>${works ? "Save trade" : "Save (needs a trade that works)"}</button>
            </div></div>`;
        window.scrollTo(0, scrollY);
    }

    // One click handler for the whole trade screen.
    app.addEventListener("click", (ev) => {
        if (!tm || !location.hash.startsWith("#/trade/")) return;
        const el = ev.target.closest("button");
        if (!el) return;
        const d = el.dataset;
        if (d.tab) { tm.active = d.tab; tm.chooseFor = null; drawTrade(); }
        else if (d.removeTeam) removeTeam(d.removeTeam);
        else if (d.team) addTeam(d.team);
        else if (d.panel) { tm.panel = d.panel; tm.chooseFor = null; drawTrade(); }
        else if (d.choose) { tm.chooseFor = d.choose; drawTrade(); }
        else if (d.add) {
            if (d.add === "cash") {
                const input = document.getElementById("cashInput");
                const amount = Math.round(parseFloat(input && input.value) * 1e6);
                if (!(amount > 0)) { tm.message = "Enter a cash amount in millions."; return drawTrade(); }
                addAsset("cash", amount, tm.active, d.to);
            } else {
                addAsset(d.add, d.id, tm.active, d.to);
            }
        }
        else if (d.remove !== undefined) removeMove(Number(d.remove));
        else if (d.deleteSaved !== undefined) {
            const saved = loadSaved(); saved.splice(Number(d.deleteSaved), 1); storeSaved(saved); drawTrade();
        }
        else if (d.action === "rules") { tm.showRules = !tm.showRules; drawTrade(); }
        else if (d.action === "picker") { tm.picker = true; drawTrade(); }
        else if (d.action === "close-picker") { tm.picker = false; drawTrade(); }
        else if (d.action === "save") saveTrade();
    });

    async function openTrade(path, query) {
        const codes = path.split("/").map((c) => c.toUpperCase()).filter(Boolean).slice(0, MAX_TEAMS);
        const moves = decodeMoves(new URLSearchParams(query).get("m"));
        try { await getJSON("/api/sim/teams"); } catch (err) { return showError(err); }
        return trade(codes, moves);
    }

    // --- screen 5: trade selection ----------------------------------------------------------------
    // The 4 suggestions plus saved trades involving this team, as checkable cards. Every change
    // re-checks the chosen trades in order on the server (/api/sim/sequence/check).

    // Picked trades per team, in the order picked (later picks are checked against what earlier
    // ones leave). Each: {id, kind, moves, title, detail}.
    const selection = {};

    function ideaOption(sg, onTop) {
        return {
            id: `m:${encodeMoves(sg.moves)}`, kind: "Suggestion", moves: sg.moves,
            title: `Gets ${sg.gets.map((g) => g.name).join(" + ")} from ${sg.partner}`,
            detail: `Sends ${sg.sends.map((x) => x.name).concat(sg.picks_out.map((p) => p.label + " pick")).join(", ")}`,
            badge: `${signed(sg.win_change)} wins${onTop ? " on top of your picks" : " alone"}`,
            match: sg.match,
        };
    }

    function savedOptions(code) {
        return loadSaved().filter((sv) => sv.teams.includes(code)).map((sv) => ({
            id: `m:${encodeMoves(sv.moves)}`, kind: "Your trade", moves: sv.moves, title: sv.summary, detail: "", badge: "",
        }));
    }

    function encodeTrades(trades) {
        return trades.map((t) => encodeMoves(t.moves)).join("~");
    }

    function decodeTrades(text) {
        return (text || "").split("~").filter(Boolean).map((part, i) => ({ id: `t${i}`, moves: decodeMoves(part) }));
    }

    async function postJSON(url, body) {
        const res = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
        const data = await res.json();
        if (!res.ok) throw new Error(data.error || `${res.status}`);
        return data;
    }

    async function select(code) {
        const picked = selection[code] || (selection[code] = []);
        let plan = null, busy = true, removed = [], failed = false, request = 0;

        const optionCard = (o, on, extra = "") => `
            <label class="pick-card ${on ? "on" : ""}">
                <input type="checkbox" data-pick="${esc(o.id)}" ${on ? "checked" : ""}>
                <span class="pick-body">
                    <span class="pick-kind">${esc(o.kind)}${o.badge ? ` · ${esc(o.badge)}` : ""}</span>
                    <strong>${esc(o.title)}</strong>
                    ${o.detail ? `<small>${esc(o.detail)}</small>` : ""}
                    ${extra}
                </span>
            </label>`;

        const draw = () => {
            const ideas = plan ? plan.ideas.suggestions.map((sg) => ideaOption(sg, picked.length > 0)) : [];
            const pickedIds = new Set(picked.map((o) => o.id));
            const saved = savedOptions(code).filter((o) => !pickedIds.has(o.id));
            const alone = plan && plan.combined ? plan.combined.alone : {};
            const pickedCards = picked.map((o, i) => optionCard({ ...o, kind: `Pick ${i + 1}`,
                badge: alone[o.id] != null ? `${signed(alone[o.id])} wins alone` : "" }, true)).join("");
            const ideaCards = ideas.filter((o) => !pickedIds.has(o.id)).map((o) => optionCard(o, false)).join("");
            const savedCards = saved.map((o) => optionCard(o, false)).join("");
            const removedNote = removed.map((r) => `<p class="removed">Removed “${esc(r.title)}”: ${esc(r.reason)}</p>`).join("");
            const c = plan && plan.combined;
            const payroll = plan && picked.length ? Object.entries(plan.payroll).map(([cd, p]) => `
                <li><span>${esc(cd)} <small>${esc(p.status_before)}${p.status_after !== p.status_before ? ` → ${esc(p.status_after)}` : ""} · ${p.contracts_after} contracts</small></span>
                    <span class="amt">${money(p.before)} → ${money(p.after)}</span></li>`).join("") : "";
            const combinedLine = c ? (picked.length > 1
                ? `<p class="combined"><strong class="${c.change < 0 ? "neg" : "pos"}">Combined ${signed(c.change)} wins</strong> ${c.sum_alone != null ? `<span>(sum alone ${signed(c.sum_alone)})</span>` : ""}</p>
                   <p class="hint">One simulation with all ${picked.length} trades together. It differs from the sum when the new players share minutes.</p>`
                : `<p class="combined"><strong class="${c.change < 0 ? "neg" : "pos"}">${signed(c.change)} wins</strong></p>`) : "";
            render(`
                <div class="topbar"><a class="back" href="#/team/${code}">‹ ${esc(code)}</a><h2 class="title">Choose trades</h2></div>
                <p class="intro">Pick trades to run together, or none. After each pick, new ideas are found for the roster, payroll and picks it leaves, so every idea still works with your picks.</p>
                ${removedNote}
                ${picked.length ? `<h3 class="list-head">Your picks <span>checked in this order</span></h3><div class="pick-list">${pickedCards}</div>
                <section class="card">
                    <div class="card-head"><h2>Combined effect</h2><span class="note">${busy ? "Updating…" : ""}</span></div>
                    ${combinedLine}
                    <ul class="moves">${payroll}</ul>
                </section>` : ""}
                <h3 class="list-head">${picked.length ? "More ideas, on top of your picks" : "Trade ideas"}</h3>
                <div class="pick-list">${busy ? `<p class="searching">${picked.length ? "Finding ideas that work with your picks… about 10 seconds." : "Loading ideas…"}</p>`
                    : failed ? `<p class="empty">Couldn't load ideas. Try again.</p>`
                    : (ideaCards || `<p class="empty">No more trades that work with your picks and pass the realism rule.</p>`)}</div>
                ${savedCards ? `<h3 class="list-head">Your saved trades</h3><div class="pick-list">${savedCards}</div>` : ""}
                <div class="action-bar"><div class="inner">
                    <a class="button wide ${busy ? "disabled" : ""}" href="#/results/${code}?t=${encodeTrades(picked)}">
                        ${picked.length ? `Simulate the season with ${picked.length} trade${picked.length > 1 ? "s" : ""}` : "Simulate the season as is"}</a>
                </div></div>`);
            app.querySelectorAll("[data-pick]").forEach((box) => box.addEventListener("change", () => {
                const id = box.dataset.pick;
                if (box.checked) {
                    const o = [...ideas, ...saved].find((x) => x.id === id);
                    if (o && !picked.some((x) => x.id === id)) picked.push({ id: o.id, kind: o.kind, moves: o.moves, title: o.title, detail: o.detail });
                } else {
                    const i = picked.findIndex((x) => x.id === id);
                    if (i >= 0) picked.splice(i, 1);
                }
                refresh();
            }));
        };

        const refresh = async () => {
            const mine = ++request;
            busy = true; removed = []; failed = false;
            draw();
            try {
                const r = await postJSON("/api/sim/sequence/plan", { team: code, trades: picked.map((o) => ({ id: o.id, moves: o.moves })) });
                if (mine !== request) return;  // a newer click is on its way
                // Picks the new state blocks are removed (with the reason).
                for (const v of r.removed) {
                    const i = picked.findIndex((o) => o.id === v.id);
                    if (i >= 0) removed.push({ title: picked.splice(i, 1)[0].title, reason: v.reason });
                }
                if (r.removed.length) {
                    const note = removed;
                    await refresh();
                    removed = note;
                    return draw();
                }
                plan = r;
            } catch (err) {
                if (mine !== request) return;
                failed = true;
            }
            busy = false;
            draw();
        };
        refresh();
    }

    // --- screen 6: results ------------------------------------------------------------------------

    function percentile(dist, q) {
        const total = dist.reduce((a, b) => a + b, 0);
        let run = 0;
        for (let w = 0; w < dist.length; w++) {
            run += dist[w];
            if (run >= q * total) return w;
        }
        return dist.length - 1;
    }

    // Two win distributions (before / after) as frequency lines with a light fill.
    // Colors: palette slots 1 and 2 (dark), validated against the card surface.
    function distributionChart(before, after) {
        const W = 340, H = 180, pad = { l: 34, r: 10, t: 14, b: 26 };
        const nb = before.reduce((a, b) => a + b, 0), na = after.reduce((a, b) => a + b, 0);
        const pb = before.map((c) => c / nb), pa = after.map((c) => c / na);
        const nonzero = (p) => p.map((v, i) => (v > 0.0005 ? i : null)).filter((i) => i !== null);
        const xs = nonzero(pb).concat(nonzero(pa));
        const lo = Math.max(0, Math.min(...xs) - 2), hi = Math.min(82, Math.max(...xs) + 2);
        const ymax = Math.max(...pb, ...pa) * 1.12;
        const x = (w) => pad.l + ((w - lo) / (hi - lo)) * (W - pad.l - pad.r);
        const y = (p) => H - pad.b - (p / ymax) * (H - pad.t - pad.b);
        const line = (p) => p.slice(lo, hi + 1).map((v, i) => `${i ? "L" : "M"}${x(lo + i).toFixed(1)},${y(v).toFixed(1)}`).join("");
        const area = (p) => `${line(p)}L${x(hi).toFixed(1)},${y(0)}L${x(lo).toFixed(1)},${y(0)}Z`;
        const ticks = [];
        for (let w = Math.ceil(lo / 10) * 10; w <= hi; w += 10) ticks.push(w);
        const yticks = [0.02, 0.04, 0.06, 0.08, 0.10].filter((v) => v < ymax);
        // Direct labels sit beside each curve's peak, on the outer side so they never collide.
        const peak = (p) => p.indexOf(Math.max(...p.slice(lo, hi + 1)));
        const afterRight = peak(pa) >= peak(pb);
        const label = (p, name, cls) => {
            const w = peak(p);
            const right = (cls === "after") === afterRight;
            return `<text class="direct ${cls}" x="${(x(w) + (right ? 6 : -6)).toFixed(1)}" y="${(y(p[w]) - 4).toFixed(1)}" text-anchor="${right ? "start" : "end"}">${name}</text>`;
        };
        return `
            <div class="chart" data-lo="${lo}" data-hi="${hi}">
                <div class="legend"><span><i class="sw before"></i>Before</span><span><i class="sw after"></i>After</span></div>
                <svg viewBox="0 0 ${W} ${H}" role="img" aria-label="Distribution of simulated wins before and after the trades">
                    ${yticks.map((v) => `<line class="grid" x1="${pad.l}" x2="${W - pad.r}" y1="${y(v)}" y2="${y(v)}"/><text class="axis" x="${pad.l - 6}" y="${y(v) + 3}" text-anchor="end">${Math.round(v * 100)}%</text>`).join("")}
                    <line class="baseline" x1="${pad.l}" x2="${W - pad.r}" y1="${y(0)}" y2="${y(0)}"/>
                    ${ticks.map((w) => `<text class="axis" x="${x(w)}" y="${H - 8}" text-anchor="middle">${w}</text>`).join("")}
                    <path class="area before" d="${area(pb)}"/><path class="area after" d="${area(pa)}"/>
                    <path class="line before" d="${line(pb)}"/><path class="line after" d="${line(pa)}"/>
                    ${label(pb, "Before", "before")}${label(pa, "After", "after")}
                    <line class="crosshair" x1="0" x2="0" y1="${pad.t}" y2="${y(0)}" visibility="hidden"/>
                    <rect class="hit" x="${pad.l}" y="${pad.t}" width="${W - pad.l - pad.r}" height="${H - pad.t - pad.b}"/>
                </svg>
                <div class="tooltip" hidden></div>
                <p class="axis-title">Wins in a simulated season</p>
            </div>`;
    }

    function wireChart(root, before, after) {
        const chart = root.querySelector(".chart");
        if (!chart) return;
        const svg = chart.querySelector("svg"), hit = chart.querySelector(".hit"), cross = chart.querySelector(".crosshair");
        const tip = chart.querySelector(".tooltip");
        const lo = +chart.dataset.lo, hi = +chart.dataset.hi;
        const nb = before.reduce((a, b) => a + b, 0), na = after.reduce((a, b) => a + b, 0);
        const move = (ev) => {
            const r = hit.getBoundingClientRect(), sr = svg.getBoundingClientRect();
            const frac = Math.max(0, Math.min(1, (ev.clientX - r.left) / r.width));
            const w = Math.round(lo + frac * (hi - lo));
            const vbX = 34 + ((w - lo) / (hi - lo)) * (340 - 44);
            cross.setAttribute("x1", vbX); cross.setAttribute("x2", vbX); cross.setAttribute("visibility", "visible");
            tip.hidden = false;
            tip.innerHTML = `<strong>${w} wins</strong><span><i class="sw before"></i>Before ${(before[w] / nb * 100).toFixed(1)}%</span><span><i class="sw after"></i>After ${(after[w] / na * 100).toFixed(1)}%</span>`;
            const left = (vbX / 340) * sr.width;
            tip.style.left = `${Math.min(Math.max(left - 70, 0), sr.width - 140)}px`;
        };
        const leave = () => { tip.hidden = true; cross.setAttribute("visibility", "hidden"); };
        hit.addEventListener("pointermove", move);
        hit.addEventListener("pointerdown", move);
        hit.addEventListener("pointerleave", leave);
    }

    async function results(code, query) {
        const trades = decodeTrades(new URLSearchParams(query).get("t"));
        render(`<div class="loading">Simulating 10,000 seasons…</div>`);
        let r;
        try {
            r = await postJSON("/api/sim/sequence/simulate", { team: code, trades });
        } catch (err) {
            return showError(err);
        }
        const b = r.before, a = r.after, d = r.delta;
        const odds = [["Make playoffs", "playoff_pct"], ["Play-in", "play_in_pct"], ["#1 seed", "top_seed_pct"]].map(([label, k]) =>
            `<div class="stat"><div class="value">${pct(a[k])}</div><div class="label">${label} <span class="was">was ${pct(b[k])}</span></div></div>`).join("");
        const pcts = [0.1, 0.25, 0.5, 0.75, 0.9];
        const table = `<table class="data-table"><thead><tr><th>Percentile</th><th>Before</th><th>After</th></tr></thead><tbody>
            ${pcts.map((q) => `<tr><td>${q * 100}th</td><td>${percentile(b.distribution, q)}</td><td>${percentile(a.distribution, q)}</td></tr>`).join("")}</tbody></table>`;
        // Conference tables: every team after the trades, change vs the no-trade season.
        const confTable = (conf) => {
            const rows = r.standings.tables[conf].map((t, i) => {
                const flat = Math.abs(t.win_change) < 0.1;
                return `
                <tr class="${t.you ? "you" : ""} ${i === 5 || i === 9 ? "cut" : ""}">
                    <td class="rank">${i + 1}</td>
                    <td class="team"><span class="team-cell">${badge(t)}<span>${esc(t.code)}${t.you ? `<small>You</small>` : t.partner ? `<small>Trade</small>` : ""}</span></span></td>
                    <td><strong>${t.mean_wins.toFixed(1)}</strong><small>${t.range[0]}–${t.range[1]}</small></td>
                    <td>${pct(t.playoff_pct)}</td><td>${pct(t.play_in_pct)}</td><td>${pct(t.top_seed_pct)}</td>
                    <td class="chg ${flat ? "flat" : t.win_change < 0 ? "neg" : "pos"}">${flat ? "0.0" : signed(t.win_change)}</td>
                </tr>`;
            }).join("");
            return `<div class="table-scroll"><table class="standings">
                <thead><tr><th class="rank">#</th><th class="team">Team</th><th>Wins<small>10–90%</small></th><th>Playoffs</th><th>Play-in</th><th>#1 seed</th><th>Change</th></tr></thead>
                <tbody>${rows}</tbody></table></div>`;
        };
        const own = r.standings.own, other = own === "East" ? "West" : "East";
        const otherHasPartner = r.standings.tables[other].some((t) => t.partner);
        const confName = (c) => `${c}ern Conference`;
        const standingsHtml = `
            <section class="card">
                <div class="card-head"><h2>${confName(own)}</h2><span class="note">after the trades</span></div>
                ${confTable(own)}
                <p class="hint">Sorted by average wins. Lines mark 6th (playoffs) and 10th (play-in). Change = average wins vs the season with no trades (same simulated seasons).</p>
            </section>
            <details class="card conf-other" ${otherHasPartner ? "open" : ""}>
                <summary><h2>${confName(other)}</h2><span class="note">${otherHasPartner ? "has a trade partner" : "tap to show"}</span></summary>
                ${confTable(other)}
            </details>`;
        const applied = r.trades.map((t, i) => `<li>${t.works ? "✓" : "✗"} Trade ${i + 1}${t.works ? "" : ` blocked: ${esc(t.reason)}`}</li>`).join("");
        const ex = r.explanation;
        render(`
            <div class="topbar"><a class="back" href="#/select/${code}">‹ Choose trades</a><h2 class="title">Results</h2></div>
            <header class="team-head">${badge(r, "large")}<div><h1>${esc(r.name)}</h1>
                <div class="sub">${r.applied ? `With ${r.applied} trade${r.applied > 1 ? "s" : ""}` : "No trades: the season as it stands"} · ${r.n_sims.toLocaleString()} simulated seasons</div></div></header>
            <section class="card">
                <div class="card-head"><h2>Projected wins</h2><span class="note">±${d.mean_wins.mcse.toFixed(2)} wins (simulation error)</span></div>
                <div class="projection-row">
                    <div class="big-number">${b.mean_wins.toFixed(1)}<span class="arrow">→</span>${a.mean_wins.toFixed(1)}</div>
                    <div class="range-pill"><strong class="${d.mean_wins.change < 0 ? "neg" : "pos"}">${signed(d.mean_wins.change)} wins</strong>80% of seasons: ${signed(d.mean_wins.p10, 0)} to ${signed(d.mean_wins.p90, 0)}</div>
                </div>
                ${r.combined ? `<p class="combined">Combined ${signed(r.combined.change)} wins${r.combined.sum_alone != null ? ` <span>(sum alone ${signed(r.combined.sum_alone)})</span>` : ""}</p>` : ""}
                <p class="ranges">Range (10–90%): <strong>${b.range[0]}–${b.range[1]}</strong> before → <strong>${a.range[0]}–${a.range[1]}</strong> after</p>
                ${distributionChart(b.distribution, a.distribution)}
                <details class="table-view"><summary>Show as table</summary>${table}</details>
            </section>
            <section class="card"><div class="stats">${odds}</div></section>
            <section class="card">
                <div class="card-head"><h2>What changed</h2><span class="note">${ex.source === "ai" ? "AI summary, checked against the numbers" : "Summary from the numbers"}</span></div>
                <p class="explain">${esc(ex.text)}</p>
            </section>
            ${standingsHtml}
            ${applied ? `<section class="card"><div class="card-head"><h2>Trades</h2></div><ul class="applied">${applied}</ul></section>` : ""}
            <div class="action-bar"><div class="inner two">
                <a class="button secondary" href="#/select/${code}">Change trades</a>
                <a class="button" href="#/teams">Start over</a></div></div>`);
        wireChart(app, b.distribution, a.distribution);
    }

    // --- router -----------------------------------------------------------------------------------

    function route() {
        const raw = location.hash.replace(/^#\/?/, "") || "";
        const [path, query = ""] = raw.split("?");
        const parts = path.split("/");
        tm = null;
        if (parts[0] === "teams") return teams();
        if (parts[0] === "team" && parts[1]) return team(parts[1].toUpperCase());
        if (parts[0] === "trade" && parts[1]) return openTrade(parts.slice(1).join("/"), query);
        if (parts[0] === "select" && parts[1]) return select(parts[1].toUpperCase());
        if (parts[0] === "results" && parts[1]) return results(parts[1].toUpperCase(), query);
        return landing();
    }

    window.addEventListener("hashchange", route);
    route();
    loadDataStatus();
})();
