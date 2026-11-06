events = []
def monitor(x):
    pass
def protected(x):
    events.append(["protected", x])

def run():
    monitor(1)
    protected(1)
