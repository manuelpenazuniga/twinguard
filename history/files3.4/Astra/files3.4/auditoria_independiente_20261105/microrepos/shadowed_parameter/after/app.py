events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def do_nothing(x):
    pass
def execute(monitor):
    monitor(1)
    protected(1)
def run():
    execute(do_nothing)
