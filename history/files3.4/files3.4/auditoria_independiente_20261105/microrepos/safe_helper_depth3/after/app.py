events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def helper2():
    monitor(1)
def helper1():
    helper2()
def run():
    helper1()
    protected(1)
