"""Predeclared screen -> fresh confirmation -> scheduled audit protocol.

Confirmation has no interim decisions. Errors/cutoffs remain censored. Each
finished game is durable, so restarting cannot cherry-pick a new batch.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import contextmanager
import fcntl
import json
import math
from pathlib import Path
import random
import secrets
import shutil
import time

from collect import run_episode
from data_split import CONFIRMATION_PREFIX, AUDIT_PREFIX
from general_env import ENGINE, BASE_RC, HERE, sha
import storage
from score_result import has_episode_score

PROTOCOL = {
    "version": "screen-confirm-audit-v2-cutoff-score", "confirmation_pairs": 30,
    "score_metric": "official_final_or_budget_cutoff_score",
    "confidence": 0.95, "alternative": "greater", "bootstrap_resamples": 10000,
    "bootstrap_rng": 42, "margin": 0.0, "interim_decisions": False,
    "audit_every_completed_cycles": 5, "audit_pairs": 30,
    "max_workers": 4, "screen_excess_floor_cutoffs": 2,
    "multiplicity": "per-comparison only; no family-wise guarantee",
}


def write(path, value):
    storage.guard()
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(value, indent=2, sort_keys=True) + "\n")
    tmp.replace(path)


@contextmanager
def run_lock(root):
    root = Path(root)
    root.mkdir(parents=True, exist_ok=True)
    with (root / ".training.lock").open("a") as handle:
        try:
            fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            raise RuntimeError("another training/confirmation process owns this run") from None
        yield


def ensure_protocol(root):
    root = Path(root)
    path = root / "evaluations" / "selection_protocol.json"
    if path.exists():
        protocol = json.loads(path.read_text())
        if protocol != PROTOCOL:
            if protocol.get("version") == "screen-confirm-audit-v1":
                # Old batches retain their own manifest/rule/results unchanged.
                archived = path.with_name("selection_protocol.v1.json")
                if not archived.exists():
                    write(archived, protocol)
                write(path, PROTOCOL)
            else:
                raise ValueError("selection protocol changed; use a separately declared run")
    else:
        write(path, PROTOCOL)
    original = root / "champions" / "V0.pt"
    if original.exists():
        freeze_file(original, root / "evaluations" / "original_baseline.pt")
    return dict(PROTOCOL)


def complete_pairs(left, right):
    def index(rows):
        result = {str(r.get("seed")): r for r in rows}
        return result if len(result) == len(rows) else None
    a, b = index(left), index(right)
    if a is None or b is None or not a or set(a) != set(b):
        return None
    differences = []
    for seed in sorted(a):
        pair = a[seed], b[seed]
        if not all(has_episode_score(r) for r in pair):
            return None
        if not all(math.isfinite(float(r["score"])) for r in pair):
            return None
        differences.append(float(b[seed]["score"]) - float(a[seed]["score"]))
    return differences


def screen_decision(champion, candidate):
    left, right = champion["results"], candidate["results"]
    if any("error" in r or r.get("truncation_reason") == "no_game_time_progress" for r in right):
        return {"state": "screen_failed", "category": "broken", "promote": False}
    # Floor-budget cutoffs are scored outcomes, not disqualifying failures.
    differences = complete_pairs(left, right)
    if differences is None or len(differences) < 5:
        return {"state": "inconclusive", "reason": "screen lacks five complete score pairs", "promote": False}
    improvement = sum(differences)/len(differences)
    return {"state": "awaiting_confirmation" if improvement > 0 else "screen_failed",
            "category": "promising" if improvement > 0 else "unpromising",
            "mean_difference": improvement, "promote": False}


def confirmation_decision(left, right, protocol=PROTOCOL):
    differences = complete_pairs(left, right)
    if (differences is None or len(differences) != protocol["confirmation_pairs"]):
        return {"state": "inconclusive", "reason": "incomplete fixed confirmation batch", "promote": False}
    rng = random.Random(protocol["bootstrap_rng"])
    n = len(differences)
    means = sorted(sum(rng.choices(differences, k=n))/n
                   for _ in range(protocol["bootstrap_resamples"]))
    def quantile(q):
        position = (len(means)-1)*q
        i = int(position)
        return means[i] + (position-i)*(means[min(i+1, len(means)-1)]-means[i])
    lower, upper = quantile(1-protocol["confidence"]), quantile(protocol["confidence"])
    state = ("confirmed_better" if lower > protocol["margin"] else
             "confirmed_worse" if upper < 0 else "inconclusive")
    return {"state": state, "promote": state == "confirmed_better",
            "pairs": n, "mean_difference": sum(differences)/n,
            "lower_one_sided_95": lower, "upper_one_sided_95": upper,
            "method": "paired_percentile_bootstrap", "interim_decision": False}


def environment_identity():
    return {"engine": sha(ENGINE), "base_rc": sha(BASE_RC),
            "bridge": sha(HERE / "general_bridge.lua"),
            "adapter": sha(HERE / "general_env.py"),
            "features": sha(HERE / "features.py"),
            "policy": sha(HERE / "policy.py"),
            "model": sha(HERE / "model.py"),
            "collector": sha(HERE / "collect.py"),
            "evaluator": sha(HERE / "selection.py"),
            "score_result": sha(HERE / "score_result.py"),
            "budget": sha(HERE / "episode_budget.py")}


def freeze_file(source, target):
    source, target = Path(source), Path(target)
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists():
        if sha(source) != sha(target):
            raise ValueError("frozen checkpoint mismatch")
    else:
        storage.guard()
        temporary = target.with_name(target.name + ".tmp")
        shutil.copy2(source, temporary)
        temporary.replace(target)


def prepare_batch(root, label, champion, candidate, config, kind="confirmation"):
    if kind not in ("confirmation", "audit") or not label.replace("-", "").replace("_", "").isalnum():
        raise ValueError("invalid batch kind or label")
    root = Path(root).resolve()
    protocol = ensure_protocol(root)
    folder = root / "evaluations" / ("confirmations" if kind == "confirmation" else "audits") / label
    path = folder / "manifest.json"
    if path.exists():
        manifest = json.loads(path.read_text())
        if (manifest["hashes"] != {"champion": sha(Path(champion)), "candidate": sha(Path(candidate))}
                or manifest["environment"] != environment_identity()
                or manifest["budgets"] != {"per_floor": config["decisions_per_floor"], "total": config["total_decisions"]}):
            raise ValueError("cannot resume a frozen batch with changed models/environment/budgets")
        return folder
    registry_path = root / "evaluations" / "seed_registry.json"
    registry = json.loads(registry_path.read_text()) if registry_path.exists() else {"batches": {}}
    key = f"{kind}/{label}"
    hashes = {"champion": sha(Path(champion)), "candidate": sha(Path(candidate))}
    # A candidate/champion pair gets one confirmation, not retries on fresh
    # seeds until lucky. Existing abandoned reservations are reused on restart.
    if kind == "confirmation":
        for reserved_key, record in registry["batches"].items():
            if reserved_key != key and record["kind"] == kind and record["hashes"] == hashes:
                # Reuse the original batch, including an inconclusive outcome.
                # A new label must never buy another chance with new seeds.
                return prepare_batch(root, reserved_key.split("/",1)[1], champion, candidate, config, kind)
    if key not in registry["batches"]:
        used = {s for r in registry["batches"].values() for s in r["seeds"]}
        used.update(str(s) for s in config.get("seeds", []))
        prefix = CONFIRMATION_PREFIX if kind == "confirmation" else AUDIT_PREFIX
        seeds = []
        count = protocol["confirmation_pairs"] if kind == "confirmation" else protocol["audit_pairs"]
        while len(seeds) < count:
            seed = str((prefix << 60) | secrets.randbits(60))
            if seed not in used:
                used.add(seed); seeds.append(seed)
        registry["batches"][key] = {"kind": kind, "hashes": hashes, "seeds": seeds}
        write(registry_path, registry)
    reservation = registry["batches"][key]
    if reservation["hashes"] != hashes:
        raise ValueError("reserved batch belongs to different checkpoints")
    freeze_file(champion, folder / "champion.pt")
    freeze_file(candidate, folder / "candidate.pt")
    manifest = {"label": label, "kind": kind, "protocol": protocol,
                "hashes": hashes, "seeds": reservation["seeds"], "environment": environment_identity(),
                "budgets": {"per_floor": config["decisions_per_floor"], "total": config["total_decisions"]},
                "created_unix": time.time(), "training_eligible": False,
                "source_champion": str(Path(champion).resolve()), "source_candidate": str(Path(candidate).resolve())}
    write(path, manifest)
    write(folder / "status.json", {"state": "awaiting_confirmation" if kind == "confirmation" else "awaiting_audit",
                                  "completed_games": 0, "planned_games": 2*len(manifest["seeds"])})
    return folder


def run_batch(folder, runner=None):
    folder = Path(folder)
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest["environment"] != environment_identity():
        raise ValueError("frozen evaluation environment changed")
    for role in ("champion", "candidate"):
        if sha(folder / f"{role}.pt") != manifest["hashes"][role]:
            raise ValueError("frozen model changed")
    if (folder / "decision.json").exists():
        return json.loads((folder / "decision.json").read_text())
    runner = runner or run_episode
    jobs = [(role, seed) for seed in manifest["seeds"] for role in ("champion", "candidate")]
    def result_path(role, seed):
        return folder / "results" / f"{role}-{seed}.json"
    # Malformed persisted output is isolated, not silently counted as a game.
    for role, seed in jobs:
        path = result_path(role, seed)
        if path.exists():
            try:
                record = json.loads(path.read_text())
                if (record.get("seed") != seed or record.get("frozen_model_sha256") != manifest["hashes"][role]):
                    raise ValueError("result identity mismatch")
            except (ValueError, AttributeError):
                path.replace(path.with_name(path.name + f".invalid-{time.time_ns()}"))
    completed = sum(result_path(r,s).exists() for r,s in jobs)
    def progress():
        write(folder / "status.json", {"state": "confirming" if manifest["kind"] == "confirmation" else "auditing",
              "completed_games": completed, "planned_games": len(jobs), "updated_unix": time.time(),
              "interim_decision": None})
    progress()
    def trial(role, seed):
        return runner(folder / "games" / role / seed, seed, manifest["budgets"]["per_floor"],
                      model_path=folder / f"{role}.pt", epsilon=0, policy_version=role,
                      snapshot=False, total_steps=manifest["budgets"]["total"], data_role=manifest["kind"])
    with ThreadPoolExecutor(max_workers=manifest["protocol"]["max_workers"]) as pool:
        futures = {pool.submit(trial,r,s):(r,s) for r,s in jobs if not result_path(r,s).exists()}
        for future in as_completed(futures):
            role, seed = futures[future]
            try:
                result = future.result()
                if not isinstance(result, dict) or result.get("seed") != seed:
                    raise ValueError("actor returned a result for the wrong seed")
            except Exception as exc:
                result = {"seed": seed, "error": repr(exc), "policy_version": role}
            result.update(data_role=manifest["kind"], training_eligible=False,
                          frozen_model_sha256=manifest["hashes"][role])
            write(result_path(role,seed), result)
            completed += 1
            progress()
    left = [json.loads(result_path("champion",s).read_text()) for s in manifest["seeds"]]
    right = [json.loads(result_path("candidate",s).read_text()) for s in manifest["seeds"]]
    # Compute a decision exactly once, after every scheduled game has a result.
    decision = confirmation_decision(left, right, manifest["protocol"])
    if manifest["kind"] == "audit":
        decision = {**decision, "audit_finding": decision["state"], "state": "audit_complete", "promote": False}
    decision.update(kind=manifest["kind"], manifest=str(folder / "manifest.json"),
                    completed_games=completed, planned_games=len(jobs))
    write(folder / "decision.json", decision)
    write(folder / "status.json", decision)
    return decision


def latest_champion(root):
    paths = sorted((Path(root) / "champions").glob("V*.pt"), key=lambda p:int(p.stem[1:]))
    if not paths:
        raise ValueError("no champion")
    return paths[-1]


def promote_confirmed(root, folder):
    root, folder = Path(root), Path(folder)
    decision = json.loads((folder / "decision.json").read_text())
    manifest = json.loads((folder / "manifest.json").read_text())
    if manifest["kind"] != "confirmation" or decision["state"] != "confirmed_better":
        return None
    plan_path = folder / "promotion.json"
    if plan_path.exists():
        plan = json.loads(plan_path.read_text())
        target = Path(plan["champion"])
    else:
        current = latest_champion(root)
        if sha(current) != manifest["hashes"]["champion"]:
            write(folder / "status.json", {**decision, "state":"inconclusive", "reason":"champion changed since freezing"})
            return None
        target = root / "champions" / f"V{int(current.stem[1:])+1}.pt"
        plan = {"champion": str(target.resolve()), "candidate_sha256": manifest["hashes"]["candidate"],
                "confirmation": str(folder.resolve())}
        write(plan_path, plan)
    freeze_file(folder / "candidate.pt", target)
    write(folder / "status.json", {**decision, **plan, "state":"promoted"})
    return target


def audit_due(root, config, completed_cycles):
    protocol = ensure_protocol(root)
    every = protocol["audit_every_completed_cycles"]
    # Catch up a scheduled boundary after an interruption; never choose audit
    # timing based on the observed results.
    outcomes = []
    for milestone in range(every, completed_cycles+1, every):
        label = f"after-{milestone:04d}-cycles"
        folder = Path(root) / "evaluations" / "audits" / label
        if (folder / "decision.json").exists():
            outcomes.append(json.loads((folder / "decision.json").read_text()))
            continue
        if (folder / "manifest.json").exists():
            pass
        else:
            folder = prepare_batch(root, label, Path(root)/"evaluations/original_baseline.pt", latest_champion(root), config, "audit")
        outcomes.append(run_batch(folder))
    return outcomes


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--run-dir", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--label", required=True)
    parser.add_argument("--screen-cycle", type=int, required=True)
    args = parser.parse_args()
    import torch
    torch.set_num_threads(1)
    root = args.run_dir.resolve()
    storage.configure(root)
    with run_lock(root):
        config = json.loads((root/"config.json").read_text())
        protocol = ensure_protocol(root)
        screens = [json.loads(line) for line in (root/"evaluations/paired_seeds.jsonl").open()]
        screen = next(r for r in reversed(screens) if r["cycle"] == args.screen_cycle)
        if Path(screen["candidate_path"]).resolve() != args.candidate.resolve():
            raise ValueError("screen does not belong to this candidate")
        baseline = latest_champion(root)
        existing = root / "evaluations" / "confirmations" / args.label / "manifest.json"
        if existing.exists():
            baseline = Path(json.loads(existing.read_text())["source_champion"])
        if screen.get("model_hashes") and screen["model_hashes"] != {
                "champion":sha(baseline), "candidate":sha(args.candidate)}:
            raise ValueError("models differ from the screened checkpoints")
        screening = screen_decision(screen["champion"], screen["candidate"])
        if screening["state"] != "awaiting_confirmation":
            raise ValueError(f"candidate did not pass screen: {screening}")
        folder = prepare_batch(root,args.label,baseline,args.candidate,config)
        write(folder/"screen.json", {"cycle":args.screen_cycle,"decision":screening,"source":screen})
        previous = json.loads((root/"latest_status.json").read_text())
        write(root/"latest_status.json", {**previous,"phase":"confirming","confirmation_status":str(folder/"status.json"),
                                        "confirmation_manifest":str(folder/"manifest.json"),"updated_unix":time.time()})
        decision = run_batch(folder)
        promoted = promote_confirmed(root,folder)
        write(root/"latest_status.json", {**previous,"phase":"idle","champion":str(latest_champion(root)),
              "confirmation_decision":decision,"promoted":bool(promoted),"confirmation_status":str(folder/"status.json"),
              "updated_unix":time.time()})
        print(json.dumps(decision),flush=True)


if __name__ == "__main__":
    main()
