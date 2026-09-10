"""Administrative cutoffs, never synthetic deaths or reward penalties."""
from collections import Counter


class DecisionBudget:
    def __init__(self, per_floor=2000, total=100000, no_turn=16):
        if min(per_floor, total, no_turn) < 1:
            raise ValueError("decision limits must be positive")
        self.per_floor, self.total_limit, self.no_turn_limit = per_floor, total, no_turn
        self.floors = Counter()
        self.total = self.no_turn = 0

    def reason(self, state):
        if state.get("terminal"):
            return None
        if self.no_turn >= self.no_turn_limit:
            return "no_game_time_progress"
        if self.total >= self.total_limit:
            return "total_decision_limit"
        if self.floors[str(state.get("level", "unknown"))] >= self.per_floor:
            return "floor_decision_limit"
        return None

    def record(self, before, after):
        self.total += 1
        self.floors[str(before.get("level", "unknown"))] += 1
        self.no_turn = self.no_turn + 1 if after.get("turn") == before.get("turn") else 0

    def summary(self):
        return {"per_floor_limit": self.per_floor, "total_limit": self.total_limit,
                "no_turn_limit": self.no_turn_limit, "decisions_by_floor": dict(self.floors),
                "total_decisions": self.total, "consecutive_no_turn": self.no_turn}
