"""Conservative, paired rollout preferences and bounded policy updates."""
import copy
import math
import random
import statistics

import torch

from exploration_score import learning_score
from model import tensor_for_actions
from teacher import _actions


def credible_pair(a, b):
    """One-sided 95% paired t screen, plus a 1% practical margin.

    This is a noise filter, not a multiple-comparison improvement claim.
    Missing/error outcomes and mixed objectives cannot supply preferences.
    """
    if a.get('empirical_return') is None or b.get('empirical_return') is None:
        return False
    aa, bb = a.get('outcomes', []), b.get('outcomes', [])
    if len(aa) != len(bb) or len(aa) < 3:
        return False
    if len({x.get('score_version') for x in aa + bb}) != 1:
        return False
    if any(x.get('error') or x.get('score_status') not in
           ('final_official', 'cutoff_official') for x in aa + bb):
        return False
    values = [learning_score(x) for x in aa + bb]
    if any(v is None or not math.isfinite(v) for v in values):
        return False
    av, bv = values[:len(aa)], values[len(aa):]
    differences = [x-y for x, y in zip(av, bv)]
    n = len(differences)
    # Conservative table buckets (df below the actual df).
    critical = 2.920 if n < 6 else 2.015 if n < 11 else 1.813 if n < 31 else 1.697
    lower = statistics.mean(differences) - critical * statistics.stdev(differences) / math.sqrt(n)
    margin = max(1., .01 * max(abs(statistics.mean(av)), abs(statistics.mean(bv))))
    return lower > margin


def ranking_groups(groups):
    result = []
    for rows in groups:
        pairs = [(a['action_index'], b['action_index']) for a in rows for b in rows
                 if a is not b and credible_pair(a, b)]
        if pairs:
            result.append((rows[0]['observation'], pairs))
    return result


def within_budget(audit):
    return (audit['mean_kl'] <= .02 and audit['max_kl'] <= .15
            and audit['changed_fraction'] <= .05)


def bounded_fit(model, groups, anchors, epochs=8):
    ranking = ranking_groups(groups)
    if not ranking:
        return {'trained': False, 'reason': 'no confident paired preferences'}
    cache = [(tensor_for_actions(s, _actions(s)), pairs) for s, pairs in ranking]
    # Include all available training anchors AND the branch states. No eval data.
    references = []
    for s in list(anchors) + [s for s, _ in ranking]:
        x = tensor_for_actions(s, _actions(s))
        with torch.no_grad():
            references.append((x, model(x).softmax(0).detach()))

    def audit():
        with torch.no_grad():
            kls, changed = [], 0
            for x, p in references:
                logits = model(x)
                kls.append(float(torch.nn.functional.kl_div(logits.log_softmax(0), p, reduction='sum')))
                changed += int(logits.argmax() != p.argmax())
            return {'mean_kl': statistics.mean(kls), 'max_kl': max(kls),
                    'changed_fraction': changed / len(references), 'references': len(references)}

    def agreement():
        with torch.no_grad():
            correct = total = 0
            for x, pairs in cache:
                logits = model(x)
                correct += sum(int(logits[a] > logits[b]) for a, b in pairs)
                total += len(pairs)
            return {'correct': correct, 'total': total, 'fraction': correct / total}

    before = agreement()
    optimizer = torch.optim.AdamW(model.net.parameters(), lr=2e-5, weight_decay=0)
    rng = random.Random(17)
    history = []
    accepted = 0
    for epoch in range(epochs):
        saved = copy.deepcopy(model.state_dict())
        rng.shuffle(cache)
        for x, pairs in cache:
            optimizer.zero_grad()
            logits = model(x)
            loss = torch.stack([torch.nn.functional.softplus(logits[b]-logits[a]) for a,b in pairs]).mean()
            penalties = [torch.nn.functional.kl_div(model(ax).log_softmax(0), ap, reduction='sum')
                         for ax, ap in rng.sample(references, min(8, len(references)))]
            loss = loss + torch.stack(penalties).mean()
            loss.backward()
            torch.nn.utils.clip_grad_norm_(model.net.parameters(), 1.)
            optimizer.step()
        measured = audit()
        keep = within_budget(measured)
        history.append({'epoch': epoch+1, **measured, 'accepted': keep})
        if not keep:
            model.load_state_dict(saved)
            break
        accepted += 1
    model.eval()
    return {'trained': accepted > 0, 'accepted_epochs': accepted,
            'informative_states': len(ranking), 'before': before, 'after': agreement(),
            'audit': audit(), 'epochs': history, 'protocol': 'paired-noise-filter-bounded-kl-v1',
            'warning': 'reference bounds do not guarantee generalization; rollout gate required'}
