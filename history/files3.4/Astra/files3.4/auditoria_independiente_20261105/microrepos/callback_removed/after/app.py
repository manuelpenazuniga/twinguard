events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

def invoke(fn):
    fn(1)
def run():
    protected(1)
