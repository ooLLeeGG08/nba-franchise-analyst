"""One row per team, mapping the different names/codes used by each data source.

- code: the app's own team id (standard NBA abbreviation)
- name: full name, as used by the contracts file and cap sheet
- short: key used by the older analyst data files (team_rosters.json etc.)
- bbref: Basketball-Reference code in the stats file
- picks: code used inside the draft-picks file
- picks_header: team header in the draft-picks file
"""

TEAMS = [
    # code, name, short, conference, bbref, picks, picks_header
    ("ATL", "Atlanta Hawks", "Hawks", "East", "ATL", "ATL", "ATLANTA HAWKS"),
    ("BOS", "Boston Celtics", "Celtics", "East", "BOS", "BOS", "BOSTON CELTICS"),
    ("BKN", "Brooklyn Nets", "Nets", "East", "BRK", "BRK", "BROOKLYN NETS"),
    ("CHA", "Charlotte Hornets", "Hornets", "East", "CHO", "CHA", "CHARLOTTE HORNETS"),
    ("CHI", "Chicago Bulls", "Bulls", "East", "CHI", "CHI", "CHICAGO BULLS"),
    ("CLE", "Cleveland Cavaliers", "Cavaliers", "East", "CLE", "CLE", "CLEVELAND CAVALIERS"),
    ("DAL", "Dallas Mavericks", "Mavericks", "West", "DAL", "DAL", "DALLAS MAVERICKS"),
    ("DEN", "Denver Nuggets", "Nuggets", "West", "DEN", "DEN", "DENVER NUGGETS"),
    ("DET", "Detroit Pistons", "Pistons", "East", "DET", "DET", "DETROIT PISTONS"),
    ("GSW", "Golden State Warriors", "Warriors", "West", "GSW", "GOS", "GOLDEN STATE WARRIORS"),
    ("HOU", "Houston Rockets", "Rockets", "West", "HOU", "HOU", "HOUSTON ROCKETS"),
    ("IND", "Indiana Pacers", "Pacers", "East", "IND", "IND", "INDIANA PACERS"),
    ("LAC", "Los Angeles Clippers", "Clippers", "West", "LAC", "LAC", "LOS ANGELES CLIPPERS"),
    ("LAL", "Los Angeles Lakers", "Lakers", "West", "LAL", "LAL", "LOS ANGELES LAKERS"),
    ("MEM", "Memphis Grizzlies", "Grizzlies", "West", "MEM", "MEM", "MEMPHIS GRIZZLIES"),
    ("MIA", "Miami Heat", "Heat", "East", "MIA", "MIA", "MIAMI HEAT"),
    ("MIL", "Milwaukee Bucks", "Bucks", "East", "MIL", "MIL", "MILWAUKEE BUCKS"),
    ("MIN", "Minnesota Timberwolves", "Timberwolves", "West", "MIN", "MIN", "MINNESOTA TIMBERWOLVES"),
    ("NOP", "New Orleans Pelicans", "Pelicans", "West", "NOP", "NOP", "NEW ORLEANS PELICANS"),
    ("NYK", "New York Knicks", "Knicks", "East", "NYK", "NYK", "NEW YORK KNICKS"),
    ("OKC", "Oklahoma City Thunder", "Thunder", "West", "OKC", "OKC", "OKLAHOMA CITY THUNDER"),
    ("ORL", "Orlando Magic", "Magic", "East", "ORL", "ORL", "ORLANDO MAGIC"),
    ("PHI", "Philadelphia 76ers", "76ers", "East", "PHI", "PHL", "PHILADELPHIA SIXERS"),
    ("PHX", "Phoenix Suns", "Suns", "West", "PHO", "PHX", "PHOENIX SUNS"),
    ("POR", "Portland Trail Blazers", "TrailBlazers", "West", "POR", "POR", "PORTLAND TRAIL BLAZERS"),
    ("SAC", "Sacramento Kings", "Kings", "West", "SAC", "SAC", "SACRAMENTO KINGS"),
    ("SAS", "San Antonio Spurs", "Spurs", "West", "SAS", "SAN", "SAN ANTONIO SPURS"),
    ("TOR", "Toronto Raptors", "Raptors", "East", "TOR", "TOR", "TORONTO RAPTORS"),
    ("UTA", "Utah Jazz", "Jazz", "West", "UTA", "UTH", "UTAH JAZZ"),
    ("WAS", "Washington Wizards", "Wizards", "East", "WAS", "WAS", "WASHINGTON WIZARDS"),
]

_FIELDS = ("code", "name", "short", "conference", "bbref", "picks", "picks_header")
TEAM_INFO = {row[0]: dict(zip(_FIELDS, row)) for row in TEAMS}


def _index(field):
    return {row[_FIELDS.index(field)]: row[0] for row in TEAMS}


CODE_BY_NAME = _index("name")
CODE_BY_SHORT = _index("short")
CODE_BY_BBREF = _index("bbref")
CODE_BY_PICKS = _index("picks")
CODE_BY_PICKS_HEADER = _index("picks_header")
# nba_api's "Traded from XXX" uses standard abbreviations, same as `code`.
