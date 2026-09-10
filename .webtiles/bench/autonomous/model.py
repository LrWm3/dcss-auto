"""Small action-conditioned policy/value model for Crawl V1."""
from __future__ import annotations

import json
from pathlib import Path

import torch
from torch import nn

from features import ACTION_DIM, FEATURE_VERSION, STATE_DIM, state_features, action_features
from teacher import navigation_distances
import storage

MODEL_VERSION = "general-action-model-v1"


class ActionValueModel(nn.Module):
    def __init__(self, hidden: int = 192):
        super().__init__()
        self.hidden = hidden
        self.net = nn.Sequential(
            nn.Linear(STATE_DIM + ACTION_DIM, hidden), nn.LayerNorm(hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1),
        )

    def forward(self, state_action: torch.Tensor) -> torch.Tensor:
        return self.net(state_action).squeeze(-1)


def tensor_for_actions(state: dict, actions: list[dict]) -> torch.Tensor:
    base = state_features(state)
    routes = [navigation_distances(state, stairs) for stairs in (False, True)]
    return torch.tensor([base + action_features(state, action, routes) for action in actions],
                        dtype=torch.float32)


def action_scores(model: ActionValueModel, state: dict, actions: list[dict]) -> torch.Tensor:
    if not actions:
        return torch.empty(0)
    with torch.no_grad():
        return model(tensor_for_actions(state, actions))


def save_model(path: str | Path, model: ActionValueModel, metadata: dict | None = None) -> None:
    storage.guard()
    payload = {
        "model_version": MODEL_VERSION,
        "feature_version": FEATURE_VERSION,
        "state_dim": STATE_DIM,
        "action_dim": ACTION_DIM,
        "hidden": model.hidden,
        "state_dict": model.state_dict(),
        "metadata": metadata or {},
    }
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    temporary = Path(path).with_name(Path(path).name + ".tmp")
    torch.save(payload, temporary)
    temporary.replace(path)


def load_model(path: str | Path) -> tuple[ActionValueModel, dict]:
    payload = torch.load(path, map_location="cpu", weights_only=False)
    if payload.get("model_version") != MODEL_VERSION:
        raise ValueError("unsupported model version")
    if payload.get("feature_version") != FEATURE_VERSION:
        raise ValueError("feature version mismatch; bootstrap a new run")
    model = ActionValueModel(int(payload.get("hidden", 192)))
    model.load_state_dict(payload["state_dict"])
    model.eval()
    return model, payload
