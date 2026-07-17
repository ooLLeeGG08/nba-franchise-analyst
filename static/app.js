const screen1 = document.getElementById('screen1');
const screen2 = document.getElementById('screen2');
const chatbotOutput = document.getElementById('chatbotOutput');

let history = [];

function wireInput(inputId, buttonId) {
    const input = document.getElementById(inputId);
    const button = document.getElementById(buttonId);
    const handler = (event) => {
        if ((event.keyCode && event.keyCode === 13) || event.type === 'click') {
            const value = input.value.trim();
            if (value) {
                askChatBot(value);
                input.value = '';
            }
        }
    };
    button.onclick = handler;
    input.onkeyup = handler;
}

wireInput('chatbotInput', 'submitButton');
wireInput('chatbotInput2', 'submitButton2');

function appendMessage(className, text) {
    const bubble = document.createElement('div');
    bubble.className = `chat-message ${className}`;
    bubble.innerText = text;
    chatbotOutput.appendChild(bubble);
    chatbotOutput.scrollTop = chatbotOutput.scrollHeight;
    return bubble;
}

function askChatBot(userInput) {
    screen1.classList.add('hidden');
    screen2.classList.remove('hidden');
    appendMessage('user', userInput);
    const thinkingBubble = appendMessage('assistant thinking', 'thinking...');

    const requestHistory = history;

    const myRequest = new Request('/api/chat', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
        },
        body: JSON.stringify({ message: userInput, history: requestHistory })
    });

    fetch(myRequest)
        .then(function(response) {
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            return response.json();
        })
        .then(function(data) {
            if (data.status === 'success') {
                thinkingBubble.className = 'chat-message assistant';
                thinkingBubble.innerText = data.response;
                history = requestHistory.concat(
                    { role: 'user', content: userInput },
                    { role: 'assistant', content: data.response }
                );
                renderWinChart(data.team, data.chart);
                renderLeaders(data.team, data.leaders);
            } else {
                thinkingBubble.className = 'chat-message error';
                thinkingBubble.innerText = data.error || 'Sorry, something went wrong.';
            }
        })
        .catch((err) => {
            console.error('Error:', err);
            thinkingBubble.className = 'chat-message error';
            thinkingBubble.innerText = 'Sorry, I\'m having trouble connecting. Please try again.';
        });
}
