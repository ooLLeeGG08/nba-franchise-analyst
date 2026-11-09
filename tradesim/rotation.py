"""Rotations: who plays how many minutes, and what happens when players move or sit.

Positions use three buckets, G=0, F=1, C=2. A listed position like "F-C" counts as both
F and C. Distance between two players = closest buckets (same = 0, adjacent = 1, G to
C = 2).

Full-strength rotation (everyone healthy)
    Each player gets his minutes per game played (from tradesim.ratings). If the roster
    adds up to more than 240, the deepest bench (fewest minutes) is trimmed first, so the
    real rotation is kept; if less, the next players up get more.

Scenario changes (one team at a time, from its final roster)
    Departing players' minutes form a pool. Each incoming player (most minutes first) takes
    his usual minutes from that pool first (same-position departures first). If the pool
    runs out, the rest is taken from the team's lowest-impact players, same position first,
    then adjacent, then any. Any pool left over goes to the next players up, as below.
    (Handling departures and arrivals separately sent a traded star's minutes to the
    existing guards first, so a team could get better by losing him.)

Outgoing or absent player
    His minutes go to the "next players up" on the depth chart: teammates at the same
    position first, then adjacent, then any; within a group, the player just below him in
    minutes first (his backup), then further down the bench; players who already play more
    than him come last. Nobody gets more than `max_extra_minutes` on top of his usual
    minutes, or more than `max_mpg` in total. (A first version gave the minutes to the
    highest-impact teammate, which had stars playing 42 minutes whenever anyone sat.)

Absence cost
    For each player j, `delta[j]` = how much team strength drops in a game he misses:
        (his minutes x his impact - sum of minutes given to each replacement x their impact) / 48
    The simulator subtracts delta[j] in every game he sits. With several players out, the
    costs are added (a simplification: in reality their replacements would overlap).

Diminishing returns (a simplification, default mild)
    If a team's top-3 players add more than `threshold` points (impact x minutes / 48),
    the excess is reduced by `haircut` (e.g. 15%): stars share one ball.
"""
from tradesim.ratings import load_ratings

BUCKET = {"G": 0, "F": 1, "C": 2}


def buckets(position):
    found = {BUCKET[ch] for ch in (position or "") if ch in BUCKET}
    return found or {1}


def distance(pos_a, pos_b):
    return min(abs(a - b) for a in buckets(pos_a) for b in buckets(pos_b))


class Rotation:
    """One team's rotation. `players`: list of player dicts (id, name, position)."""

    def __init__(self, code, players, cfg, ratings=None):
        self.code = code
        self.cfg = cfg
        self.rc = cfg["rotation"]
        ratings = ratings or load_ratings()
        rated = ratings["players"]
        self.residual = ratings["team_residuals"][code]["residual"]
        self.players = {p["id"]: {"id": p["id"], "name": p["name"], "position": p.get("position"),
                                  "impact": rated[p["id"]]["impact"], "se": rated[p["id"]]["se"],
                                  "usual": rated[p["id"]]["mpg_when_playing"],
                                  "availability": rated[p["id"]]["availability"]}
                        for p in players}
        self.minutes = self._full_strength()

    # --- building blocks -----------------------------------------------------------------

    def _ceiling(self, pid):
        p = self.players[pid]
        return min(self.rc["max_mpg"], p["usual"] + self.rc["max_extra_minutes"])

    def _full_strength(self):
        total = self.cfg["minutes"]["team_minutes"]
        minutes = {pid: min(p["usual"], self.rc["max_mpg"]) for pid, p in self.players.items()}
        excess = sum(minutes.values()) - total
        for pid in sorted(minutes, key=lambda k: (minutes[k], k)):  # deepest bench first
            if excess <= 1e-9:
                break
            cut = min(minutes[pid], excess)
            minutes[pid] -= cut
            excess -= cut
        if excess < -1e-9:
            minutes = self._give(minutes, -excess, position=None, exclude=set())
        return minutes

    def _give(self, minutes, amount, position, exclude, below=None):
        """Hand `amount` minutes to the next players up, up to each player's ceiling:
        same position first, then adjacent, then any; within a group, players below `below`
        minutes in order (closest first), then those above. Returns new minutes."""
        minutes = dict(minutes)
        below = float("inf") if below is None else below

        def depth(k):
            m = minutes.get(k, 0.0)
            return (0, -m) if m < below else (1, m)

        order = sorted((pid for pid in self.players if pid not in exclude),
                       key=lambda k: (distance(self.players[k]["position"], position) if position else 0,
                                      depth(k), k))
        for pid in order:
            if amount <= 1e-9:
                break
            room = max(self._ceiling(pid) - minutes[pid], 0)
            add = min(room, amount)
            minutes[pid] += add
            amount -= add
        if amount > 1e-9:  # everyone at his ceiling: spread the rest evenly
            others = [pid for pid in self.players if pid not in exclude]
            for pid in others:
                minutes[pid] += amount / len(others)
        return minutes

    # --- scenario changes ------------------------------------------------------------------

    def change(self, outgoing, incoming, ratings):
        """Apply a team's net roster change: `outgoing` player ids leave, `incoming` player
        dicts arrive. See the module docstring for the rule."""
        pools = []  # [position, minutes] of departing players
        for pid in outgoing:
            pools.append([self.players[pid]["position"], self.minutes.pop(pid)])
            del self.players[pid]
        minutes = dict(self.minutes)
        for player in sorted(incoming, key=lambda p: -ratings["players"][p["id"]]["mpg_when_playing"]):
            pid, rated = player["id"], ratings["players"][player["id"]]
            self.players[pid] = {"id": pid, "name": player["name"], "position": player.get("position"),
                                 "impact": rated["impact"], "se": rated["se"], "usual": rated["mpg_when_playing"],
                                 "availability": rated["availability"]}
            need = min(rated["mpg_when_playing"], self.rc["max_mpg"])
            minutes[pid] = need
            for pool in sorted(pools, key=lambda pl: distance(pl[0], player.get("position"))):
                take = min(pool[1], need)
                pool[1] -= take
                need -= take
            order = sorted((k for k in minutes if k != pid and minutes[k] > 0 and k not in {i["id"] for i in incoming}),
                           key=lambda k: (distance(self.players[k]["position"], player.get("position")),
                                          self.players[k]["impact"], k))
            for k in order:
                if need <= 1e-9:
                    break
                cut = min(minutes[k], need)
                minutes[k] -= cut
                need -= cut
        for position, left in pools:
            if left > 1e-9:
                minutes = self._give(minutes, left, position, exclude=set(), below=left)
        self.minutes = minutes

    # --- strength ------------------------------------------------------------------------------

    def absence_transfer(self, pid):
        """{teammate: minutes gained} in a game `pid` misses (his minutes go to the next players up)."""
        mine = self.minutes[pid]
        if mine <= 0:
            return {}
        after = self._give({k: v for k, v in self.minutes.items() if k != pid}, mine,
                           self.players[pid]["position"], exclude={pid}, below=mine)
        return {k: after[k] - self.minutes[k] for k in after if after[k] - self.minutes[k] > 1e-12}

    def absence_weights(self, pid):
        """Absence cost as weights on impacts: cost = sum(weight[k] x impact[k]). Lets the
        simulator recompute the cost for each simulated set of player impacts."""
        weights = {pid: self.minutes[pid] / 48} if self.minutes[pid] > 0 else {}
        for k, gained in self.absence_transfer(pid).items():
            weights[k] = weights.get(k, 0.0) - gained / 48
        return weights

    def absence_cost(self, pid):
        """Strength lost in a game `pid` misses, at the players' rated impacts."""
        return sum(w * self.players[k]["impact"] for k, w in self.absence_weights(pid).items())

    def diminishing_returns(self):
        dr = self.rc["diminishing_returns"]
        contributions = sorted((self.players[k]["impact"] * m / 48 for k, m in self.minutes.items()), reverse=True)
        top3 = sum(c for c in contributions[:3] if c > 0)
        return dr["haircut"] * max(top3 - dr["threshold"], 0.0)

    def full_strength(self):
        """Strength with everyone available, after the diminishing-returns haircut."""
        players = sum(self.players[k]["impact"] * m / 48 for k, m in self.minutes.items())
        return players + self.residual - self.diminishing_returns()

    def expected_strength(self):
        """Average strength over a season, counting each player's expected missed games."""
        return self.full_strength() - sum((1 - self.players[k]["availability"]) * self.absence_cost(k)
                                          for k in self.players)

    def breakdown(self):
        return sorted(({"id": k, "name": self.players[k]["name"], "position": self.players[k]["position"],
                        "impact": self.players[k]["impact"], "minutes": round(m, 1),
                        "availability": self.players[k]["availability"],
                        "absence_cost": round(self.absence_cost(k), 2)}
                       for k, m in self.minutes.items()), key=lambda b: -b["minutes"])


def final_rosters(league, moves):
    """{team: set of player ids} after applying `moves` in order."""
    team_of = {pid: p["team"] for pid, p in league.players.items() if p["on_roster"]}
    for m in moves:
        if team_of.get(m["player"]) != m["from"]:
            raise ValueError(f"{m['player']} is not on {m['from']}")
        team_of[m["player"]] = m["to"]
    rosters = {code: set() for code in league.teams}
    for pid, code in team_of.items():
        rosters[code].add(pid)
    return rosters


def apply_moves(league, moves, cfg, ratings=None):
    """Rotations for every team after a list of moves [{"player", "from", "to"}], applied in
    order. Only teams whose final roster differs are changed; a move to the player's own
    team changes nothing."""
    ratings = ratings or load_ratings()
    rotations = {code: Rotation(code, league.roster(code), cfg, ratings) for code in league.teams}
    if not moves:
        return rotations
    final = final_rosters(league, moves)
    for code, rotation in rotations.items():
        before = set(rotation.players)
        outgoing, incoming = before - final[code], final[code] - before
        if outgoing or incoming:
            rotation.change(sorted(outgoing), [league.players[pid] for pid in sorted(incoming)], ratings)
    return rotations
