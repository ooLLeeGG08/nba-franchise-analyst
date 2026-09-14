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

    async function fetchTeamDashboard(team) {
        const response = await fetch(`/api/team/${encodeURIComponent(team)}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchTeamComparison(teamA, teamB) {
        const response = await fetch(`/api/team/${encodeURIComponent(teamA)}/vs/${encodeURIComponent(teamB)}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchLeaders() {
        const response = await fetch('/api/leaders');
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    async function fetchPlayerView(name) {
        const response = await fetch(`/api/player/${encodeURIComponent(name)}`);
        if (!response.ok) throw new Error(`HTTP error ${response.status}`);
        return response.json();
    }

    return { sendChatMessage, fetchTeams, fetchTeamDashboard, fetchTeamComparison, fetchLeaders, fetchPlayerView };
})();
