"""Reproduce policy/return interference and build an isolated-critic challenger."""
import argparse
import copy
import json
import random
from collections import Counter
from pathlib import Path

import torch
from model import load_model, save_model, tensor_for_actions
from train_model import rows_from_replay, train_behavioral_clone, train_q_finetune, train_counterfactual_preferences
import storage


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("source", type=Path)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    torch.set_num_threads(1)
    args.output.mkdir(parents=True, exist_ok=False)
    storage.configure(args.output)
    rows = [r for r in rows_from_replay(args.source / "replay")
            if ":counterfactual" not in r.get("policy_version", "")]
    base, provenance = load_model(args.source / "champions/V0.pt")
    rng = random.Random(51)
    sample = rng.sample(rows, min(256, len(rows)))
    tensors = [tensor_for_actions(r["observation"], r["observation"]["actions"]) for r in sample]
    def choices(model):
        with torch.no_grad():
            return [int(model(x).argmax()) for x in tensors]
    original = choices(base)
    def measure(model):
        selected = choices(model)
        return {"agreement_with_V0": sum(a == b for a,b in zip(original, selected))/len(sample),
                "action_counts": dict(Counter(r["observation"]["actions"][i]["kind"]
                                              for r,i in zip(sample, selected)))}
    report = {"V0_metadata": provenance["metadata"], "rows":len(rows),
              "diagnostic_sample":len(sample), "V0":measure(base)}
    def persist():
        (args.output / "update_diagnostics.json").write_text(json.dumps(report, indent=2)+"\n")
        print(json.dumps(report), flush=True)
    save_model(args.output / "baseline.pt", base, {"source":str(args.source / "champions/V0.pt")})
    persist()
    model, bc = train_behavioral_clone(rows, epochs=2, seed=len(rows), model=copy.deepcopy(base))
    report["after_anchored_BC"] = {**measure(model), "training":bc}
    save_model(args.output / "after_bc.pt", model, bc)
    persist()
    # Reproduce the old objective on the same BC policy and return rows.
    legacy = copy.deepcopy(model)
    optimizer = torch.optim.AdamW(legacy.net.parameters(), lr=5e-4, weight_decay=1e-5)
    import math
    for row in rows:
        if row.get("return") is None:
            continue
        state = row["observation"]
        prediction = legacy(tensor_for_actions(state, state["actions"]))[row["action_index"]]
        loss = (prediction-math.log1p(max(0, row["return"])))**2
        optimizer.zero_grad(); loss.backward(); optimizer.step()
    report["after_legacy_score_update"] = measure(legacy)
    save_model(args.output / "legacy_ablation.pt", legacy, {"diagnostic_only":True})
    persist()
    actor_weights = {k:v.clone() for k,v in model.net.state_dict().items()}
    critic = train_q_finetune(model, rows)
    assert all(torch.equal(v, model.net.state_dict()[k]) for k,v in actor_weights.items())
    report["after_separate_critic"] = {**measure(model), "training":critic,
                                      "actor_parameters_bitwise_unchanged":True}
    cf = []
    for line in (args.source / "rollouts/counterfactual_results.jsonl").open():
        r=json.loads(line)
        cf.append({"observation":r["observation"], "action_index":r["action_index"],
                   "return":r["empirical_return"]})
    report["preference_update"] = train_counterfactual_preferences(model, cf, anchors=rows)
    report["final_candidate"] = measure(model)
    save_model(args.output / "candidate.pt", model, report)
    persist()


if __name__ == "__main__":
    main()
