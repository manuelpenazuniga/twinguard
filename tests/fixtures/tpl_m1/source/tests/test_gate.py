from gate.monitor import Decision, PolicyTimeout, process


class SlowPolicy:
    def evaluate(self, request):
        raise PolicyTimeout()


class Recorder:
    def __init__(self):
        self.done = []

    def execute(self, request):
        self.done.append(request)


def test_timeout_finishes_cleanly():
    assert isinstance(process("r1", SlowPolicy(), Recorder()), Decision)


def test_allowed_request_runs():
    class Yes:
        def evaluate(self, request):
            return True
    rec = Recorder()
    assert process("r2", Yes(), rec) is Decision.ALLOW and rec.done == ["r2"]
