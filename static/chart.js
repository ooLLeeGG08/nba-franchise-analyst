let winChartInstance = null;

function renderWinChart(team, records) {
    const section = document.getElementById('winChartSection');
    if (!team || !records) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');
    document.getElementById('winChartTitle').innerText = `${team} Win Totals (2015-2026)`;

    const seasons = Object.keys(records);
    const wins = seasons.map((s) => records[s]);

    if (winChartInstance) {
        winChartInstance.destroy();
    }

    winChartInstance = new Chart(document.getElementById('winChart'), {
        type: 'line',
        data: {
            labels: seasons,
            datasets: [{
                label: `${team} wins`,
                data: wins,
                borderColor: '#667eea',
                backgroundColor: '#667eea',
                fill: false,
                tension: 0.2,
            }],
        },
        options: {
            responsive: true,
            scales: { y: { beginAtZero: true, title: { display: true, text: 'Wins' } } },
        },
    });
}

function renderLeaders(team, leaders) {
    const section = document.getElementById('leadersSection');
    if (!team || !leaders) {
        section.classList.add('hidden');
        return;
    }
    section.classList.remove('hidden');

    const categories = { ppg: 'leadersPpg', apg: 'leadersApg', rpg: 'leadersRpg', spg: 'leadersSpg' };
    Object.entries(categories).forEach(([key, listId]) => {
        const list = document.getElementById(listId);
        list.innerHTML = '';
        (leaders[key] || [])
            .slice()
            .sort((a, b) => b.value - a.value)
            .slice(0, 5)
            .forEach((entry) => {
                const li = document.createElement('li');
                li.innerText = `${entry.player} — ${entry.value}`;
                list.appendChild(li);
            });
    });
}
