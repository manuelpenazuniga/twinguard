"""Hourly rate card used to quote resource requests."""

DEFAULT_RATES = {
    "c6.large": 0.085,
    "c6.xlarge": 0.17,
    "m6.2xlarge": 0.384,
    "r6.4xlarge": 1.008,
    "g5.12xlarge": 5.672,
}


class RateCard:
    def __init__(self, rates=None):
        self._rates = dict(DEFAULT_RATES if rates is None else rates)

    def rate(self, instance_type):
        try:
            return self._rates[instance_type]
        except KeyError:
            raise ValueError(f"no rate for instance type {instance_type!r}") from None

    def quote(self, request):
        """Cost in USD of running the request for its full duration."""
        if request.count <= 0 or request.hours <= 0:
            raise ValueError(f"{request.request_id}: count and hours must be positive")
        return round(self.rate(request.instance_type) * request.count * request.hours, 2)
