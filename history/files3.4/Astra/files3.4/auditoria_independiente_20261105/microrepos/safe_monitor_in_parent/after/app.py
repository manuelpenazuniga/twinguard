events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def helper():
    protected(1)
def run():
    monitor(1)
    helper()
