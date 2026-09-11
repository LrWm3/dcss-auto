"""Recover official cutoff scores by quitting disposable checkpoint copies."""
import argparse
import json
from pathlib import Path
import shutil
import time

from general_env import GeneralEnvironment, sha
import storage


def extract(result_path, output):
    result = json.loads(result_path.read_text())
    source = Path(result["resume_checkpoint"])
    original = {p.name: sha(p) for p in source.iterdir() if p.is_file()}
    output.mkdir(parents=True, exist_ok=True)
    record_path = output / "score.json"
    if record_path.exists():
        return json.loads(record_path.read_text())
    clone = output / "checkpoint-copy"
    shutil.copytree(source, clone, dirs_exist_ok=True)
    rc = clone / "trial.rc"
    text = rc.read_text()
    anchor = "  if key == 30 then\n"
    if text.count(anchor) != 1:
        raise ValueError("unexpected checkpoint bridge")
    # Private administrative command, never an action exposed to the policy.
    text = text.replace(anchor,
        '  if key == 31 then\n'
        '    crawl.sendkeys("quit\\r")\n'
        '    crawl.do_commands({"CMD_QUIT"})\n'
        '    return\n'
        '  end\n' + anchor)
    rc.write_text(text)
    env = GeneralEnvironment(output / "extraction", data_role="confirmation")
    try:
        before = env.launch(clone)
        if before["turn"] != result["final_turn"]:
            raise ValueError("restore changed the cutoff turn")
        env.child.send(chr(31))
        deadline = time.monotonic() + 30
        record = None
        while time.monotonic() < deadline:
            try:
                env.child.read_nonblocking(65536, timeout=.2)
            except Exception:
                pass
            record = env.death_record()
            if record:
                break
        if not record or record.get("terminal") != "quit" or record.get("score") is None:
            raise RuntimeError(f"quit did not produce official score; inspect {env.work}")
        if record["turn"] != before["turn"]:
            raise ValueError("quitting advanced game time")
        if original != {p.name: sha(p) for p in source.iterdir() if p.is_file()}:
            raise ValueError("original checkpoint changed")
        recovered = {"seed":result["seed"], "policy_version":result["policy_version"],
            "score":record["score"], "turn":record["turn"], "level":record["level"],
            "method":"official_quit_score_from_checkpoint_copy", "original_outcome":"truncated",
            "original_result":str(result_path.resolve()), "checkpoint_hashes":original,
            "evidence":record["evidence"], "evidence_sha256":record["evidence_sha256"],
            "turns_advanced":0, "training_eligible":False}
        record_path.write_text(json.dumps(recovered, indent=2)+"\n")
        return recovered
    finally:
        env.close()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--batch", type=Path, required=True)
    args = parser.parse_args()
    batch = args.batch.resolve()
    storage.configure(batch.parents[2])
    records = []
    for path in sorted((batch / "results").glob("*.json")):
        if not json.loads(path.read_text()).get("truncated"):
            continue
        storage.guard()
        record = extract(path, batch / "cutoff_scores" / path.stem)
        records.append(record)
        print(json.dumps(record), flush=True)
    (batch / "cutoff_scores" / "summary.json").write_text(json.dumps(records, indent=2)+"\n")


if __name__ == "__main__":
    main()
