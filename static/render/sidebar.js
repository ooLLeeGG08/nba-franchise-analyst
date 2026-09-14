const Sidebar = (() => {
    function render(container, { threads, activeThreadId, searchQuery, onSelect, onDelete, onRename }) {
        container.innerHTML = '';

        const filtered = searchQuery
            ? threads.filter((t) => t.title.toLowerCase().includes(searchQuery.toLowerCase()))
            : threads;

        const groups = State.groupByRecency(filtered);
        const groupOrder = ['Today', 'Yesterday', 'Previous 7 days', 'Older'];

        let hasAny = false;
        groupOrder.forEach((groupName) => {
            const groupThreads = groups[groupName];
            if (!groupThreads.length) return;
            hasAny = true;

            const section = document.createElement('div');
            section.className = 'sidebar-group';

            const label = document.createElement('div');
            label.className = 'sidebar-group-label';
            label.textContent = groupName;
            section.appendChild(label);

            groupThreads.forEach((thread) => {
                section.appendChild(renderThreadRow(thread, thread.id === activeThreadId, onSelect, onDelete, onRename));
            });

            container.appendChild(section);
        });

        if (!hasAny) {
            const empty = document.createElement('div');
            empty.className = 'sidebar-empty';
            empty.textContent = searchQuery ? 'No matching chats' : 'No conversations yet';
            container.appendChild(empty);
        }
    }

    function renderThreadRow(thread, isActive, onSelect, onDelete, onRename) {
        const row = document.createElement('div');
        row.className = 'thread-row' + (isActive ? ' active' : '');

        const kindDot = document.createElement('span');
        kindDot.className = 'thread-kind-dot ' + (thread.kind === 'task' ? 'task' : 'chat');
        row.appendChild(kindDot);

        const title = document.createElement('span');
        title.className = 'thread-title';
        title.textContent = thread.title;
        title.title = thread.title;
        row.appendChild(title);

        const actions = document.createElement('span');
        actions.className = 'thread-actions';

        const renameBtn = document.createElement('button');
        renameBtn.className = 'thread-action-button';
        renameBtn.type = 'button';
        renameBtn.title = 'Rename';
        renameBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M11.5 2.5l2 2L5 13l-2.5.5L3 11l8.5-8.5z" stroke="currentColor" stroke-width="1.3" stroke-linejoin="round"/></svg>';
        renameBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            const next = prompt('Rename chat', thread.title);
            if (next && next.trim()) onRename(thread.id, next.trim());
        });
        actions.appendChild(renameBtn);

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'thread-action-button';
        deleteBtn.type = 'button';
        deleteBtn.title = 'Delete';
        deleteBtn.innerHTML = '<svg width="13" height="13" viewBox="0 0 16 16" fill="none"><path d="M3 4.5h10M6.5 4.5V3a1 1 0 011-1h1a1 1 0 011 1v1.5M6 7.5v4M10 7.5v4M4 4.5l.6 8.4a1 1 0 001 .9h4.8a1 1 0 001-.9l.6-8.4" stroke="currentColor" stroke-width="1.3" stroke-linecap="round" stroke-linejoin="round"/></svg>';
        deleteBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            if (confirm(`Delete "${thread.title}"?`)) onDelete(thread.id);
        });
        actions.appendChild(deleteBtn);

        row.appendChild(actions);
        row.addEventListener('click', () => onSelect(thread.id));
        return row;
    }

    return { render };
})();
