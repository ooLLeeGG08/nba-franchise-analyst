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
        return `
            <section class="card" id="ideas">
                <div class="card-head"><h2>Trade ideas</h2><span class="note">legal under the cap rules</span></div>
                <div class="ideas"><p class="searching">Searching the league for players who fit… about 15 seconds the first time.</p>
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
            <div class="action-bar"><div class="inner"><a class="button wide" href="#/trade/${t.code}">Propose a trade</a></div></div>`);
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

    // --- router -----------------------------------------------------------------------------------

    function route() {
        const raw = location.hash.replace(/^#\/?/, "") || "";
        const [path, query = ""] = raw.split("?");
        const parts = path.split("/");
        tm = null;
        if (parts[0] === "teams") return teams();
        if (parts[0] === "team" && parts[1]) return team(parts[1].toUpperCase());
        if (parts[0] === "trade" && parts[1]) return openTrade(parts.slice(1).join("/"), query);
        return landing();
    }

    window.addEventListener("hashchange", route);
    route();
})();
