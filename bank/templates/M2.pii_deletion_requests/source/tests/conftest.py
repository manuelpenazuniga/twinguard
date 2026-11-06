import pytest

from erasure.store_api import ErasureReceipt


class FakeRecordStore:
    """In-memory record store exposing the client 2.0 API only."""

    ROWS_PER_TABLE = 2

    def __init__(self):
        self.specs = []

    def erase(self, spec):
        self.specs.append(spec)
        return ErasureReceipt(
            erasure_id=f"er-{len(self.specs):04d}",
            customer_id=spec.customer_id,
            rows_erased=self.ROWS_PER_TABLE * len(spec.tables),
        )


@pytest.fixture
def store():
    return FakeRecordStore()


@pytest.fixture
def audit_events():
    return []


def message(request_id, customer_id, tables=("customers",), **extra):
    data = {
        "request_id": request_id,
        "customer_id": customer_id,
        "tables": list(tables),
        "reason": "gdpr_art17",
        "identity_verified": True,
        "submitted_by": "privacy-portal",
    }
    data.update(extra)
    return data
