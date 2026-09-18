"""Positive-state minGRU with stable parallel training and sequential rollout.

Sequences must not cross episode boundaries. The existing collector stores one
life per sequence, with initial burn-in padding and terminal loss padding.
"""
import torch
from torch import nn
from symbolic_fast import FastSymbolicPolicy


class MinGRU(nn.Module):
    def __init__(self, input_dim, hidden_dim, scan_backend="eager"):
        super().__init__()
        if scan_backend not in ("eager", "triton"):
            raise ValueError(scan_backend)
        self.scan_backend = scan_backend
        self.hidden_dim = hidden_dim
        self.linear = nn.Linear(input_dim, 2 * hidden_dim, bias=False)

    def _project(self, x):
        candidate, gate = self.linear(x).chunk(2, dim=-1)
        # Keep recurrent arithmetic in FP32 under autocast, preserving FP64 tests.
        if candidate.dtype in (torch.float16, torch.bfloat16):
            candidate, gate = candidate.float(), gate.float()
        return candidate, gate

    def forward(self, x, h=None):
        if self.scan_backend == "triton":
            from mingru_scan import scan
            return scan(self.linear(x[:, None]), None if h is None else h.float())[:, 0]
        candidate, gate = self._project(x)
        candidate = torch.where(candidate >= 0, candidate + .5, candidate.sigmoid())
        if h is None:
            h = torch.zeros_like(candidate)
        # Separate sigmoid(-gate) avoids cancellation in 1 - sigmoid(gate).
        return (-gate).sigmoid() * h + gate.sigmoid() * candidate

    def sequence(self, x, h=None):
        if x.ndim != 3 or x.shape[1] == 0:
            raise ValueError('Expected a nonempty [batch, time, features] sequence')
        if self.scan_backend == "triton":
            from mingru_scan import scan
            states = scan(self.linear(x), h)
            return states, states[:, -1]
        candidate, gate = self._project(x)
        # Inclusive affine prefix scan. Composing (a,b) with (c,d) gives
        # (a*c, b+a*d). Unlike the log-cumsum-exp formulation, this never
        # subtracts large cumulative logs or exponentiates large values.
        a = (-gate).sigmoid()
        candidate = torch.where(candidate >= 0, candidate + .5, candidate.sigmoid())
        b = gate.sigmoid() * candidate
        offset = 1
        while offset < x.shape[1]:
            b = torch.cat([b[:, :offset], b[:, offset:] + a[:, offset:] * b[:, :-offset]], dim=1)
            a = torch.cat([a[:, :offset], a[:, offset:] * a[:, :-offset]], dim=1)
            offset *= 2
        states = b if h is None else b + a * h.unsqueeze(1)
        return states, states[:, -1]


class MinSymbolicPolicy(FastSymbolicPolicy):
    def __init__(self, scan_backend="eager"):
        super().__init__(True)
        del self.sequence_core
        self.core = MinGRU(194, 128, scan_backend)

    def sequence(self, x, h=None):
        return self.core.sequence(x, h)
