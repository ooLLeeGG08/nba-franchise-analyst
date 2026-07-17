import os
import traceback

from dotenv import load_dotenv
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

load_dotenv()

from llm import answer_question
from rag import get_team_leaders, get_team_records, resolve_team

app = Flask(__name__)
CORS(app)


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

        return jsonify({
            'response': bot_response,
            'status': 'success',
            'team': team,
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


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    app.run(host='0.0.0.0', port=port, debug=False)
