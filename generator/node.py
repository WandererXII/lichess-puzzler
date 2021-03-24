from shogi import Move, Board
from typing import Optional, List
from copy import deepcopy
from score import PovScore


class Node(object):
    def __init__(self, current_board: Board, parent: Optional['Node'] = None, root: Optional['Node'] = None):
        self.current_board = deepcopy(current_board)
        if root:
            self.root = root
        else:
            self.root = self

        self.parent = parent
        self.variations: List['Node'] = list()
        self.eval = None
        self.id = ""
        self.comment = ""

    def get_id(self) -> str:
        return self.root.id

    def add_variation(self, move: Move) -> 'Node':
        tmp = deepcopy(self.current_board)
        if self.root:
            root = self.root
        else:
            root = self
        tmp.push(move)
        variation = Node(tmp, parent = self, root = root)
        self.variations.append(variation)
        return variation

    def variation(self, index: int) -> 'Node':
        return self.variations[index]

    def board(self) -> Board:
        return deepcopy(self.current_board)
    
    def copy(self) -> 'Node':
        return deepcopy(self)
    
    def initial_position(self) -> str:
        return self.root.current_board.sfen()

    def is_end(self) -> bool:
        return len(self.variations) == 0

    def next(self) -> 'Node':
        return self.variations[0]
    
    def usi_moves(self) -> List[str]:
        return [m.usi() for m in self.current_board.move_stack]
    
    def move(self) -> Move:
        return self.current_board.move_stack[-1] if len(self.current_board.move_stack) > 0 else None
    
    def __str__(self) -> str:
        return str(self.current_board.sfen())

    def __repr__(self) -> str:
        return str(self.current_board.sfen())
