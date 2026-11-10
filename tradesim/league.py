"""Load the built league data and CBA config.

The League object is the "state" a trade is checked against: who is on which
team, each team's salary, which picks and exceptions each team holds, and any
hard caps. apply_trade() in checker.py returns a NEW League, so trades can be
checked one after another without changing the original.
"""
import copy
import json
import os
from functools import lru_cache

from tradesim.names import slug

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
        self.as_of = data.get("as_of")            # oldest roster / contract / cap / stats source
        self.sources_as_of = data.get("sources_as_of", {})
        # Players this team has traded away during this run of trades
        # (team -> set of player ids), for the re-acquire rule.
        self.traded_away = {code: set() for code in self.teams}

    @classmethod
    def load(cls, path=LEAGUE_PATH):
        with open(path) as f:
            return cls(json.load(f))

    def player_id(self, ref):
        """Player key (NBA ID as a string) for an NBA ID, an old name-based id
        ("derrick-white", used before players were keyed by NBA ID, e.g. in trades saved on a
        phone) or an exact name. None if unknown or two players share the name."""
        ref = str(ref)
        if ref in self.players:
            return ref
        if "_by_slug" not in self.__dict__:
            by_slug = {}
            for pid, p in self.players.items():
                by_slug.setdefault(slug(p["name"]), []).append(pid)
            self._by_slug = {k: v[0] for k, v in by_slug.items() if len(v) == 1}
        return self._by_slug.get(slug(ref.replace("-", " ")))


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


@lru_cache(maxsize=1)
def _default_league():
    return League.load()


def player_id(ref):
    """League.player_id on the built league (for scripts and tests)."""
    return _default_league().player_id(ref)
