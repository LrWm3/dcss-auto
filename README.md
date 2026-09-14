# DCSS autonomous policy experiments

Research infrastructure for scripted Crawl play, reproducible tactical
encounters and general semantic-action neural policies. General-policy
improvement on held-out game score remains unproven.

- [Experimental ledger](.webtiles/bench/EXPERIMENT-LEDGER.md): attempted approaches,
  results, failures, evidence and historical limitations.
- [General-policy system](.webtiles/bench/autonomous/README.md): current training
  infrastructure and experiment-specific commands.
- [Tactical laboratory](.webtiles/bench/tactical/README.md): archived controllers,
  datasets and simulator benchmarks retained as regression infrastructure.
- [Repository/storage policy](REPOSITORY.md): what belongs in Git and how to
  avoid checking in hundreds of gigabytes of generated data.
- [Engine reconstruction](engine/README.md): pinned upstream plus cumulative
  source patch; compiled binaries and the local engine checkout are not vendored.

This is a research checkout, not a trained agent distribution. Model weights,
saved game datasets and large run artifacts are local-only and need a separate
backup if they must survive loss of the workstation. Historical file links may
refer to the original workstation and are not portable remote URLs.
