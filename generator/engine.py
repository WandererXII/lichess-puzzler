import subprocess
import os
import threading
import signal
import shogi
import dataclasses

from typing import List, Optional
from score import PovScore, Mate, Cp

@dataclasses.dataclass
class Limit:
    time: Optional[float] = None

    depth: Optional[int] = None

    nodes: Optional[int] = None

    mate: Optional[int] = None

    sente_clock: Optional[float] = None

    gote_clock: Optional[float] = None

    sente_inc: Optional[float] = None

    gote_inc: Optional[float] = None

    byoyomi: Optional[float] = None

    remaining_moves: Optional[int] = None


class YaneuraOu:

    def __init__(self, command: str, cwd=None, shell=True, _popen_lock=threading.Lock()):
        kwargs = {
            "shell": shell,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.PIPE,
            "bufsize": 1,  # Line buffered
            "universal_newlines": True,
        }
        self.multipv = 1

        if cwd is not None:
            kwargs["cwd"] = cwd

        # Prevent signal propagation from parent process
        try:
            # Windows
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type:ignore
        except AttributeError:
            # Unix
            kwargs["preexec_fn"] = os.setpgrp  # type:ignore

        with _popen_lock:  # Work around Python 2 Popen race condition
            self.engine_proccess = subprocess.Popen(command, **kwargs)  # type:ignore

    def quit(self):
        try:
            # Windows
            self.engine_proccess.send_signal(signal.CTRL_BREAK_EVENT)  # type:ignore
        except AttributeError:
            # Unix
            os.killpg(self.engine_proccess.pid, signal.SIGKILL)  # type:ignore

        self.engine_proccess.communicate()

    def send(self, line: str):
        #print("%s << %s" % (self.engine_proccess.pid, line))
        self.engine_proccess.stdin.write(line + "\n")  # type:ignore
        self.engine_proccess.stdin.flush()  # type:ignore

    def recv(self) -> str:
        while True:
            line: str = self.engine_proccess.stdout.readline()  # type:ignore
            if line == "":
                raise EOFError()

            line = line.rstrip()

            # print("%s >> %s" % (self.engine_proccess.pid, line))

            if line:
                return line

    def recv_usi(self) -> List[str]:
        command_and_args = self.recv().split(None, 1)
        if len(command_and_args) == 1:
            return [command_and_args[0], ""]
        elif len(command_and_args) == 2:
            return command_and_args

    def usinewgame(self):
        self.send("usinewgame")
        self.isready()

    def usi(self):
        self.send("usi")

        engine_info = {}

        while True:
            command, arg = self.recv_usi()

            if command == "usiok":
                return engine_info
            elif command == "id":
                name_and_value = arg.split(None, 1)
                if len(name_and_value) == 2:
                    engine_info[name_and_value[0]] = name_and_value[1]
            elif command == "option":
                pass
            else:
                print("Unexpected engine response to usi: %s %s", command, arg)

    def isready(self):
        self.send("stop")
        self.send("isready")
        while True:
            command, arg = self.recv_usi()
            if command == "readyok":
                break
            elif command == "info" and arg.startswith("string Error! "):
                print("Unexpected engine response to isready: %s %s", command, arg)
            elif command == "info" and arg.startswith("string "):
                pass
            else:
                print("Unexpected engine response to isready: %s %s", command, arg)

    def stop(self):
        self.send("stop")

    def setoption(self, name, value):
        if value is True:
            value = "true"
        elif value is False:
            value = "false"
        elif value is None:
            value = "none"

        self.send("setoption name %s value %s" % (name, value))

    def id(self) -> str:
        return str(self.engine_proccess.pid)

    def start_engine(self, threads=4, memory=512):
        self.usi()
        self.setoption("Threads", str(threads))
        self.setoption("USI_Hash", str(memory))
        # self.setoption("EnteringKingRule", "TryRule")
        self.setoption("BookFile", "no_book")
        self.setoption("ConsiderationMode", "true")
        self.setoption("OutputFailLHPV", "true")
        self.isready()

    def analyze(self, node, limit=Limit(), multipv=1, ponder=False, infinite=False, root_moves=list()):
        if multipv != self.multipv:
            self.multipv = multipv
            self.setoption("MultiPV", multipv)
        self.isready()

        self.send("position sfen %s" % (node.current_board.sfen()))

        builder = ["go"]
        if ponder:
            builder.append("ponder")
        if limit.sente_clock is not None:
            builder.append("wtime")
            builder.append(str(max(1, int(limit.sente_clock * 1000))))
        if limit.gote_clock is not None:
            builder.append("btime")
            builder.append(str(max(1, int(limit.gote_clock * 1000))))
        if limit.sente_inc is not None:
            builder.append("winc")
            builder.append(str(int(limit.sente_inc * 1000)))
        if limit.gote_inc is not None:
            builder.append("binc")
            builder.append(str(int(limit.gote_inc * 1000)))
        if limit.byoyomi is not None:
            builder.append("byoyomi")
            builder.append(str(int(limit.byoyomi * 1000)))
        if limit.remaining_moves is not None and int(limit.remaining_moves) > 0:
            builder.append("movestogo")
            builder.append(str(int(limit.remaining_moves)))
        if limit.depth is not None:
            builder.append("depth")
            builder.append(str(max(1, int(limit.depth))))
        if limit.nodes is not None:
            builder.append("nodes")
            builder.append(str(max(1, int(limit.nodes))))
        if limit.mate is not None:
            builder.append("mate")
            builder.append(str(max(1, int(limit.mate))))
        if limit.time is not None:
            builder.append("movetime")
            builder.append(str(max(1, int(limit.time * 1000))))
        if infinite:
            builder.append("infinite")
        if root_moves:
            builder.append("searchmoves")
            builder.extend(move.usi() for move in root_moves)
        self.send(" ".join(builder))

        color = shogi.WHITE if node.current_board.sfen().split(" ")[1] == 'w' else shogi.BLACK
        info = [{} for i in range(1, self.multipv + 1)]
        
        def parse_usi(m):
            if m.startswith('rep') or m == 'resign':
                return
            else:
                return shogi.Move.from_usi(m)

        while True:
            command, arg = self.recv_usi()

            if command == "bestmove":
                return info

            elif command == "info":
                arg = arg or ""

                # Parse all other parameters
                score_kind, score_value = None, None
                current_parameter = None
                current_multipv = 1
                current_nps = 0
                current_pv = []

                for token in arg.split(" "):
                    if token in ["score", "multipv", "pv", "nps"]:
                        current_parameter = token
                    elif current_parameter == "multipv":
                        current_multipv = int(token)
                        current_parameter = None
                    elif current_parameter == "nps":
                        current_nps = int(token)
                        current_parameter = None
                    elif current_parameter == "score":
                        if token in ["cp", "mate"]:
                            score_kind = token
                            score_value = None
                        else:
                            score_value = int(token)
                            current_parameter = None
                    elif current_parameter == "pv":
                        current_pv.append(parse_usi(token))

                # Set score. Prefer scores that are not just a bound
                if score_kind is not None and score_value is not None:
                    if score_kind == "mate":
                        info[current_multipv - 1]["score"] = PovScore(color, Mate(score_value))
                    elif score_kind == "cp":
                        info[current_multipv - 1]["score"] = PovScore(color, Cp(score_value))
                info[current_multipv - 1]["pv"] = current_pv
                info[current_multipv - 1]["nps"] = current_nps
            else:
                print("Unexpected engine response to go: %s %s", command, arg)



class Fairy:

    def __init__(self, command: str, cwd=None, shell=True, _popen_lock=threading.Lock()):
        kwargs = {
            "shell": shell,
            "stdout": subprocess.PIPE,
            "stderr": subprocess.STDOUT,
            "stdin": subprocess.PIPE,
            "bufsize": 1,  # Line buffered
            "universal_newlines": True,
        }
        self.multipv = 1

        if cwd is not None:
            kwargs["cwd"] = cwd

        # Prevent signal propagation from parent process
        try:
            # Windows
            kwargs["creationflags"] = subprocess.CREATE_NEW_PROCESS_GROUP  # type:ignore
        except AttributeError:
            # Unix
            kwargs["preexec_fn"] = os.setpgrp  # type:ignore

        with _popen_lock:  # Work around Python 2 Popen race condition
            self.engine_proccess = subprocess.Popen("fairy.exe", **kwargs)  # type:ignore

    def quit(self):
        try:
            # Windows
            self.engine_proccess.send_signal(signal.CTRL_BREAK_EVENT)  # type:ignore
        except AttributeError:
            # Unix
            os.killpg(self.engine_proccess.pid, signal.SIGKILL)  # type:ignore

        self.engine_proccess.communicate()

    def send(self, line: str):
        #print("%s << %s" % (self.engine_proccess.pid, line))
        self.engine_proccess.stdin.write(line + "\n")  # type:ignore
        self.engine_proccess.stdin.flush()  # type:ignore

    def recv(self) -> str:
        while True:
            line: str = self.engine_proccess.stdout.readline()  # type:ignore
            if line == "":
                raise EOFError()

            line = line.rstrip()

            # print("%s >> %s" % (self.engine_proccess.pid, line))

            if line:
                return line

    def recv_usi(self) -> List[str]:
        command_and_args = self.recv().split(None, 1)
        if len(command_and_args) == 1:
            return [command_and_args[0], ""]
        elif len(command_and_args) == 2:
            return command_and_args

    def usinewgame(self):
        self.send("usinewgame")
        self.isready()

    def usi(self):
        self.send("usi")

        engine_info = {}

        while True:
            command, arg = self.recv_usi()

            if command == "usiok":
                return engine_info
            elif command == "id":
                name_and_value = arg.split(None, 1)
                if len(name_and_value) == 2:
                    engine_info[name_and_value[0]] = name_and_value[1]
            elif command == "option":
                pass
            else:
                print("Unexpected engine response to usi: %s %s", command, arg)

    def isready(self):
        self.send("stop")
        self.send("isready")
        while True:
            command, arg = self.recv_usi()
            if command == "readyok":
                break
            elif command == "info" and arg.startswith("string Error! "):
                print("Unexpected engine response to isready: %s %s", command, arg)
            elif command == "info" and arg.startswith("string "):
                pass
            else:
                print("Unexpected engine response to isready: %s %s", command, arg)

    def stop(self):
        self.send("stop")

    def setoption(self, name, value):
        if value is True:
            value = "true"
        elif value is False:
            value = "false"
        elif value is None:
            value = "none"

        self.send("setoption name %s value %s" % (name, value))

    def id(self) -> str:
        return str(self.engine_proccess.pid)

    def start_engine(self, threads=4, memory=1024):
        self.usi()
        self.setoption("Threads", str(threads))
        self.setoption("Hash", str(memory))
        self.setoption("UCI_AnalyseMode", True)
        self.setoption("Skill Level", str(20))
        self.isready()

    def analyze(self, node, limit=Limit(), multipv=1, ponder=False, infinite=False, root_moves=list()):
        if multipv != self.multipv:
            self.multipv = multipv
            self.setoption("MultiPV", multipv)
        self.isready()

        self.send("position sfen %s" % (node.current_board.sfen()))

        builder = ["go"]
        if ponder:
            builder.append("ponder")
        if limit.sente_clock is not None:
            builder.append("wtime")
            builder.append(str(max(1, int(limit.sente_clock * 1000))))
        if limit.gote_clock is not None:
            builder.append("btime")
            builder.append(str(max(1, int(limit.gote_clock * 1000))))
        if limit.sente_inc is not None:
            builder.append("winc")
            builder.append(str(int(limit.sente_inc * 1000)))
        if limit.gote_inc is not None:
            builder.append("binc")
            builder.append(str(int(limit.gote_inc * 1000)))
        if limit.byoyomi is not None:
            builder.append("byoyomi")
            builder.append(str(int(limit.byoyomi * 1000)))
        if limit.remaining_moves is not None and int(limit.remaining_moves) > 0:
            builder.append("movestogo")
            builder.append(str(int(limit.remaining_moves)))
        if limit.depth is not None:
            builder.append("depth")
            builder.append(str(max(1, int(limit.depth))))
        if limit.nodes is not None:
            builder.append("nodes")
            builder.append(str(max(1, int(limit.nodes))))
        if limit.mate is not None:
            builder.append("mate")
            builder.append(str(max(1, int(limit.mate))))
        if limit.time is not None:
            builder.append("movetime")
            builder.append(str(max(1, int(limit.time * 1000))))
        if infinite:
            builder.append("infinite")
        if root_moves:
            builder.append("searchmoves")
            builder.extend(move.usi() for move in root_moves)
        self.send(" ".join(builder))

        color = shogi.WHITE if node.current_board.sfen().split(" ")[1] == 'w' else shogi.BLACK
        info = [{} for i in range(1, self.multipv + 1)]
        
        def parse_usi(m):
            if m.startswith('rep') or m == 'resign':
                return
            else:
                return shogi.Move.from_usi(m)

        while True:
            command, arg = self.recv_usi()

            if command == "bestmove":
                return info

            elif command == "info":
                arg = arg or ""

                # Parse all other parameters
                score_kind, score_value = None, None
                current_parameter = None
                current_multipv = 1
                current_nps = 0
                current_pv = []

                for token in arg.split(" "):
                    if token in ["score", "multipv", "pv", "nps"]:
                        current_parameter = token
                    elif current_parameter == "multipv":
                        current_multipv = int(token)
                        current_parameter = None
                    elif current_parameter == "nps":
                        current_nps = int(token)
                        current_parameter = None
                    elif current_parameter == "score":
                        if token in ["cp", "mate"]:
                            score_kind = token
                            score_value = None
                        else:
                            score_value = int(token)
                            current_parameter = None
                    elif current_parameter == "pv":
                        current_pv.append(parse_usi(token))

                # Set score. Prefer scores that are not just a bound
                if score_kind is not None and score_value is not None:
                    if score_kind == "mate":
                        info[current_multipv - 1]["score"] = PovScore(color, Mate(score_value))
                    elif score_kind == "cp":
                        info[current_multipv - 1]["score"] = PovScore(color, Cp(score_value))
                info[current_multipv - 1]["pv"] = current_pv
                info[current_multipv - 1]["nps"] = current_nps
            else:
                print("Unexpected engine response to go: %s %s", command, arg)
