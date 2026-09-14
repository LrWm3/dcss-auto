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
import engine_cache

HERE = Path(__file__).resolve().parent
# autonomous/ is directly under .webtiles/bench (the older tactical package
# has one additional directory and therefore used parents[3]).
ROOT = HERE.parents[2]
ENGINE = Path(os.environ.get(
    "DCSS_TACTICAL_ENGINE",
    # Dedicated non-exiting snapshot build; historical binaries are preserved.
    str(ROOT / "crawl-0.35/crawl-ref/source" / (
        "crawl-general-explore-sim" if os.environ.get('DCSS_EXPLORATION_SCORE') == '1'
        else "crawl-general-sim")),
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
    if os.environ.get('DCSS_REST_ONLY') == '1':
        bridge = 'GENERAL_AGENT_REST_ONLY = true\n' + bridge
    if os.environ.get('DCSS_TARGET_DETAILS') == '1':
        bridge = 'GENERAL_AGENT_TARGET_DETAILS = true\n' + bridge
    if os.environ.get('DCSS_REPRESENTATION') == 'spatial-v6':
        bridge += '\n' + (HERE / 'structured_bridge.lua').read_text()
    path.write_text(source[:at] + "\n" + bridge + "\n>\n")
    return path


class GeneralEnvironment:
    """Private Crawl process with exact save/restore boundaries."""

    def __init__(self, workspace: str | Path, seed: str = SEED,
                 source_rc: str | Path | None = None, data_role: str = "training"):
        self.workspace = Path(workspace).resolve()
        self.workspace.mkdir(parents=True, exist_ok=True)
        if not str(seed).isdigit() or not 0 <= int(seed) < 2**64:
            raise ValueError("seed must be an unsigned 64-bit integer")
        self.seed = str(seed)
        self.data_role = data_role
        self.source_rc = Path(source_rc or BASE_RC).resolve()
        self.child = None
        self.pipe_fd = None
        self.pipe_dir = None
        self.buffer = b""
        self.state = None
        self.events = None
        self.terminal_tail = ""
        self.works = []
        self.record_events = True

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
        self.terminal_tail = ''
        self.work = Path(tempfile.mkdtemp(prefix="general-", dir=self.workspace))
        self.works.append(self.work)
        for directory in ("saves", "morgue", "macros"):
            (self.work / directory).mkdir()
        engine_hash = sha(ENGINE)
        cache_template = engine_cache.install(self.work / 'saves', engine_hash)
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
            saved_rest = 'GENERAL_AGENT_REST_ONLY = true\n' in rc.read_text()
            if saved_rest != (os.environ.get('DCSS_REST_ONLY') == '1'):
                raise ValueError('checkpoint REST/WAIT action mode mismatch; start a fresh game')
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
            "event_schema": "initial_then_next_v1" if self.record_events else "external_replay",
            "cache_template": cache_template,
            "observation_schema": "crawl-general-v1",
            "action_schema": "crawl-semantic-actions-v1",
            "checkpoint": str(checkpoint_path) if checkpoint_path else None,
            "engine_sha256": sha(ENGINE),
            "rc_sha256": sha(rc),
            "source_rc_sha256": sha(self.source_rc),
            "adapter_sha256": sha(Path(__file__)),
            "seed": self.seed,
            "data_role": self.data_role,
            "character": CHARACTER,
            "started_unix": time.time(),
        }, indent=2) + "\n")
        child_env = {**os.environ, "TERM": "xterm", FIFO_ENV: str(fifo),
                     "DCSS_TACTICAL_SIM_FLAGS": "3"}
        child_env['DCSS_EXPLORATION_RESULT'] = str(self.work / 'exploration-final.json')
        self.child = pexpect.spawn(str(ENGINE), args, cwd=str(ENGINE.parent),
                                   env=child_env, encoding="utf-8",
                                   codec_errors="replace", dimensions=(50, 160),
                                   timeout=30)
        self.child.delaybeforesend = None
        self.child.logfile_read = None
        self.state = self.await_state(startup=True)
        if os.environ.get('DCSS_REPRESENTATION') == 'spatial-v6':
            self.state['history'] = (metadata.get('observation', {}).get('history', [])
                                     if checkpoint_path else [])
        if os.environ.get('DCSS_VISIT_MEMORY') == '1':
            from visit_memory import initial
            self.state['visit_memory'] = ((metadata.get('observation', {}).get('visit_memory')
                                          if checkpoint_path else None) or initial(self.state))
        engine_cache.publish(self.work / 'saves', engine_hash)
        (self.work / "initial.json").write_text(json.dumps(self.state, indent=2) + "\n")
        self.events = (self.work / "events.jsonl").open("a", buffering=65536) if self.record_events else None
        self._event({"type": "reset", "observation": self.state})
        return self.state

    def _event(self, value: dict) -> None:
        if self.events:
            if value.get('type') == 'transition':
                value = {k:v for k,v in value.items() if k != 'observation'}
            value = {**value, "episode_seed": self.seed, "data_role": self.data_role}
            self.events.write(json.dumps(value, sort_keys=True) + "\n")

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
                if os.environ.get('DCSS_EXPLORATION_SCORE') == '1':
                    final = json.loads((self.work / 'exploration-final.json').read_text())
                    if (final.get('version') != 1 or final.get('seed') != self.seed
                            or final.get('native_score') != record['score']):
                        raise ValueError('terminal exploration/native score mismatch')
                    record['exploration_raw'] = final['exploration_raw']
                    from exploration_score import attach
                    record = attach(record)
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
                    expected_seq: int | None = None, snapshot: bool = False) -> dict:
        deadline = time.monotonic() + (180 if startup else 30)
        terminal_tail = ""
        while time.monotonic() < deadline:
            while b"\n" in self.buffer:
                line, self.buffer = self.buffer.split(b"\n", 1)
                if not line:
                    continue
                if line.startswith(b'GSAVED ') and snapshot:
                    ack = json.loads(line[7:])
                    if ack.get('seq') != expected_seq:
                        raise RuntimeError('snapshot acknowledgement sequence mismatch')
                    if ack.get('rng_state') != self.state.get('rng_state'):
                        raise RuntimeError('saving checkpoint changed non-UI RNG state')
                    return ack
                if snapshot:
                    raise RuntimeError('expected checkpoint acknowledgement, not an observation')
                if not line.startswith(b"GJSON "):
                    raise RuntimeError("invalid general observation frame")
                state = json.loads(line[6:])
                from exploration_score import attach
                state = attach(state)
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
        state = self.state or {}
        return state.get("score") if (self.is_terminal()
                    or state.get("score_status") == "live_official") else None

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
        try:
            after = self.await_state(expected_seq=int(before["seq"]) + 1)
        except Exception as exc:
            # The ordinary transition is only written on success. Preserve the
            # attempted action as well, so a UI block is not blamed on the
            # preceding successful move in the replay.
            (self.work / 'failed_action.json').write_text(json.dumps({
                'action': actions[index], 'action_index':index,
                'observation':before, 'error':str(exc)}, indent=2))
            raise
        if os.environ.get('DCSS_REPRESENTATION') == 'spatial-v6':
            from observation_history import add_history
            after = add_history(before, actions[index], after)
        if os.environ.get('DCSS_VISIT_MEMORY') == '1':
            from visit_memory import advance
            after['visit_memory'] = advance(before, actions[index], after)
        self.state = after
        self._event({"type": "transition", "observation": before,
                     "action": actions[index], "action_index": index,
                     "next_observation": after,
                     "terminated": after.get("terminal") == "death"})
        return after

    def save_state(self, destination: str | Path, *, in_place: bool = True) -> dict:
        storage.guard()
        destination = Path(destination).resolve()
        if destination.exists():
            raise FileExistsError(destination)
        if not self.state or self.state.get("terminal"):
            raise RuntimeError("cannot save a terminal state")
        # ASCII record separator is deliberately outside the semantic action
        # range and is handled only by the Lua transport.
        supported = bool(self.state.get('snapshot_in_place'))
        in_place = in_place and supported
        self.child.send(chr(29 if supported and not in_place else 30))
        # CMD_SAVE_GAME_NOW returns to Crawl's main menu rather than closing
        # the ncurses process.  The menu marker is the successful save
        # boundary; close the private process after seeing it.
        if in_place:
            self.await_state(expected_seq=self.state['seq'], snapshot=True)
        else:
            self.child.expect([pexpect.EOF, "view rc file information and log"], timeout=30)
        save = self.work / "saves" / (CHARACTER + ".cs")
        if not save.exists():
            raise RuntimeError(f"Crawl exited without save: {self.work}")
        destination.mkdir(parents=True)
        shutil.copy2(save, destination / "checkpoint.cs")
        shutil.copy2(self.work / "trial.rc", destination / "trial.rc")
        metadata = {
            "schema_version": 1,
            "id": destination.name,
            "data_role": self.data_role,
            "seed": self.seed,
            "character": CHARACTER,
            "engine_sha256": sha(ENGINE),
            "rc_sha256": sha(destination / "trial.rc"),
            "bridge_sha256": (sha(HERE / 'general_bridge.lua')
                              if (HERE / 'general_bridge.lua').read_text() in (destination / 'trial.rc').read_text()
                              else None),
            "save_sha256": sha(destination / "checkpoint.cs"),
            "observation_schema": "crawl-general-v1",
            "action_schema": "crawl-semantic-actions-v1",
            "observation": self.state,
            "fidelity": "exact Crawl save boundary including engine RNG state",
            "save_mode": "in_place" if in_place else "save_and_quit",
        }
        (destination / "case.json").write_text(json.dumps(metadata, indent=2) + "\n")
        if not in_place:
            self.close()
        return metadata

    def clone_state(self, destination: str | Path) -> dict:
        metadata = self.save_state(destination)
        if metadata.get('save_mode') != 'in_place':
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
            self.transcript.write(self.terminal_tail)
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
