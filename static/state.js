// Thread state: persisted to localStorage. A "thread" is one conversation.
// kind: 'chat' | 'task' (task is a client-side categorization only -- the
// backend answers synchronously, there's no real async job engine behind it).
const STORAGE_KEY = 'nba-analyst-threads-v1';

const State = (() => {
    function loadThreads() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            const parsed = raw ? JSON.parse(raw) : [];
            return Array.isArray(parsed) ? parsed : [];
        } catch (e) {
            console.warn('Failed to load thread history from localStorage', e);
            return [];
        }
    }

    function saveThreads(threads) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(threads));
        } catch (e) {
            console.warn('Failed to persist thread history to localStorage', e);
        }
    }

    function makeId() {
        return 'thread-' + Math.random().toString(36).slice(2, 10) + Date.now().toString(36);
    }

    function createThread(kind) {
        const now = new Date().toISOString();
        return {
            id: makeId(),
            title: 'New chat',
            kind: kind || 'chat',
            createdAt: now,
            updatedAt: now,
            messages: [],
            teamContext: null,
        };
    }

    // Heuristic title generation from the first user message -- no LLM call
    // spent on titling.
    function generateTitle(firstMessage) {
        const original = firstMessage.trim();
        let title = original
            .replace(/^(why|how|what|who|when|where|tell me about|explain)\s+/i, '')
            .replace(/\?+$/, '')
            .trim();
        if (!title) title = original;
        title = title.charAt(0).toUpperCase() + title.slice(1);
        if (title.length > 48) title = title.slice(0, 45).trimEnd() + '...';
        return title || 'New chat';
    }

    function groupByRecency(threads) {
        const now = new Date();
        const startOfToday = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        const startOfYesterday = new Date(startOfToday);
        startOfYesterday.setDate(startOfYesterday.getDate() - 1);
        const sevenDaysAgo = new Date(startOfToday);
        sevenDaysAgo.setDate(sevenDaysAgo.getDate() - 7);

        const groups = { Today: [], Yesterday: [], 'Previous 7 days': [], Older: [] };
        const sorted = [...threads].sort((a, b) => new Date(b.updatedAt) - new Date(a.updatedAt));

        for (const thread of sorted) {
            const updated = new Date(thread.updatedAt);
            if (updated >= startOfToday) groups.Today.push(thread);
            else if (updated >= startOfYesterday) groups.Yesterday.push(thread);
            else if (updated >= sevenDaysAgo) groups['Previous 7 days'].push(thread);
            else groups.Older.push(thread);
        }
        return groups;
    }

    return { loadThreads, saveThreads, createThread, generateTitle, groupByRecency };
})();
