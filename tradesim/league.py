"""Load the built league data and CBA config.

The League object is the "state" a trade is checked against: who is on which
team, each team's salary, which picks and exceptions each team holds, and any
hard caps. apply_trade() in checker.py returns a NEW League, so trades can be
checked one after another without changing the original.
"""
import copy
import json
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEAGUE_PATH = os.path.join(ROOT, "data", "2026_27", "league.json")
CBA_PATH = os.path.join(ROOT, "config", "cba_2026_27.json")


def load_cba(path=CBA_PATH):
    with open(path) as f:
        return json.load(f)


class League:
    def __init__(self, data):
        self.teams = data["teams"]
        self.players = data["players"]
        self.picks = data["picks"]
        self.trade_exceptions = data["trade_exceptions"]
        self.calendar = data.get("calendar", [])
        # Players this team has traded away during this run of trades
        # (team -> set of player ids), for the re-acquire rule.
        self.traded_away = {code: set() for code in self.teams}

    @classmethod
    def load(cls, path=LEAGUE_PATH):
        with open(path) as f:
            return cls(json.load(f))

    def copy(self):
        return copy.deepcopy(self)

    def roster(self, team):
        """Standard-contract players currently on `team` (excludes waived players)."""
        return [p for p in self.players.values() if p["team"] == team and p["on_roster"]]

    def picks_held(self, team):
        """Pick entries `team` can trade (own, acquired, frozen, conditional)."""
        return [p for p in self.picks.values() if p["holder"] == team and p["kind"] != "conveyed"]

    def first_round_by_year(self, team):
        out = {}
        for p in self.picks_held(team):
            if p["round"] == 1:
                out.setdefault(p["year"], []).append(p)
        return out

    def exceptions_of(self, team):
        return [e for e in self.trade_exceptions.values() if e["team"] == team and e["amount"] > 0]
