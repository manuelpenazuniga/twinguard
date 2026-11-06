events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def guarded(fn):
    def wrapper():
        monitor(1)
        return fn()
    return wrapper
def run():
    protected(1)
