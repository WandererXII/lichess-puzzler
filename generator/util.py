from dataclasses import dataclass
import math
import shogi
import os
from model import EngineMove, NextMovePair
from shogi import Board
from node import Node
from score import Score
from engine import YaneuraOu, Limit

nps = []

def pieces(board: Board, role: int, side: bool) -> int:
    return len(shogi.SquareSet(board.piece_bb[role] & board.occupied[side])) + board.pieces_in_hand[side][role]

def material_count(board: Board, side: bool) -> int:
    values = { shogi.PAWN: 1, shogi.LANCE: 3, shogi.KNIGHT: 3, shogi.SILVER: 5, shogi.GOLD: 5, shogi.BISHOP: 8, shogi.ROOK: 9,
              shogi.PROM_PAWN: 5, shogi.PROM_LANCE: 5, shogi.PROM_KNIGHT: 5, shogi.PROM_SILVER: 5, shogi.PROM_BISHOP: 12, shogi.PROM_ROOK: 13 }
    return sum(pieces(board, piece_type, side) * value for piece_type, value in values.items())

def material_diff(board: Board, side: bool) -> int:
    return material_count(board, side) - material_count(board, not side)

def is_up_in_material(board: Board, side: bool) -> bool:
    return material_diff(board, side) > 0

def engine_filename():
    if os.name == "nt":
        return "YaneuraOu.exe"
    elif os.name == "os2" or sys.platform == "darwin":
        return "YaneuraOu"
    elif os.name == "posix":
        return "YaneuraOu"

def get_next_move_pair(engine: YaneuraOu, node: Node, winner: bool, limit: Limit) -> NextMovePair:
    info = engine.analyze(node, multipv = 2, limit = limit)
    global nps
    nps.append(info[0]["nps"])
    nps = nps[-20:]
    # print(info)
    best = EngineMove(info[0]["pv"][0], info[0]["score"].pov(winner))
    second = EngineMove(info[1]["pv"][0], info[1]["score"].pov(winner)) if len(info) > 1 and "pv" in info[1] else None
    return NextMovePair(node, winner, best, second)

def avg_knps():
    global nps
    return round(sum(nps) / len(nps) / 1000) if nps else 0

def win_chances(score: Score) -> float:
    """
    winning chances from -1 to 1 https://graphsketch.com/?eqn1_color=1&eqn1_eqn=100+*+%282+%2F+%281+%2B+exp%28-0.0007+*+x%29%29+-+1%29&eqn2_color=2&eqn2_eqn=&eqn3_color=3&eqn3_eqn=&eqn4_color=4&eqn4_eqn=&eqn5_color=5&eqn5_eqn=&eqn6_color=6&eqn6_eqn=&x_min=-7000&x_max=7000&y_min=-100&y_max=100&x_tick=100&y_tick=10&x_label_freq=2&y_label_freq=2&do_grid=0&do_grid=1&bold_labeled_lines=0&bold_labeled_lines=1&line_width=4&image_w=850&image_h=525
    """
    mate = score.mate()
    if mate is not None:
        return 1 if mate > 0 else -1

    cp = score.score()
    return 2 / (1 + math.exp(-0.0007 * cp)) - 1 if cp is not None else 0

