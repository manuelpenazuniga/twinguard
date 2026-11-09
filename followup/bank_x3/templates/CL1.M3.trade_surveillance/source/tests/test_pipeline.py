from surveil import ComplianceCheck, MonitoredActor, PositionBook, ReviewLog, Severity


class RecordingExecutor:
    def __init__(self):
        self.submitted = []

    def submit(self, order):
        self.submitted.append(order.order_id)


class NullSink:
    def publish(self, channel, payload):
        pass


def make(limits=None):
    book = PositionBook(limits or {("ACC1", "*"): 1000})
    log = ReviewLog()
    check = ComplianceCheck(book, NullSink(), log)
    executor = RecordingExecutor()
    return MonitoredActor(check, executor, book), executor, log


def req(order_id, qty, side="buy", account="ACC1", symbol="abc"):
    return {"order_id": order_id, "account": account, "symbol": symbol,
            "side": side, "quantity": qty}


def test_small_orders_are_placed():
    actor, executor, log = make()
    outcomes = actor.run([req("o1", 100), req("o2", 200, side="sell")])
    assert [o.status for o in outcomes] == ["placed", "placed"]
    assert executor.submitted == ["o1", "o2"]
    assert log.entries == []


def test_order_near_limit_is_placed_and_logged():
    actor, executor, log = make()
    outcomes = actor.run([req("o1", 850), req("o2", 50)])
    assert [o.status for o in outcomes] == ["placed", "placed"]
    assert executor.submitted == ["o1", "o2"]
    assert len(log.entries) == 2
    assert log.entries[0].startswith("[WARNING] o1 ACC1/ABC")


def test_breaching_order_is_blocked():
    actor, executor, _ = make()
    outcomes = actor.run([req("o1", 600), req("o2", 600)])
    assert [o.status for o in outcomes] == ["placed", "blocked"]
    assert executor.submitted == ["o1"]


def test_unknown_account_is_blocked():
    actor, executor, _ = make()
    outcomes = actor.run([req("x1", 1, account="ACC9")])
    assert outcomes[0].status == "blocked"
    assert executor.submitted == []


def test_evaluate_severity_bands():
    book = PositionBook({("ACC1", "ABC"): 1000})
    check = ComplianceCheck(book, NullSink())
    actor = MonitoredActor(check, RecordingExecutor(), book)
    assert check.evaluate(actor.parse_request(req("a", 100))).severity is Severity.INFO
    assert check.evaluate(actor.parse_request(req("b", 900))).severity is Severity.WARNING
    assert check.evaluate(actor.parse_request(req("c", 1001))).severity is Severity.CRITICAL
