(function () {
    const ACTIVE_THREAD_KEY = 'nba-analyst-active-thread-v1';

    let threads = State.loadThreads();
    let activeThreadId = localStorage.getItem(ACTIVE_THREAD_KEY) || null;
    let searchQuery = '';
    let sending = false;

    const sidebarEl = document.getElementById('sidebarThreadList');
    const mainContentEl = document.getElementById('mainContent');
    const composerDockEl = document.getElementById('composerDock');
    const sidebarSearchEl = document.getElementById('sidebarSearch');
    const sidebarEl2 = document.getElementById('sidebar');
    const mobileMenuButton = document.getElementById('mobileMenuButton');
    const sidebarBackdrop = document.getElementById('sidebarBackdrop');
    const collapseButton = document.getElementById('collapseButton');
    const newChatButton = document.getElementById('newChatButton');

    let composer = null;

    function persistThreads() {
        State.saveThreads(threads);
    }

    function setActiveThread(id) {
        activeThreadId = id;
        if (id) localStorage.setItem(ACTIVE_THREAD_KEY, id);
        else localStorage.removeItem(ACTIVE_THREAD_KEY);
    }

    function getActiveThread() {
        return threads.find((t) => t.id === activeThreadId) || null;
    }

    function renderSidebarPane() {
        Sidebar.render(sidebarEl, {
            threads,
            activeThreadId,
            searchQuery,
            onSelect: (id) => {
                setActiveThread(id);
                renderAll();
                closeMobileSidebar();
            },
            onDelete: (id) => {
                threads = threads.filter((t) => t.id !== id);
                persistThreads();
                if (activeThreadId === id) setActiveThread(null);
                renderAll();
            },
            onRename: (id, newTitle) => {
                const thread = threads.find((t) => t.id === id);
                if (thread) {
                    thread.title = newTitle;
                    persistThreads();
                    renderSidebarPane();
                }
            },
        });
    }

    function chatHandlers() {
        return { onNavigateToTeam: (team) => handleSend(`Analyze the ${team}`) };
    }

    function renderMainPane() {
        const thread = getActiveThread();
        if (!thread || thread.messages.length === 0) {
            EmptyState.render(mainContentEl, { onSuggestionClick: handleSend });
        } else {
            ChatThread.render(mainContentEl, thread, chatHandlers());
        }
    }

    function renderComposerPane() {
        composer = Composer.render(composerDockEl, { onSend: handleSend });
        composer.setDisabled(sending);
    }

    function renderAll() {
        renderSidebarPane();
        renderMainPane();
        renderComposerPane();
    }

    async function handleSend(userInput) {
        if (sending) return;
        sending = true;
        if (composer) composer.setDisabled(true);

        let thread = getActiveThread();
        const isNewThread = !thread;
        if (isNewThread) {
            thread = State.createThread('chat');
            threads.unshift(thread);
            setActiveThread(thread.id);
        }

        // Render the thread view (empty-state -> transcript) then show the
        // user's message as UI-only until the reply succeeds -- matches the
        // backend's stateless design: a failed exchange isn't persisted into
        // the history sent on future requests.
        ChatThread.render(mainContentEl, thread, chatHandlers());
        ChatThread.appendUserMessage(mainContentEl, userInput);
        const thinking = ChatThread.appendThinkingBubble(mainContentEl, chatHandlers());

        const requestHistory = thread.messages.map((m) => ({ role: m.role, content: m.content }));

        try {
            const data = await Api.sendChatMessage(userInput, requestHistory);
            if (data.status !== 'success') throw new Error(data.error || 'Unknown error');

            const assistantMessage = {
                role: 'assistant',
                content: data.response,
                team: data.team || null,
                teams: data.teams || [],
            };
            thread.messages.push({ role: 'user', content: userInput }, assistantMessage);
            thread.updatedAt = new Date().toISOString();
            if (thread.messages.length === 2) thread.title = State.generateTitle(userInput);
            if (assistantMessage.team) thread.teamContext = assistantMessage.team;
            persistThreads();

            thinking.resolveAsAssistantMessage(assistantMessage);
            renderSidebarPane();
        } catch (e) {
            console.error(e);
            thinking.resolveAsError("Sorry, I'm having trouble connecting. Please try again.");
        } finally {
            sending = false;
            if (composer) {
                composer.setDisabled(false);
                composer.focus();
            }
        }
    }

    function openMobileSidebar() {
        sidebarEl2.classList.add('mobile-open');
        sidebarBackdrop.classList.add('visible');
    }

    function closeMobileSidebar() {
        sidebarEl2.classList.remove('mobile-open');
        sidebarBackdrop.classList.remove('visible');
    }

    mobileMenuButton.addEventListener('click', openMobileSidebar);
    sidebarBackdrop.addEventListener('click', closeMobileSidebar);

    collapseButton.addEventListener('click', () => {
        sidebarEl2.classList.toggle('collapsed');
    });

    newChatButton.addEventListener('click', () => {
        setActiveThread(null);
        renderAll();
        closeMobileSidebar();
        if (composer) composer.focus();
    });

    sidebarSearchEl.addEventListener('input', (e) => {
        searchQuery = e.target.value;
        renderSidebarPane();
    });

    renderAll();
})();
