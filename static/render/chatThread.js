// Renders the message transcript. User messages are compact/subtle; assistant
// messages are plain prose (the backend deliberately returns no markdown)
// with a data-driven visual companion mounted underneath, fetched live (never
// persisted into localStorage -- only lightweight team keys are stored per
// message): a comparison view for two teams, a single team's dashboard, or
// -- when no team was resolved at all -- the league-wide leaders table, so
// every assistant reply gets some visual answer, not just team questions.
const ChatThread = (() => {
    function render(container, thread, handlers = {}) {
        container.innerHTML = '';
        const transcript = document.createElement('div');
        transcript.className = 'transcript';
        thread.messages.forEach((message) => {
            transcript.appendChild(buildMessageElement(message, handlers));
        });
        container.appendChild(transcript);
        scrollToBottom(container);
        return transcript;
    }

    function buildMessageElement(message, handlers = {}) {
        if (message.role === 'user') {
            const row = document.createElement('div');
            row.className = 'message-row user';
            const bubble = document.createElement('div');
            bubble.className = 'message user-message';
            bubble.textContent = message.content;
            row.appendChild(bubble);
            return row;
        }

        const row = document.createElement('div');
        row.className = 'message-row assistant';

        if (!message.isError && message.trade) {
            row.appendChild(buildTradeBadge());
        }

        const body = document.createElement('div');
        body.className = 'message assistant-message' + (message.isError ? ' error' : '');
        body.textContent = message.content;
        row.appendChild(body);

        if (!message.isError) {
            const teams = message.teams || (message.team ? [message.team] : []);
            const players = message.players || (message.player ? [message.player] : []);
            // Messages saved before the server sent `comparison` keep the old
            // behavior (compare whenever two are mentioned).
            const wantsComparison = message.comparison === undefined ? true : message.comparison;
            if (wantsComparison && teams.length >= 2) {
                row.appendChild(buildComparisonMount(teams[0], teams[1], message.season));
            } else if (wantsComparison && players.length >= 2) {
                row.appendChild(buildPlayerComparisonMount(players[0], players[1], message.season));
            } else if (players.length === 1 && message.player) {
                row.appendChild(buildPlayerMount(message.player, handlers, message.season));
            } else if (message.team) {
                row.appendChild(buildDashboardMount(message.team, message.season));
            } else {
                row.appendChild(buildLeadersMount(handlers));
            }
        }

        return row;
    }

    // Trade questions get a structured breakdown (see llm.py's
    // TRADE_PROMPT_ADDENDUM) instead of the usual 3-5 sentence answer -- this
    // badge sets that expectation up front and makes explicit what the brief
    // calls for: distinguishing a preliminary basketball-fit judgment from a
    // verified statistic. It is never financial/cap advice; this app has no
    // contract or salary data to back that up.
    function buildTradeBadge() {
        const badge = document.createElement('div');
        badge.className = 'trade-badge';
        badge.textContent = 'Preliminary basketball-fit analysis — not a cap or contract check';
        return badge;
    }

    // Shared loading/error chrome for the five dashboard mounts below. `task`
    // is re-invoked on Retry (with the same mount node), so a flaky fetch
    // (cold-start Render dyno, a dropped connection) doesn't require
    // re-asking the question.
    function mountWithRetry(loadingText, errorText, task) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';

        function load() {
            mount.innerHTML = `<div class="dashboard-loading">${escapeHtml(loadingText)}</div>`;
            task(mount).catch((e) => {
                console.error(e);
                renderLoadError(mount, errorText, load);
            });
        }

        load();
        return mount;
    }

    function renderLoadError(mount, text, onRetry) {
        mount.innerHTML = '';
        const wrap = document.createElement('div');
        wrap.className = 'dashboard-loading dashboard-error';
        const label = document.createElement('span');
        label.textContent = text;
        wrap.appendChild(label);
        wrap.appendChild(buildRetryButton(onRetry));
        mount.appendChild(wrap);
    }

    function buildRetryButton(onRetry) {
        const button = document.createElement('button');
        button.type = 'button';
        button.className = 'retry-button';
        button.textContent = 'Retry';
        button.addEventListener('click', onRetry);
        return button;
    }

    function buildDashboardMount(team, season) {
        return mountWithRetry(
            `Loading ${team} analytics...`,
            `Couldn't load ${team} analytics.`,
            (mount) => Api.fetchTeamDashboard(team, season).then((bundle) => TeamDashboard.render(mount, bundle)),
        );
    }

    function buildComparisonMount(teamA, teamB, season) {
        return mountWithRetry(
            `Loading ${teamA} vs ${teamB}...`,
            "Couldn't load that comparison.",
            (mount) => Api.fetchTeamComparison(teamA, teamB, season).then((bundle) => ComparisonView.render(mount, bundle)),
        );
    }

    function buildPlayerComparisonMount(playerA, playerB, season) {
        return mountWithRetry(
            `Loading ${playerA} vs ${playerB}...`,
            "Couldn't load that comparison.",
            (mount) => Api.fetchPlayerComparison(playerA, playerB, season).then((bundle) => PlayerComparisonView.render(mount, bundle)),
        );
    }

    function buildPlayerMount(player, handlers, season) {
        return mountWithRetry(
            `Loading ${player}...`,
            `Couldn't load ${player}.`,
            (mount) => Api.fetchPlayerView(player, season).then((view) => PlayerView.render(mount, view, handlers)),
        );
    }

    function buildLeadersMount(handlers) {
        return mountWithRetry(
            'Loading league leaders...',
            "Couldn't load league leaders.",
            (mount) => Api.fetchLeaders().then((data) => LeadersTable.render(mount, data, handlers)),
        );
    }

    function appendThinkingBubble(container, handlers = {}) {
        const transcript = container.querySelector('.transcript');
        const row = document.createElement('div');
        row.className = 'message-row assistant';
        const bubble = document.createElement('div');
        bubble.className = 'message assistant-message thinking';
        bubble.textContent = 'Thinking...';
        row.appendChild(bubble);
        transcript.appendChild(row);
        scrollToBottom(container);

        return {
            resolveAsAssistantMessage(message) {
                row.replaceWith(buildMessageElement(message, handlers));
                scrollToBottom(container);
            },
            resolveAsError(text, onRetry) {
                bubble.textContent = text;
                bubble.classList.remove('thinking');
                bubble.classList.add('error');
                if (onRetry) row.appendChild(buildRetryButton(onRetry));
                scrollToBottom(container);
            },
        };
    }

    function appendUserMessage(container, content) {
        const transcript = container.querySelector('.transcript');
        transcript.appendChild(buildMessageElement({ role: 'user', content }));
        scrollToBottom(container);
    }

    function scrollToBottom(container) {
        container.scrollTop = container.scrollHeight;
    }

    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    return { render, appendThinkingBubble, appendUserMessage };
})();
