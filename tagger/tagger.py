import pymongo
import logging
import argparse
from multiprocessing import Pool
from datetime import datetime
from chess import Move, Board
from chess.pgn import Game, GameNode
from typing import List, Tuple, Dict, Any
from model import Puzzle, TagKind
from cook import cook

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-4s %(message)s', datefmt='%m/%d %H:%M')
logger.setLevel(logging.INFO)

def read(doc) -> Puzzle:
    board = Board(doc["fen"])
    node: GameNode = Game.from_board(board)
    for uci in doc["line"].split(' '):
        move = Move.from_uci(uci)
        node = node.add_main_variation(move)
    return Puzzle(doc["_id"], node.game())

if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog='tagger.py', description='automatically tags lichess puzzles')
    parser.add_argument("--verbose", "-v", help="increase verbosity", action="count")
    args = parser.parse_args()
    if args.verbose == 1:
        logger.setLevel(logging.DEBUG)
    mongo = pymongo.MongoClient()
    db = mongo['puzzler']
    play_coll = db['puzzle2_puzzle']
    round_coll = db['puzzle2_round']
    nb = 0

    def tags_of(doc) -> Tuple[str, List[TagKind]]:
        puzzle = read(doc)
        return puzzle.id, cook(puzzle)

    def process_batch(batch: List[Dict[str, Any]]):
        for id, tags in pool.imap_unordered(tags_of, batch):
            result = round_coll.update_one({
                "_id": f"lichess:{id}"
            }, {
                "$set": {
                    "p": id,
                    "d": datetime.now(),
                    "w": 10,
                    "t": [f"+{t}" for t in tags]
                }
            }, upsert = True);
            play_coll.update_one({"_id":id},{"$set":{"dirty":True}})

    with Pool(processes=16) as pool:
        batch: List[Dict[str, Any]] = []
        for doc in play_coll.find():
            id = doc["_id"]
            if round_coll.count_documents({"_id":f"lichess:{id}"}) > 0:
                continue
            if len(batch) < 256:
                batch.append(doc)
                continue
            process_batch(batch)
            nb += len(batch)
            if nb % 1024 == 0:
                logger.info(nb)
            batch = []
        process_batch(batch)
