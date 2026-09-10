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

    def choose(self, state: dict) -> tuple[int, dict]:
        actions = state.get("actions", [])
        if isinstance(actions, dict):
            actions = [actions[key] for key in sorted(actions, key=lambda x: int(x))]
        if not actions:
            raise ValueError("no legal semantic actions")
        if self.rng.random() < self.epsilon:
            index = self.rng.randrange(len(actions))
        else:
            index = int(action_scores(self.model, state, actions).argmax().item())
        return index, actions[index]
