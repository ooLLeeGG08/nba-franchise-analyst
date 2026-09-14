// Renders the message transcript. User messages are compact/subtle; assistant
// messages are plain prose (the backend deliberately returns no markdown) with
// the full team analytics dashboard mounted underneath when a team was
// resolved, fetched live from /api/team/<team> (never persisted into
// localStorage -- only the lightweight team key is stored per message).
const ChatThread = (() => {
    function render(container, thread) {
        container.innerHTML = '';
        const transcript = document.createElement('div');
        transcript.className = 'transcript';
        thread.messages.forEach((message) => {
            transcript.appendChild(buildMessageElement(message));
        });
        container.appendChild(transcript);
        scrollToBottom(container);
        return transcript;
    }

    function buildMessageElement(message) {
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

        if (message.team) {
            row.appendChild(buildDashboardMount(message.team));
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

    function appendThinkingBubble(container) {
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
                row.replaceWith(buildMessageElement(message));
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
