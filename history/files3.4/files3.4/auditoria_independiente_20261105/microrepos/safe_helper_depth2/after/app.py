events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def helper():
    monitor(1)
def run():
    helper()
    protected(1)
