"""Monthly budget envelope for one cloud account."""


class BudgetEnvelope:
    def __init__(self, account, limit, committed=0.0, warn_ratio=0.8):
        if limit <= 0:
            raise ValueError("limit must be positive")
        if not 0 < warn_ratio < 1:
            raise ValueError("warn_ratio must be between 0 and 1")
        self.account = account
        self.limit = float(limit)
        self.committed = float(committed)
        self.warn_ratio = warn_ratio

    def projected(self, cost):
        return self.committed + cost

    def exceeds(self, cost):
        return self.projected(cost) > self.limit

    def near_limit(self, cost):
        return self.projected(cost) >= self.limit * self.warn_ratio

    def reserve(self, cost):
        self.committed += cost
        return self.committed

    def remaining(self):
        return max(self.limit - self.committed, 0.0)
