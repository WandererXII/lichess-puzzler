from node import Node
from shogi import Move
from score import Score, Mate, Cp
from dataclasses import dataclass
from typing import Tuple, List, Optional

@dataclass
class Puzzle:
    node: Node
    moves: List[Move]
    cp: int

@dataclass
class Line:
    nb: Tuple[int, int]
    letter: str
    password: str

@dataclass
class EngineMove:
    move: Move
    score: Score

@dataclass
class NextMovePair:
    node: Node
    winner: bool
    best: EngineMove
    second: Optional[EngineMove]
