"""One-decision Crawl environment for the general policy trainer.

The engine still runs through Crawl's real Lua API.  Python receives one
structured observation, sends one semantic-action index, and waits for the
next observation.  The save command is a separate transport control and is
never exposed as a learning action.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import select
import shutil
import tempfile
import time
from pathlib import Path

import pexpect
import storage

HERE = Path(__file__).resolve().parent
# autonomous/ is directly under .webtiles/bench (the older tactical package
# has one additional directory and therefore used parents[3]).
ROOT = HERE.parents[2]
ENGINE = Path(os.environ.get(
    "DCSS_TACTICAL_ENGINE",
    # Use the established fast simulator; chain-v2 remains available for
    # reproducing the archived chained-encounter benchmarks.
    str(ROOT / "crawl-0.35/crawl-ref/source/crawl-tactical-sim"),
)).resolve()
BASE_RC = ROOT / ".webtiles/rcs/codex-autocrawl.rc"
FIFO_ENV = "DCSS_TACTICAL_OBSERVATION_FIFO"
CHARACTER = "CodexGeneral"
SEED = "1760771545328102746"


def sha(path: Path) -> str:
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def make_rc(path: Path, source_rc: Path | None = None) -> Path:
    """Build a general-policy RC without changing the archived controller."""
    source = Path(source_rc or BASE_RC).read_text()
    at = source.rfind(">")
    if at <= 0 or source[at + 1 :].strip():
        raise ValueError("source RC does not have a single final Lua block")
    bridge = (HERE / "general_bridge.lua").read_text()
    path.write_text(source[:at] + "\n" + bridge + "\n>\n")
    return path


class GeneralEnvironment:
    """Private Crawl process with exact save/restore boundaries."""

    def __init__(self, workspace: str | Path, seed: str = SEED,
                 source_rc: str | Path | None = None):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not str(seed).isdigit() or not 0 <= int(seed) < 2**64:
            raise ValueError("seed must be an unsigned 64-bit integer")
        self.seed = str(seed)
        self.source_rc = Path(source_rc or BASE_RC).resolve()
        self.child = None
        self.pipe_fd = None
        self.pipe_dir = None
        self.buffer = b""
        self.state = None
        self.events = None
        self.terminal_tail = ""
        self.works = []

    @property
    def work_path(self) -> Path:
        return self.work

    @staticmethod
    def _normalise_actions(state: dict) -> list[dict]:
        actions = state.get("actions", [])
        if isinstance(actions, dict):
            actions = [actions[key] for key in sorted(actions, key=lambda x: int(x))]
        return list(actions)

    def launch(self, checkpoint: str | Path | None = None) -> dict:
        storage.guard()
        self.close()
        self.work = Path(tempfile.mkdtemp(prefix="general-", dir=self.workspace))
        self.works.append(self.work)
        for directory in ("saves", "morgue", "macros"):
            (self.work / directory).mkdir()
        self.pipe_dir = Path(tempfile.mkdtemp(prefix="fifo-", dir=self.workspace))
        fifo = self.pipe_dir / "observations"
        os.mkfifo(fifo, 0o600)
        self.pipe_fd = os.open(fifo, os.O_RDWR | os.O_NONBLOCK)

        rc = self.work / "trial.rc"
        checkpoint_path = Path(checkpoint).resolve() if checkpoint else None
        if checkpoint_path:
            metadata = json.loads((checkpoint_path / "case.json").read_text())
            if metadata.get("engine_sha256") != sha(ENGINE):
                raise ValueError("checkpoint engine mismatch")
            if metadata.get("save_sha256") != sha(checkpoint_path / "checkpoint.cs"):
                raise ValueError("checkpoint checksum mismatch")
            shutil.copy2(checkpoint_path / "checkpoint.cs",
                         self.work / "saves" / (CHARACTER + ".cs"))
            shutil.copy2(checkpoint_path / "trial.rc", rc)
            self.seed = str(metadata["seed"])
        else:
            make_rc(rc, self.source_rc)

        args = ["-name", CHARACTER, "-rc", str(rc), "-seed", self.seed,
                "-no-player-bones", "-extra-opt-last", "species=Minotaur",
                "-extra-opt-last", "background=Berserker",
                "-extra-opt-last", "weapon=hand axe"]
        for option, folder in (("save_dir", "saves"),
                               ("morgue_dir", "morgue"),
                               ("macro_dir", "macros")):
            args += ["-extra-opt-last", f"{option}={self.work / folder}/"]

        self.transcript = (self.work / "terminal.txt").open("w")
        (self.work / "run.json").write_text(json.dumps({
            "schema_version": 1,
            "observation_schema": "crawl-general-v1",
            "action_schema": "crawl-semantic-actions-v1",
            "checkpoint": str(checkpoint_path) if checkpoint_path else None,
            "engine_sha256": sha(ENGINE),
            "rc_sha256": sha(rc),
            "source_rc_sha256": sha(self.source_rc),
            "adapter_sha256": sha(Path(__file__)),
            "seed": self.seed,
            "character": CHARACTER,
            "started_unix": time.time(),
        }, indent=2) + "\n")
        child_env = {**os.environ, "TERM": "xterm", FIFO_ENV: str(fifo),
                     "DCSS_TACTICAL_SIM_FLAGS": "3"}
        self.child = pexpect.spawn(str(ENGINE), args, cwd=str(ENGINE.parent),
                                   env=child_env, encoding="utf-8",
                                   codec_errors="replace", dimensions=(50, 160),
                                   timeout=30)
        self.child.logfile_read = self.transcript
        self.state = self.await_state(startup=True)
        (self.work / "initial.json").write_text(json.dumps(self.state, indent=2) + "\n")
        self.events = (self.work / "events.jsonl").open("a")
        self._event({"type": "reset", "observation": self.state})
        return self.state

    def _event(self, value: dict) -> None:
        if self.events:
            self.events.write(json.dumps(value, sort_keys=True) + "\n")
            self.events.flush()

    def death_record(self) -> dict | None:
        for path in (self.work / "morgue").glob("morgue-*.txt"):
            content = path.read_text(errors="replace")
            if re.search(r"\bGame seed:\s*" + re.escape(self.seed) + r"\b", content):
                previous = self.state or {}
                record = {"terminal": "death", "score": self._parse_score(content),
                        "level": previous.get("level"), "branch": previous.get("branch"),
                        "depth": previous.get("depth"), "turn": previous.get("turn"),
                        "evidence": str(path), "evidence_sha256": sha(path)}
                for logfile in (self.work / "saves").glob("logfile*"):
                    for line in logfile.read_text(errors="replace").splitlines():
                        fields = dict(part.split("=",1) for part in
                                      re.split(r"(?<!:):(?!:)",line) if "=" in part)
                        if fields.get("seed") != self.seed or fields.get("name") != CHARACTER:
                            continue
                        record.update(score=int(fields["sc"]),
                                      turn=int(fields["turn"]),
                                      level=fields.get("place", "").replace("::",":"),
                                      terminal={"winning":"win","leaving":"leave",
                                                "quitting":"quit"}.get(fields.get("ktyp"),"death"),
                                      death_cause=fields.get("killer"),
                                      runes=int(fields.get("nrune",0)))
                return record
        return None

    @staticmethod
    def _parse_score(content: str) -> int | None:
        for pattern in (r"(?m)^([0-9][0-9,]*) CodexGeneral .+\(level \d+,", r"\(([0-9][0-9,]*) points\)", r"\bScore:\s*([0-9][0-9,]*)", r"\bscore\s+([0-9][0-9,]*)"):
            match = re.search(pattern, content, re.I)
            if match:
                return int(match.group(1).replace(",", ""))
        return None

    def await_state(self, startup: bool = False,
                    expected_seq: int | None = None) -> dict:
        deadline = time.monotonic() + (180 if startup else 30)
        terminal_tail = ""
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line:
                    continue
                if not line.startswith(b"GJSON "):
                    raise RuntimeError("invalid general observation frame")
                state = json.loads(line[6:])
                state["actions"] = self._normalise_actions(state)
                if expected_seq is not None and state.get("seq") != expected_seq:
                    continue
                self.state = state
                return state

            ready, _, _ = select.select([self.pipe_fd, self.child.child_fd], [], [], .1)
            if self.pipe_fd in ready:
                chunk = os.read(self.pipe_fd, 1 << 20)
                if chunk:
                    self.buffer += chunk
            if self.child.child_fd in ready:
                try:
                    data = self.child.read_nonblocking(65536, timeout=0)
                    terminal_tail = (terminal_tail + data)[-12000:]
                    self.terminal_tail = terminal_tail
                    if startup and re.search(r"(?:Hit|Press) .* to (?:continue|start)",
                                             terminal_tail):
                        self.child.send(" ")
                        terminal_tail = ""
                except pexpect.TIMEOUT:
                    pass
                except pexpect.EOF:
                    death = self.death_record()
                    if death:
                        self.state = death
                        return death
                    raise RuntimeError("unexpected Crawl exit: " + terminal_tail[-2000:])
        death = self.death_record()
        if death:
            self.state = death
            return death
        raise TimeoutError(f"no general decision boundary; see {self.work}")

    def legal_actions(self) -> list[dict]:
        return self._normalise_actions(self.state or {})

    def get_observation(self) -> dict:
        if self.state is None:
            raise RuntimeError("environment not reset")
        return self.state

    get_legal_actions = legal_actions

    def is_terminal(self) -> bool:
        return bool((self.state or {}).get("terminal"))

    def get_game_score(self):
        return self.state.get("score") if self.is_terminal() else None

    def reset(self, checkpoint=None):
        return self.launch(checkpoint)

    def restore_state(self, checkpoint):
        return self.launch(checkpoint)

    def step(self, action: int | dict) -> dict:
        storage.guard()
        if not self.state or self.state.get("terminal"):
            raise RuntimeError("episode is terminal or not launched")
        actions = self.legal_actions()
        if isinstance(action, dict):
            index = next((i for i, item in enumerate(actions) if item == action), -1)
        else:
            index = int(action)
        if not 0 <= index < len(actions):
            raise ValueError(f"illegal action index {index}")
        before = self.state
        # 33 is '!' and leaves 0x1e available as a save control.  The Lua
        # bridge caps semantic actions at 88 so the byte protocol is unambiguous.
        self.child.send(chr(33 + index))
        after = self.await_state(expected_seq=int(before["seq"]) + 1)
        self.state = after
        self._event({"type": "transition", "observation": before,
                     "action": actions[index], "action_index": index,
                     "next_observation": after,
                     "terminated": after.get("terminal") == "death"})
        return after

    def save_state(self, destination: str | Path) -> dict:
        storage.guard()
        destination = Path(destination).resolve()
        if destination.exists():
            raise FileExistsError(destination)
        if not self.state or self.state.get("terminal"):
            raise RuntimeError("cannot save a terminal state")
        # ASCII record separator is deliberately outside the semantic action
        # range and is handled only by the Lua transport.
        self.child.send(chr(30))
        # CMD_SAVE_GAME_NOW returns to Crawl's main menu rather than closing
        # the ncurses process.  The menu marker is the successful save
        # boundary; close the private process after seeing it.
        self.child.expect([pexpect.EOF, "view rc file information and log"],
                          timeout=30)
        save = self.work / "saves" / (CHARACTER + ".cs")
        if not save.exists():
            raise RuntimeError(f"Crawl exited without save: {self.work}")
        destination.mkdir(parents=True)
        shutil.copy2(save, destination / "checkpoint.cs")
        shutil.copy2(self.work / "trial.rc", destination / "trial.rc")
        metadata = {
            "schema_version": 1,
            "id": destination.name,
            "seed": self.seed,
            "character": CHARACTER,
            "engine_sha256": sha(ENGINE),
            "rc_sha256": sha(destination / "trial.rc"),
            "save_sha256": sha(destination / "checkpoint.cs"),
            "observation_schema": "crawl-general-v1",
            "action_schema": "crawl-semantic-actions-v1",
            "observation": self.state,
            "fidelity": "exact Crawl save boundary including engine RNG state",
        }
        (destination / "case.json").write_text(json.dumps(metadata, indent=2) + "\n")
        self.close()
        return metadata

    def clone_state(self, destination: str | Path) -> dict:
        metadata = self.save_state(destination)
        self.launch(destination)
        return metadata

    def close(self) -> None:
        if getattr(self, "child", None) is not None:
            try:
                self.child.close(force=True)
            except Exception:
                pass
            self.child = None
        if getattr(self, "events", None):
            self.events.close()
            self.events = None
        if getattr(self, "transcript", None):
            self.transcript.close()
            self.transcript = None
        if getattr(self, "pipe_fd", None) is not None:
            os.close(self.pipe_fd)
            self.pipe_fd = None
        if getattr(self, "pipe_dir", None):
            try:
                (self.pipe_dir / "observations").unlink()
                self.pipe_dir.rmdir()
            except FileNotFoundError:
                pass
            self.pipe_dir = None

    def __enter__(self):
        return self

    def __exit__(self, *_):
        self.close()
