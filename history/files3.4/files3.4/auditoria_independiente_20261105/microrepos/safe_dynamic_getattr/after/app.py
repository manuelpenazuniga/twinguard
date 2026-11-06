events = []
def protected(x):
    events.append(["protected", x])
class Monitor:
    def check(self, x):
        events.append(["monitor", x])
def run():
    m = Monitor()
    getattr(m, "check")(1)
    protected(1)
