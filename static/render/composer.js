const Composer = (() => {
    function render(container, { onSend }) {
        container.innerHTML = '';

        const wrap = document.createElement('div');
        wrap.className = 'composer';

        const textarea = document.createElement('textarea');
        textarea.className = 'composer-input';
        textarea.placeholder = 'Ask anything about the NBA...';
        textarea.rows = 1;

        const sendButton = document.createElement('button');
        sendButton.type = 'button';
        sendButton.className = 'composer-send';
        sendButton.setAttribute('aria-label', 'Send message');
        sendButton.innerHTML = '<svg width="16" height="16" viewBox="0 0 16 16" fill="none"><path d="M2 8h11M8.5 3.5L13 8l-4.5 4.5" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round"/></svg>';

        function autoGrow() {
            textarea.style.height = 'auto';
            textarea.style.height = Math.min(textarea.scrollHeight, 200) + 'px';
        }

        function trySend() {
            const value = textarea.value.trim();
            if (!value) return;
            textarea.value = '';
            autoGrow();
            onSend(value);
        }

        textarea.addEventListener('input', autoGrow);
        textarea.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault();
                trySend();
            }
        });
        sendButton.addEventListener('click', trySend);

        wrap.appendChild(textarea);
        wrap.appendChild(sendButton);
        container.appendChild(wrap);

        return {
            setDisabled(disabled) {
                textarea.disabled = disabled;
                sendButton.disabled = disabled;
            },
            focus() {
                textarea.focus();
            },
        };
    }

    return { render };
})();
