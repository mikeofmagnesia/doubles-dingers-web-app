from dataclasses import dataclass, field


@dataclass
class PlayerStats:
    name: str
    br_id: str
    group: str = "Wildcard"
    doubles: int = 0
    homers: int = 0
    games_played: int = 0

    # Set after sorting all players by total (descending)
    rank: int | None = None

    # Loaded from the Player History sheet before writing
    prev_rank: int | None = None
    prev_doubles: int | None = None
    prev_homers: int | None = None

    @property
    def total(self) -> int:
        return self.doubles + self.homers

    @property
    def prev_total(self) -> int | None:
        if self.prev_doubles is None or self.prev_homers is None:
            return None
        return self.prev_doubles + self.prev_homers

    @property
    def rank_change(self) -> int | None:
        """Positive = moved up in rankings (better). Negative = moved down."""
        if self.prev_rank is None or self.rank is None:
            return None
        return self.prev_rank - self.rank

    @property
    def total_change(self) -> int | None:
        if self.prev_total is None:
            return None
        return self.total - self.prev_total

    @property
    def per_game(self) -> float:
        if self.games_played == 0:
            return 0.0
        return round(self.total / self.games_played, 3)


@dataclass
class Team:
    owner: str
    team_name: str
    player_ids: list[str]
    players: list[PlayerStats] = field(default_factory=list)

    # Set after sorting all teams by total (descending)
    rank: int | None = None

    # Loaded from the Team History sheet before writing
    prev_rank: int | None = None
    prev_doubles: int | None = None
    prev_homers: int | None = None

    @property
    def doubles(self) -> int:
        return sum(p.doubles for p in self.players)

    @property
    def homers(self) -> int:
        return sum(p.homers for p in self.players)

    @property
    def total(self) -> int:
        return self.doubles + self.homers

    @property
    def prev_total(self) -> int | None:
        if self.prev_doubles is None or self.prev_homers is None:
            return None
        return self.prev_doubles + self.prev_homers

    @property
    def rank_change(self) -> int | None:
        """Positive = moved up in rankings (better). Negative = moved down."""
        if self.prev_rank is None or self.rank is None:
            return None
        return self.prev_rank - self.rank

    @property
    def total_change(self) -> int | None:
        if self.prev_total is None:
            return None
        return self.total - self.prev_total
