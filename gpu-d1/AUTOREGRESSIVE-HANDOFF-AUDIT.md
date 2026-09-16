# Early PPO handoff audit

Replay from preserved controller-imitation checkpoint. First test the frozen
policy on the actual training distribution (512 worlds, 256 maps, clumped
placement), then isolate 30 PPO updates per condition: normal, no entropy,
value loss only, policy loss only. Each update uses 512 worlds x 64 decisions,
four optimizer epochs, and original optimizer/GAE settings. Each condition resets
model, optimizer, environment and RNG; sampled evaluations preserve training RNG.

A fixed 128-placement diagnostic panel spans 32 validation layouts. Evaluate
before training and after updates 1, 2, 4, 8, 16, 24 and 30. These are diagnostic
comparisons, not full-panel final-policy selection. Log training episode outcomes,
values, advantages, losses, gradient norms, policy KL and probability changes.
Check stored versus recomputed pre-update log probabilities, legal actions,
clear-only reward aggregation, terminal flags, and physical-turn accounting.

Script: diagnostics/autoregressive-imitation/handoff_audit.py. Raw results:
results/autoregressive-handoff-audit.json. No changes to production trainers or
original checkpoints. No diagnostic model checkpoints or rollout datasets saved.
