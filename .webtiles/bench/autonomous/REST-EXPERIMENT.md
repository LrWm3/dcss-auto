# REST-only experiment

`DCSS_REST_ONLY=1` removes WAIT entirely from newly generated RCs. REST is
available only below full HP, without visible hostile monsters, and when
Crawl's `you.feel_safe()` succeeds. Native rest retains normal interruptions;
it can consume many game turns per policy decision. It does not find a safer
tile first. Full HP with missing MP does not permit REST.

REST queues native `5`: synchronous CMD_REST followed by the bridge's normal
wake-up Escape canceled resting without spending a turn. REST now bypasses
that Escape. Live smoke verified rests spanning 5, 16, and 47 turns, and absence
of WAIT throughout, including full-HP and enemy-visible states. Enemy arrival
during rest has not yet been specifically demonstrated.

The V6 feature version gains `-rest-v1`; its WAIT kind slot becomes REST.
`try_rest_policy.py` explicitly initializes this slot from the prior checkpoint
without claiming the weights were trained on REST. Historical WAIT replay must
not be relabeled as REST training data. Checkpoint restore rejects a REST/WAIT
mode mismatch. Existing runs retain their original WAIT RCs.

Run with the tactical Python environment:

```
python try_rest_policy.py --initial artifacts/v6-health-repair-03/candidate.pt --output artifacts/v6-rest-only-01
```

This performs a live controller smoke test, then five fresh neural-policy games
on the prior five validation seeds, bounded at 2,000 decisions each. It does
not train or promote. Inspect `latest_status.json`, `smoke.json`, and
`games/results.json`. Compare official score, descents, death/cutoff, decision
counts AND final game turns: REST changes the decisions-to-turns ratio.
The old WAIT-dominated-cutoff gate is not an acceptance test for this experiment.
