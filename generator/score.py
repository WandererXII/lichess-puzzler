import shogi
import abc
from typing import Optional, Tuple


class Score(abc.ABC):
    @abc.abstractmethod
    def mate(self) -> Optional[int]:
        ...

    @abc.abstractmethod
    def score(self) -> Optional[int]:
        ...

    def is_mate(self) -> bool:
        return self.mate() is not None

    @abc.abstractmethod
    def __str__(self) -> str:
        ...

    @abc.abstractmethod
    def __neg__(self) -> 'Score':
        ...

    @abc.abstractmethod
    def __pos__(self) -> 'Score':
        ...

    @abc.abstractmethod
    def __abs__(self) -> 'Score':
        ...

    def _score_tuple(self) -> Tuple[bool, bool, bool, int, Optional[int]]:
        mate = self.mate()
        return (
            isinstance(self, MateGivenType),
            mate is not None and mate > 0,
            mate is None,
            -(mate or 0),
            self.score(),
        )

    def __eq__(self, other: object) -> bool:
        if isinstance(other, Score):
            return self._score_tuple() == other._score_tuple()
        else:
            return NotImplemented

    def __lt__(self, other: object) -> bool:
        if isinstance(other, Score):
            return self._score_tuple() < other._score_tuple()
        else:
            return NotImplemented

    def __le__(self, other: object) -> bool:
        if isinstance(other, Score):
            return self._score_tuple() <= other._score_tuple()
        else:
            return NotImplemented

    def __gt__(self, other: object) -> bool:
        if isinstance(other, Score):
            return self._score_tuple() > other._score_tuple()
        else:
            return NotImplemented

    def __ge__(self, other: object) -> bool:
        if isinstance(other, Score):
            return self._score_tuple() >= other._score_tuple()
        else:
            return NotImplemented


class Mate(Score):
    def __init__(self, moves: int) -> None:
        self.moves = moves

    def mate(self) -> int:
        return self.moves

    def score(self) -> None:
        return None

    def __str__(self) -> str:
        return f"#+{self.moves}" if self.moves > 0 else f"#-{abs(self.moves)}"

    def __repr__(self) -> str:
        return "Mate({})".format(str(self).lstrip("#"))

    def __neg__(self) -> 'Mate':
        return Mate(-self.moves)

    def __pos__(self) -> 'Mate':
        return Mate(self.moves)

    def __abs__(self) -> 'Mate':
        return Mate(abs(self.moves))


class Cp(Score):
    def __init__(self, cp: int) -> None:
        self.cp = cp

    def mate(self) -> None:
        return None

    def score(self) -> int:
        return self.cp

    def __str__(self) -> str:
        return f"+{self.cp:d}" if self.cp > 0 else str(self.cp)

    def __repr__(self) -> str:
        return f"Cp({self})"

    def __neg__(self) -> 'Cp':
        return Cp(-self.cp)

    def __pos__(self) -> 'Cp':
        return Cp(self.cp)

    def __abs__(self) -> 'Cp':
        return Cp(abs(self.cp))


class MateGivenType(Score):
    """Winning mate score, equivalent to ``-Mate(0)``."""

    def mate(self) -> int:
        return 0

    def score(self) -> None:
        return None

    def __neg__(self) -> Mate:
        return Mate(0)

    def __pos__(self) -> 'MateGivenType':
        return self

    def __abs__(self) -> 'MateGivenType':
        return self

    def __repr__(self) -> str:
        return "MateGiven"

    def __str__(self) -> str:
        return "#+0"


MateGiven = MateGivenType()


class PovScore:
    def __init__(self, turn: shogi.COLORS, relative_score: Score):
        self.turn = turn
        self.relative_score = relative_score

    def pov(self, turn):
        return self.relative_score if self.turn == turn else -self.relative_score

    def sente(self) -> Score:
        return self.relative_score if self.turn == shogi.BLACK else -self.relative_score

    def gote(self) -> Score:
        return self.relative_score if self.turn == shogi.WHITE else -self.relative_score

    def is_mate(self) -> bool:
        return self.relative_score.is_mate()

    def score(self) -> Score:
        return self.relative_score

    def __str__(self) -> str:
        return str(self.relative_score)

