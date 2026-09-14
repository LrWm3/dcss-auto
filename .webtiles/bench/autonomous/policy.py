"""Policy selection over the action list supplied by Crawl."""
from __future__ import annotations

import random

from model import ActionValueModel, action_scores, load_model


class Policy:
    def __init__(self, model: ActionValueModel, epsilon: float = 0.05,
                 rng: random.Random | None = None):
        self.model = model
        self.epsilon = epsilon
        self.rng = rng or random.Random(0)

    @classmethod
    def from_checkpoint(cls, path, epsilon=0.05, seed=0):
        model, metadata = load_model(path)
        return cls(model, epsilon, random.Random(seed)), metadata

    def choose(self, state: dict, teacher_index: int | None = None) -> tuple[int, dict]:
        actions = state.get("actions", [])
        if isinstance(actions, dict):
            actions = [actions[key] for key in sorted(actions, key=lambda x: int(x))]
        if not actions:
            raise ValueError("no legal semantic actions")
        scores = action_scores(self.model, state, actions)
        greedy = int(scores.argmax().item())
        if teacher_index is None:
            pool = list(range(len(actions)))
            self.last_exploration_mode = "greedy"
        else:
            ranked = list(reversed(scores.argsort().tolist()))
            pool = ranked[:min(4, len(ranked))]
            if 0 <= int(teacher_index) < len(actions):
                pool.append(int(teacher_index))
            for candidate in self.rng.sample(list(range(len(actions))), len(actions)):
                if candidate not in pool:
                    pool.append(candidate)
                    break
            pool = list(dict.fromkeys(pool))
            self.last_exploration_mode = "greedy"
        self.last_exploration_pool = pool
        if self.rng.random() < self.epsilon:
            if teacher_index is None:
                # Preserve the old uniform behavior for evaluation helpers and
                # callers that do not have a teacher suggestion.
                self.last_exploration_mode = "uniform"
            else:
                # Exploration should produce useful disagreements, not mostly
                # arbitrary menu or movement deaths. Include the policy's top
                # actions, the bootstrap teacher, and one reproducible legal
                # alternative outside the top set.
                self.last_exploration_mode = "structured"
            index = self.rng.choice(pool)
            self.last_exploration_pool = pool
        else:
            index = greedy
        exploratory_probability = self.epsilon / len(self.last_exploration_pool)
        self.last_action_probability = exploratory_probability + (
            1 - self.epsilon if index == greedy else 0)
        return index, actions[index]
