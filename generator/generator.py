import logging
import argparse
import shogi
import copy
import sys
import util
import bz2
from model import Puzzle, NextMovePair
from io import StringIO
from shogi import Move, Board
from typing import List, Optional, Union, Tuple
from util import get_next_move_pair, material_count, material_diff, is_up_in_material, win_chances, engine_filename
from server import Server
from engine import YaneuraOu, Limit
from score import Score, PovScore, Cp, Mate
from node import Node

version = 0

logger = logging.getLogger(__name__)
logging.basicConfig(format='%(asctime)s %(levelname)-4s %(message)s', datefmt='%m/%d %H:%M:%S')

game_limit = Limit(depth = 15, time = 3)
pair_limit = Limit(depth = 18, time = 5)
mate_defense_limit = Limit(depth = 15)

mate_soon = Mate(10)
allow_one_mater = True

def is_valid_mate_in_one(pair: NextMovePair, engine: YaneuraOu) -> bool:
    if pair.best.score != Mate(1):
        return False
    non_mate_win_threshold = 0.85
    if not pair.second or win_chances(pair.second.score) <= non_mate_win_threshold:
        return True
    return False

# is pair.best the only continuation?
def is_valid_attack(pair: NextMovePair, engine: YaneuraOu) -> bool:
    return (
        pair.second is None or 
        is_valid_mate_in_one(pair, engine) or 
        win_chances(pair.best.score) > win_chances(pair.second.score) + 0.4
    )

def get_next_pair(engine: YaneuraOu, node: Node, winner: bool) -> Optional[NextMovePair]:
    pair = get_next_move_pair(engine, node, winner, pair_limit)
    if node.board().turn == winner and not is_valid_attack(pair, engine):
        logger.debug("No valid attack {}".format(pair))
        return None
    return pair

def get_next_move(engine: YaneuraOu, node: Node, limit: Limit) -> Optional[Move]:
    result = engine.analyze(node, limit = limit)[0]["pv"][0]
    return result if result else None

def cook_mate(engine: YaneuraOu, node: Node, winner: bool) -> Optional[List[Move]]:
    
    board = node.board()

    if board.is_game_over():
        return []

    if board.turn == winner:
        pair = get_next_pair(engine, node, winner)
        if not pair:
            return None
        if pair.best.score < mate_soon:
            logger.debug("Best move is not a mate, we're probably not searching deep enough")
            return None
        move = pair.best.move
    else:
        next = get_next_move(engine, node, mate_defense_limit)
        if not next:
            return None
        move = next

    follow_up = cook_mate(engine, node.add_variation(move), winner)

    if follow_up is None:
        return None

    return [move] + follow_up


def cook_advantage(engine: YaneuraOu, node: Node, winner: bool) -> Optional[List[NextMovePair]]:
    
    board = node.board()

    if board.is_fourfold_repetition():
        return None

    pair = get_next_pair(engine, node, winner)
    if not pair:
        return []
    # if pair.best.score < Cp(1000):
    #     logger.info("Not winning enough, aborting")
    #     return None

    follow_up = cook_advantage(engine, node.add_variation(pair.best.move), winner)

    if follow_up is None:
        return None

    return [pair] + follow_up


def analyze_game(server: Server, engine: YaneuraOu, game: Node, args: argparse.Namespace) -> List[Puzzle]:

    logger.info("Analyzing game {}...".format(game.get_id()))

    node = game
    engine.usinewgame()
    
    while not node.is_end():
        node.eval = engine.analyze(node, game_limit)
        logger.debug("%d.  %s  %s" % (node.current_board.move_number, node.move().usi() if node.move() else "    ", str(node.eval[0]["score"].sente())))
        node = node.variation(0)

    prev_score: Score = Cp(20)
    puzs: List[Puzzle] = list()

    node = game

    while not node.is_end():

        current_eval = node.eval[0]["score"]

        if not current_eval:
            logger.debug("Skipping game without eval on move {}".format(node.current_board.move_number))
            return puzs

        result, puz = analyze_position(server, engine, node, prev_score, current_eval, args)

        if isinstance(puz, Puzzle):
            logger.info("Found puzzle in %s" % game.get_id())
            puzs.append(puz)

        prev_score = -result
        node = node.variation(0)

    if len(puzs) > 0:
        logger.info("Found %s from %s" % (len(puzs), game.get_id()))

    return puzs


def analyze_position(server: Server, engine: YaneuraOu, node: Node, prev_score: Score, current_eval: PovScore, args: argparse.Namespace) -> Tuple[Score, Optional[Puzzle]]:

    board = node.board()
    winner = board.turn
    score = current_eval.pov(winner)

    logger.debug("\nAnalyzing position, scores: {} -> {}".format(prev_score, score))

    if sum(1 for i in board.legal_moves) < 2:
        logger.debug("Not enough legal moves.")
        return score, None

    logger.debug("{} {} to {}".format(node.current_board.move_number, node.move() if node.move() else None, score))

    if prev_score > Cp(3000) and score < mate_soon:
        logger.debug("{} Too much of a winning position to start with {} -> {}".format(node.current_board.move_number, prev_score, score))
        return score, None
    if is_up_in_material(board, winner) and prev_score > Cp(2200):
        logger.debug("{} already up in material {} {} {}".format(node.current_board.move_number, winner, material_count(board, winner), material_count(board, not winner)))
        return score, None
    elif score >= Mate(1) and not allow_one_mater:
        logger.debug("{} mate in one".format(node.current_board.move_number))
        return score, None
    elif score > mate_soon:
        logger.debug("Mate {}. {} Probing...".format(node.current_board.move_number, score))
        if server.is_seen_pos(node):
            logger.debug("Skip duplicate position")
            return score, None
        mate_solution = cook_mate(engine, copy.deepcopy(node), winner)
        server.set_seen(node)
        return score, Puzzle(node, mate_solution, 999999999) if mate_solution is not None else None
    elif win_chances(score) > win_chances(prev_score) + 0.40:
        if score < Cp(750) and win_chances(score) < win_chances(prev_score) + 0.50:
            logger.debug("Not clearly winning and not equalizing enough, aborting")
            return score, None
        logger.debug("Advantage {}. {} -> {}. Probing...".format(node.current_board.move_number, prev_score, score))
        if server.is_seen_pos(node):
            logger.debug("Skip duplicate position")
            return score, None
        puzzle_node = copy.deepcopy(node)
        solution : Optional[List[NextMovePair]] = cook_advantage(engine, puzzle_node, winner)
        server.set_seen(node)
        if not solution:
            return score, None
        while len(solution) % 2 == 0 or not solution[-1].second:
            if not solution[-1].second:
                logger.debug("Remove final only-move")
            solution = solution[:-1]
        if not solution or len(solution) == 1:
            logger.debug("Discard one-mover")
            return score, None
        cp = solution[len(solution) - 1].best.score.score()
        return score, Puzzle(node, [p.best.move for p in solution], 999999998 if cp is None else cp)
    else:
        logger.debug("Nothing, {}, {}".format(score, win_chances(score)))
        return score, None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog='generator.py',
        description='takes a file and produces shogi puzzles')
    parser.add_argument("--file", "-f", help="input file", required=True, metavar="FILE.txt")
    parser.add_argument("--threads", "-t", help="count of cpu threads for engine searches", default="2")
    parser.add_argument("--uri", "-u", help="mongo URI where to post puzzles", default="mongodb://localhost:27017/")
    parser.add_argument("--skip", help="How many games to skip from the source", default="0")
    parser.add_argument("--verbose", "-v", help="increase verbosity", action="count")

    return parser.parse_args()

# expects this format: id;sfen;moves separated by space
def read_game(l: str) -> Optional[Node]:
    
    splitted = l.split(';')
    if splitted[1]:
        sfen = splitted[1]
    else:
        sfen = "lnsgkgsnl/1r5b1/ppppppppp/9/9/9/PPPPPPPPP/1B5R1/LNSGKGSNL b - 1"
    moves = splitted[2].split(' ')
    root = Node(Board(sfen))
    root.id = splitted[0]
    node = root
    for m in moves:
        if node.current_board.move_number > 85 or not m:
            break
        node = node.add_variation(Move.from_usi(m))
    return root


def main() -> None:
    sys.setrecursionlimit(10000) # else node.deepcopy() sometimes fails?
    args = parse_args()
    logger.setLevel(logging.INFO)
    engine = YaneuraOu(engine_filename())
    engine.start_engine(args.threads)
    server = Server(logger, args.uri, version)
    games = 0
    skip = int(args.skip)
    logger.info("Skipping first {} games".format(skip))

    print(f'v{version} {args.file}')

    try:
        with open(args.file) as m_file:
            skip_next = False
            for line in m_file:
                if games < skip:
                    continue
                if (game := read_game(line.strip('\n'))):
                    game_id = game.get_id()
                    if server.is_seen(game_id):
                        to_skip = 50
                        logger.info(f'Game was already seen before, skipping {to_skip} - {games}')
                        skip = games + to_skip
                        continue
                    try:
                        puzzles = analyze_game(server, engine, game, args)
                        if puzzles:
                            logger.debug(f'v{version} {args.file} {util.avg_knps()} knps, Game {games}')
                            server.post(game_id, puzzles)
                    except Exception as e:
                        logger.error("Exception on {}: {}".format(game_id, e))
    except KeyboardInterrupt:
        print(f'v{version} {args.file} Game {games}')
        sys.exit(1)

    engine.quit()

if __name__ == "__main__":
    main()
