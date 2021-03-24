import logging
import pymongo

from node import Node
from model import Puzzle
from typing import List

class Server:

    def __init__(self, logger: logging.Logger, uri: str, version: int) -> None:
        self.myclient = pymongo.MongoClient(uri)
        self.mydb = self.myclient["genpuzzles"]
        self.col = self.mydb["puz"]
        self.poscol = self.mydb["puzpos"]
        self.version = version

    def is_seen(self, game_id: str) -> bool:
        return self.col.count_documents({"game_id": game_id}, limit = 1) > 0

    def set_seen(self, node: Node) -> None:
        self.poscol.insert_one({"_id": node.current_board.sfen()})

    def is_seen_pos(self, node: Node) -> bool:
        return self.poscol.count_documents({"_id": node.current_board.sfen()}, limit = 1) > 0

    def post(self, game_id: str, puzzles: List[Puzzle]) -> None:
        for puzzle in puzzles:
            parent = puzzle.node.parent
            assert parent
            json = {
                'game_id': game_id,
                'fen': parent.current_board.sfen(),
                'ply': parent.current_board.move_number - 1,
                'moves': [puzzle.node.move().usi()] + list(map(lambda m : m.usi(), puzzle.moves)),
                'cp': puzzle.cp,
                'generator_version': self.version,
            }
            self.col.insert_one(json)
            print(json, flush=True)
        return None