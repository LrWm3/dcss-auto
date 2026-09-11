"""Small action-conditioned policy/value model for Crawl V1."""
from __future__ import annotations

import json
import copy
from pathlib import Path

import torch
from torch import nn

from features import ACTION_DIM, FEATURE_VERSION, STATE_DIM, state_features, action_features
from teacher import navigation_distances
import storage

MODEL_VERSION = "general-action-model-v2-separate-critic"


class ActionValueModel(nn.Module):
    def __init__(self, hidden: int = 192):
        super().__init__()
        self.hidden = hidden
        self.net = nn.Sequential(
            nn.Linear(STATE_DIM + ACTION_DIM, hidden), nn.LayerNorm(hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(), nn.Linear(hidden, 1),
        )
        # No shared parameters: absolute return regression must not rewrite
        # action logits or the bootstrap navigation representation.
        self.value_net = copy.deepcopy(self.net)

    def forward(self, state_action: torch.Tensor) -> torch.Tensor:
        return self.net(state_action).squeeze(-1)

    def value(self, state_action: torch.Tensor) -> torch.Tensor:
        return self.value_net(state_action).squeeze(-1)


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
    if payload.get("model_version") not in (MODEL_VERSION, "general-action-model-v1"):
        raise ValueError("unsupported model version")
    migrating = payload.get('feature_version') == 'general-features-v4-route-deltas'
    if payload.get("feature_version") != FEATURE_VERSION and not migrating:
        raise ValueError("feature version mismatch; bootstrap a new run")
    model = ActionValueModel(int(payload.get("hidden", 192)))
    weights = dict(payload["state_dict"])
    if payload["model_version"] == "general-action-model-v1":
        weights.update({"value_net." + key[4:]: value.clone()
                        for key, value in payload["state_dict"].items() if key.startswith("net.")})
    if migrating:
        for key in ('net.0.weight', 'value_net.0.weight'):
            old = weights[key]
            expanded = torch.zeros((old.shape[0], STATE_DIM + ACTION_DIM))
            expanded[:, :192] = old[:, :192]
            expanded[:, STATE_DIM:STATE_DIM+96] = old[:, 192:288]
            weights[key] = expanded
        payload = copy.deepcopy(payload)
        payload['metadata'] = dict(payload.get('metadata', {}))
        payload['metadata'].pop('optimizer_states', None)
        payload['metadata']['feature_migration'] = 'v4_to_v5_zero_initialized_properties'
    model.load_state_dict(weights)
    model.eval()
    return model, payload
