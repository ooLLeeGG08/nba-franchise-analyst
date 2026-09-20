import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

from llm import answer_question
from rag import (
    available_seasons,
    explicit_season,
    get_all_teams,
    get_league_leaders,
    get_player_view,
    get_team_advanced_stats,
    get_team_branding,
    get_team_knowledge,
    get_team_leaders,
    get_team_records,
    get_team_recent_games,
    get_team_roster,
    get_team_season_snapshot,
    is_comparison_query,
    latest_season,
    mentioned_players,
    mentioned_teams,
    resolve_player,
    resolve_team,
)

app = Flask(__name__)
CORS(app)

_TEAM_KEY_LOOKUP = {t["key"].lower(): t["key"] for t in get_all_teams()}


def _resolve_team_key(raw):
    return _TEAM_KEY_LOOKUP.get(raw.lower())


def _requested_season():
    season = request.args.get('season')
    return season if season in available_seasons() else None


def _team_dashboard_bundle(team_key, season=None):
    season = season if season in available_seasons() else latest_season()
    return {
        "team": team_key,
        "season": season,
        "availableSeasons": available_seasons(),
        "branding": get_team_branding(team_key),
        "knowledge": get_team_knowledge(team_key),
        "records": get_team_records(team_key),
        "advancedStats": get_team_advanced_stats(team_key),
        "leaders": get_team_leaders(team_key),
        "recentGames": get_team_recent_games(team_key, season),
        "seasonSnapshot": get_team_season_snapshot(team_key, season),
        "roster": get_team_roster(team_key, season),
    }


@app.route('/')
def index():
    return send_from_directory('static', 'index.html')


@app.route('/<path:filename>')
def static_files(filename):
    return send_from_directory('static', filename)


@app.route('/api/chat', methods=['POST'])
def chat():
    try:
        data = request.get_json()
        if not data or 'message' not in data:
            return jsonify({'error': 'No message provided'}), 400

        message = data['message']
        history = data.get('history') or []
        bot_response = answer_question(message, history)

        team = resolve_team(message, history)
        teams = mentioned_teams(message) or ([team] if team else [])
        player = resolve_player(message, history)
        players = mentioned_players(message) or ([player] if player else [])

        return jsonify({
            'response': bot_response,
            'status': 'success',
            'team': team,
            'teams': teams,
            'player': player,
            'players': players,
            'comparison': is_comparison_query(message),
            'season': explicit_season(message, history),
            'chart': get_team_records(team) if team else None,
            'leaders': get_team_leaders(team) if team else None,
        })

    except Exception as e:
        print(f"Error: {e}")
        traceback.print_exc()
        return jsonify({
            'error': 'Sorry, I encountered an error processing your request.',
            'status': 'error'
        }), 500


@app.route('/api/teams')
def teams_list():
    return jsonify(get_all_teams())


@app.route('/api/team/<team>')
def team_dashboard(team):
    team_key = _resolve_team_key(team)
    if not team_key:
        return jsonify({'error': f'Unknown team: {team}'}), 404
    return jsonify(_team_dashboard_bundle(team_key, request.args.get('season')))


@app.route('/api/team/<team>/vs/<other>')
def team_comparison(team, other):
    team_key = _resolve_team_key(team)
    other_key = _resolve_team_key(other)
    if not team_key or not other_key:
        unknown = team if not team_key else other
        return jsonify({'error': f'Unknown team: {unknown}'}), 404
    season = _requested_season()
    return jsonify({
        'teamA': _team_dashboard_bundle(team_key, season),
        'teamB': _team_dashboard_bundle(other_key, season),
    })


@app.route('/api/leaders')
def leaders():
    categories = ['ppg', 'apg', 'rpg', 'spg', 'pie']
    return jsonify({category: get_league_leaders(category) for category in categories})


@app.route('/api/player/<name>')
def player_view(name):
    view = get_player_view(name, _requested_season())
    if not view:
        return jsonify({'error': f'Unknown player: {name}'}), 404
    return jsonify(view)


@app.route('/api/player/<name>/vs/<other>')
def player_comparison(name, other):
    season = _requested_season()
    view_a, view_b = get_player_view(name, season), get_player_view(other, season)
    if not view_a or not view_b:
        unknown = name if not view_a else other
        return jsonify({'error': f'Unknown player: {unknown}'}), 404
    return jsonify({'playerA': view_a, 'playerB': view_b})


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
