events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])
def run():
    unused = lambda: monitor(1)
    protected(1)
