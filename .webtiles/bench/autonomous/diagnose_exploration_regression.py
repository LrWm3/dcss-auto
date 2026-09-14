"""Read-only policy/replay diagnosis; writes only a diagnostic report."""
import os
for key in ('DCSS_EXPLORATION_SCORE', 'DCSS_HEALTH_FEATURES', 'DCSS_REST_ONLY', 'DCSS_VISIT_MEMORY'):
    os.environ[key] = '1'
os.environ['DCSS_REPRESENTATION'] = 'spatial-v6'
import json, gzip, statistics
from pathlib import Path
from collections import Counter
import torch
from model import load_model, tensor_for_actions
from teacher import _actions
from bootstrap_repair import write


def main():
    torch.set_num_threads(1)
    root = Path(__file__).parent/'artifacts/v6-exploration-training-02'
    base,_ = load_model(root/'initial.pt')
    candidate,_ = load_model(root/'candidate.pt')
    def compare(state):
        a = _actions(state); x = tensor_for_actions(state,a)
        with torch.no_grad():
            old, new = base(x), candidate(x)
        assert torch.isfinite(old).all() and torch.isfinite(new).all()
        result = {'kl_old_to_new': float((old.softmax(0)*(old.log_softmax(0)-new.log_softmax(0))).sum())}
        for name, logits in (('baseline',old),('candidate',new)):
            p = logits.softmax(0)
            result[name] = [{'label':a[i].get('label'), 'kind':a[i]['kind'],
                             'probability':float(p[i]), 'logit':float(logits[i])}
                            for i in logits.argsort(descending=True)[:4].tolist()]
        return result
    episodes = []
    for p in sorted((root/'candidate-games').glob('episode-*.result.json')):
        r = json.loads(p.read_text())
        item = {k:r.get(k) for k in ('seed','score','training_score','steps','action_counts','truncation_reason')}
        initial = json.loads((Path(r['work'])/'initial.json').read_text())
        item['initial'] = compare(initial)
        if r.get('resume_checkpoint'):
            s = json.loads((Path(r['resume_checkpoint'])/'case.json').read_text())['observation']
            item['cutoff'] = compare(s)
            item['last_actions'] = [h['action'].get('label') for h in s.get('history',[])]
            item['cutoff_native'] = s['score']
            item['cutoff_exploration'] = s['exploration_raw']
        episodes.append(item)
    anchors = []
    for path in sorted((root/'collection').glob('*/anchors.json.gz')):
        with gzip.open(path,'rt') as f:
            anchors.extend(json.load(f))
    # Audit the exact anchor subset/order used by fit, not just easy states.
    import random
    random.Random(17).shuffle(anchors)
    anchor_results = [compare(s) for s in anchors[:128]]
    wins = Counter(); pairs = Counter(); actions = Counter(); states=[]
    for path in sorted(root.glob('counterfactual-*.json.gz')):
        with gzip.open(path,'rt') as f: rows = json.load(f)
        valid = [r for r in rows if r.get('empirical_return') is not None]
        if not valid: continue
        best = max(r['empirical_return'] for r in valid)
        for r in valid:
            actions[r['action']['kind']] += 1
            if r['empirical_return'] == best: wins[r['action']['kind']] += 1
            for other in valid:
                if r['empirical_return'] > other['empirical_return']:
                    pairs[r['action']['kind']] += 1
        states.append({'case':valid[0]['case'], 'comparison':compare(valid[0]['observation']),
            'actions':[{'action':r['action']['label'],'mean':r['empirical_return'],
                        'scores':[o.get('training_score') for o in r['outcomes']],
                        'native_scores':[o.get('score') for o in r['outcomes']]} for r in valid]})
    report = {'episodes':episodes,'anchor_audit':{
        'count':len(anchor_results),
        'changed_greedy':sum(r['baseline'][0]['label']!=r['candidate'][0]['label'] for r in anchor_results),
        'mean_kl':statistics.mean(r['kl_old_to_new'] for r in anchor_results),
        'baseline_kinds':dict(Counter(r['baseline'][0]['kind'] for r in anchor_results)),
        'candidate_kinds':dict(Counter(r['candidate'][0]['kind'] for r in anchor_results))},
        'counterfactuals':{'evaluated_actions':dict(actions),'best_actions':dict(wins),
                           'winning_pairs':dict(pairs),'states':states}}
    write(root/'regression-diagnosis.json',report)
    print(json.dumps(report['anchor_audit'],indent=2))
    print('label counts',dict(wins),dict(pairs))
    for r in episodes[:4]:
        print('seed',r['seed'],'initial',r['initial'],'cutoff',r.get('cutoff'))


if __name__ == '__main__': main()
