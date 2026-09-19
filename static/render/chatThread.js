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
                row.appendChild(buildComparisonMount(teams[0], teams[1]));
            } else if (wantsComparison && players.length >= 2) {
                row.appendChild(buildPlayerComparisonMount(players[0], players[1]));
            } else if (players.length === 1 && message.player) {
                row.appendChild(buildPlayerMount(message.player, handlers));
            } else if (message.team) {
                row.appendChild(buildDashboardMount(message.team));
            } else {
                row.appendChild(buildLeadersMount(handlers));
            }
        }

        return row;
    }

    function buildDashboardMount(team) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';
        mount.innerHTML = `<div class="dashboard-loading">Loading ${escapeHtml(team)} analytics...</div>`;

        Api.fetchTeamDashboard(team)
            .then((bundle) => TeamDashboard.render(mount, bundle))
            .catch((e) => {
                console.error(e);
                mount.innerHTML = `<div class="dashboard-loading">Couldn't load ${escapeHtml(team)} analytics.</div>`;
            });

        return mount;
    }

    function buildComparisonMount(teamA, teamB) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';
        mount.innerHTML = `<div class="dashboard-loading">Loading ${escapeHtml(teamA)} vs ${escapeHtml(teamB)}...</div>`;

        Api.fetchTeamComparison(teamA, teamB)
            .then((bundle) => ComparisonView.render(mount, bundle))
            .catch((e) => {
                console.error(e);
                mount.innerHTML = `<div class="dashboard-loading">Couldn't load that comparison.</div>`;
            });

        return mount;
    }

    function buildPlayerComparisonMount(playerA, playerB) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';
        mount.innerHTML = `<div class="dashboard-loading">Loading ${escapeHtml(playerA)} vs ${escapeHtml(playerB)}...</div>`;

        Api.fetchPlayerComparison(playerA, playerB)
            .then((bundle) => PlayerComparisonView.render(mount, bundle))
            .catch((e) => {
                console.error(e);
                mount.innerHTML = `<div class="dashboard-loading">Couldn't load that comparison.</div>`;
            });

        return mount;
    }

    function buildPlayerMount(player, handlers) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';
        mount.innerHTML = `<div class="dashboard-loading">Loading ${escapeHtml(player)}...</div>`;

        Api.fetchPlayerView(player)
            .then((view) => PlayerView.render(mount, view, handlers))
            .catch((e) => {
                console.error(e);
                mount.innerHTML = `<div class="dashboard-loading">Couldn't load ${escapeHtml(player)}.</div>`;
            });

        return mount;
    }

    function buildLeadersMount(handlers) {
        const mount = document.createElement('div');
        mount.className = 'dashboard-mount';
        mount.innerHTML = `<div class="dashboard-loading">Loading league leaders...</div>`;

        Api.fetchLeaders()
            .then((data) => LeadersTable.render(mount, data, handlers))
            .catch((e) => {
                console.error(e);
                mount.innerHTML = `<div class="dashboard-loading">Couldn't load league leaders.</div>`;
            });

        return mount;
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
            resolveAsError(text) {
                bubble.textContent = text;
                bubble.classList.remove('thinking');
                bubble.classList.add('error');
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
