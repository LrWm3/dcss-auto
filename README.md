i# DCSS autonomous policy experiments

Research infrastructure for scripted Crawl play, reproducible tactical
encounters and general semantic-action neural policies. General-policy
improvement on held-out game score remains unproven.

`gpu-d1` contains a variant that runs between 100,000 and 200,000 decisions per second, and is essentially the basis of all actually interesting work. The other work is essentially just an example and simply doesn't work on consumer hardware because the 40 decisions per second it achieves is too slow for exploring methods of getting learning to work in this context.

Overall the experiments & the existing body of research indicate it is outside of the scope of today's RL methods to get anything close to a bot that can convincingly play even a vastly simplifed `dcss` on consumer grade hardware. But the findings and issues encountered along the are still interesting.

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
