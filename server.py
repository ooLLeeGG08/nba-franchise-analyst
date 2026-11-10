import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

from llm import answer_question
from rag import (
    TEAM_FACTS_GENERATED_AT,
    available_seasons,
    default_team_season,
    explicit_season,
    get_all_teams,
    get_league_leaders,
    leaders_season,
    get_player_view,
    get_team_advanced_stats,
    get_team_branding,
    get_team_knowledge,
    get_team_records,
    get_team_recent_games,
    get_team_roster,
    get_team_season_leaders,
    get_team_season_snapshot,
    is_comparison_query,
    is_trade_query,
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
    season = season if season in available_seasons() else default_team_season(team_key)
    return {
        "team": team_key,
        "season": season,
        "latestSeason": latest_season(),
        "availableSeasons": available_seasons(),
        "branding": get_team_branding(team_key),
        "knowledge": get_team_knowledge(team_key),
        "records": get_team_records(team_key),
        "advancedStats": get_team_advanced_stats(team_key),
        "leaders": get_team_season_leaders(team_key, season),
        "recentGames": get_team_recent_games(team_key, season),
        "seasonSnapshot": get_team_season_snapshot(team_key, season),
        "roster": get_team_roster(team_key, season),
    }


@app.route('/')
def index():
    """Trade simulator (mobile-first single-page app)."""
    return send_from_directory('static/sim', 'index.html')


@app.route('/analyst')
def analyst_index():
    """The original chat-based franchise analyst, kept while the trade simulator is built."""
    return send_from_directory('static', 'index.html')


# --- trade simulator API ----------------------------------------------------------------------

_SIM = {}


def _sim():
    """League, CBA config and simulation engine, loaded once (the baseline comes from the
    on-disk cache when the data hasn't changed)."""
    if not _SIM:
        from tradesim.engine import Engine
        from tradesim.games import load_schedule_2026_27
        from tradesim.league import League, load_cba
        from tradesim.model import load_sim_config
        league, cfg = League.load(), load_sim_config()
        engine = Engine(league, load_schedule_2026_27(), cfg)
        engine.baseline()
        _SIM.update(league=league, cba=load_cba(), cfg=cfg, engine=engine)
    return _SIM


@app.route('/api/sim/status')
def sim_status():
    from datetime import date
    from tradesim.analysis import data_status
    s = _sim()
    return jsonify(data_status(s["league"], s["cfg"], date.today()))


@app.route('/api/sim/teams')
def sim_teams():
    from tradesim.analysis import teams_overview
    return jsonify({"conferences": teams_overview(_sim()["engine"])})


@app.route('/api/sim/trade/assets/<code>')
def sim_trade_assets(code):
    from tradesim.teams import TEAM_INFO
    from tradesim.trade_api import team_assets
    code = code.upper()
    if code not in TEAM_INFO:
        return jsonify({"error": f"Unknown team {code}"}), 404
    s = _sim()
    return jsonify(team_assets(code, s["league"], s["cba"]))


@app.route('/api/sim/trade/check', methods=['POST'])
def sim_trade_check():
    from tradesim.trade_api import BadTrade, check
    s = _sim()
    try:
        return jsonify(check(request.get_json(silent=True), s["league"], s["cba"]))
    except BadTrade as err:
        return jsonify({"error": str(err)}), 400


@app.route('/api/sim/team/<code>/suggestions')
def sim_suggestions(code):
    from datetime import date
    from tradesim.ai import NameIndex, get_llm
    from tradesim.suggest import cached_suggest
    from tradesim.teams import TEAM_INFO
    code = code.upper()
    if code not in TEAM_INFO:
        return jsonify({"error": f"Unknown team {code}"}), 404
    s = _sim()
    if "names" not in s:
        s["names"] = NameIndex(s["league"].players, s["engine"].ratings["players"])
    return jsonify(cached_suggest(code, s["engine"], s["league"], s["cba"], date.today(), get_llm(), s["names"]))


@app.route('/api/sim/sequence/check', methods=['POST'])
def sim_sequence_check():
    from datetime import date
    from tradesim.sequence_api import check_sequence
    from tradesim.trade_api import BadTrade
    s = _sim()
    try:
        out = check_sequence(request.get_json(silent=True), s["league"], s["cba"], date.today())
    except BadTrade as err:
        return jsonify({"error": str(err)}), 400
    out.pop("working")
    out.pop("final_league")
    return jsonify(out)


@app.route('/api/sim/sequence/plan', methods=['POST'])
def sim_sequence_plan():
    from datetime import date
    from tradesim.ai import NameIndex, get_llm
    from tradesim.sequence_api import plan
    from tradesim.trade_api import BadTrade
    s = _sim()
    if "names" not in s:
        s["names"] = NameIndex(s["league"].players, s["engine"].ratings["players"])
    try:
        return jsonify(plan(request.get_json(silent=True), s["league"], s["cba"], s["engine"], date.today(),
                            get_llm(), s["names"]))
    except BadTrade as err:
        return jsonify({"error": str(err)}), 400


@app.route('/api/sim/sequence/simulate', methods=['POST'])
def sim_sequence_simulate():
    from datetime import date
    from tradesim.ai import NameIndex, get_llm
    from tradesim.sequence_api import simulate_sequence
    from tradesim.trade_api import BadTrade
    s = _sim()
    if "names" not in s:
        s["names"] = NameIndex(s["league"].players, s["engine"].ratings["players"])
    try:
        return jsonify(simulate_sequence(request.get_json(silent=True), s["league"], s["cba"], s["engine"],
                                         date.today(), get_llm(), s["names"]))
    except BadTrade as err:
        return jsonify({"error": str(err)}), 400


@app.route('/api/sim/players/resolve')
def sim_resolve_player():
    """Turn a typed name into database players: exact, ambiguous (the user picks), or none."""
    from tradesim.ai import NameIndex
    s = _sim()
    if "names" not in s:
        s["names"] = NameIndex(s["league"].players, s["engine"].ratings["players"])
    q = request.args.get("q", "")
    r = s["names"].resolve(q)
    r["players"] = [{"id": pid, "name": s["league"].players[pid]["name"], "team": s["league"].players[pid]["team"]}
                    for pid in r["candidates"]]
    return jsonify(r)


@app.route('/api/sim/team/<code>')
def sim_team(code):
    from tradesim.analysis import team_analysis
    from tradesim.teams import TEAM_INFO
    code = code.upper()
    if code not in TEAM_INFO:
        return jsonify({"error": f"Unknown team {code}"}), 404
    s = _sim()
    return jsonify(team_analysis(code, s["engine"], s["league"], s["cba"]))


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
            'trade': is_trade_query(message),
            'season': explicit_season(message, history),
            'chart': get_team_records(team) if team else None,
            'leaders': get_team_season_leaders(team, default_team_season(team)) if team else None,
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


@app.route('/api/meta')
def meta():
    # Powers the UI's "Data through {season} season - facts as of {date}"
    # label. factsAsOf is team_facts.json's own fetch timestamp (championships
    # and current head coaches, live via nba_api -- see fetch_team_facts.py),
    # not the stats data's freshness, since those can be refreshed separately.
    return jsonify({
        'dataThroughSeason': latest_season(),
        'factsAsOf': TEAM_FACTS_GENERATED_AT,
    })


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
    return jsonify({
        'season': leaders_season(),
        'latestSeason': latest_season(),
        **{category: get_league_leaders(category) for category in categories},
    })


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
