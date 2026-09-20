const Api = (() => {
    async function sendChatMessage(message, history) {
        const response = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ message, history }),
        });
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchTeams() {
        const response = await fetch('/api/teams');
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchTeamDashboard(team, season) {
        const query = season ? `?season=${encodeURIComponent(season)}` : '';
        const response = await fetch(`/api/team/${encodeURIComponent(team)}${query}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchTeamComparison(teamA, teamB, season) {
        const query = season ? `?season=${encodeURIComponent(season)}` : '';
        const response = await fetch(`/api/team/${encodeURIComponent(teamA)}/vs/${encodeURIComponent(teamB)}${query}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchLeaders() {
        const response = await fetch('/api/leaders');
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchPlayerView(name, season) {
        const query = season ? `?season=${encodeURIComponent(season)}` : '';
        const response = await fetch(`/api/player/${encodeURIComponent(name)}${query}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchPlayerComparison(nameA, nameB, season) {
        const query = season ? `?season=${encodeURIComponent(season)}` : '';
        const response = await fetch(`/api/player/${encodeURIComponent(nameA)}/vs/${encodeURIComponent(nameB)}${query}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    return {
        sendChatMessage, fetchTeams, fetchTeamDashboard, fetchTeamComparison,
        fetchLeaders, fetchPlayerView, fetchPlayerComparison,
    };
})();
