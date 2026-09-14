# Visit-memory counterfactual experiment

`DCSS_VISIT_MEMORY=1` adds eight action-conditioned features to V6 REST mode:
memory presence, whether the destination was visited, log visit count, age of
its last arrival, current-tile visit count, decisions since map discovery,
decisions since a new visited tile, and remembered visited-tile count.

The bounded 4,096-tile floor-local memory follows observed displacement, not
assumed command movement. Stationary resting/combat does not count as another
arrival. Floor changes and ambiguous displacement reset memory. Snapshots
persist this Python-side state alongside the Crawl save. This is explicit
memory, not a recurrent network or a persistent navigation-goal controller.

The version suffix is `-visits-v1`. Migration from the REST checkpoint appends
zero-weight input columns to both policy and critic, preserving the original
policy before training. Historical data is not fabricated to contain visits.

`try_visit_memory.py` collects greedy policy rollouts on eight training seeds
(60917000–60917007), up to 600 decisions each. It saves the first safe two-tile
loop with at least 24 decisions without new tiles/discovery. The reserved
evaluation seeds and their already-observed looping checkpoints are NOT used
for fitting or counterfactual labels.

For each captured state, test top-3 policy actions, two random alternatives,
and the bootstrap teacher's suggestion if not already included. Each first
action gets three 384-decision continuations using the original policy with
15% uniform legal-action exploration. All branches restore identical engine
RNG; paired policy-sampling seeds supply stochastic continuations. These are
not independently resampled worlds or advanced-engine-RNG experiments.

The only preference target is mean official game score at death or cutoff.
Invalid continuation sets are excluded; score ties do not become labels.
Training uses pairwise preferences and a small original-policy KL anchor on
training states. There are no direction bans, novelty rewards, or handcrafted
exploration targets. If every action ties, the run reports no training signal.

After training, run initial and candidate policies on the same five reserved
screen seeds, at most 2,000 decisions each, recording score, descent, deaths,
and cutoffs. Training-ordering improvement is not gameplay improvement; this
small screen cannot justify promotion. No automatic promotion occurs.

Run via the tactical Python environment:

```
python try_visit_memory.py --initial artifacts/v6-rest-only-01/rest-initial.pt --output artifacts/v6-visits-01
```

The output directory must be new; this bounded experiment does not resume an
interrupted partial run. It retains snapshots, compressed labels, candidate,
paired results, and `latest_status.json`. The 20 GiB free-space pause applies.
`--smoke-only` collects four seeds and checks full observation/visit-memory
determinism over two restored eight-action continuations, without fitting.
