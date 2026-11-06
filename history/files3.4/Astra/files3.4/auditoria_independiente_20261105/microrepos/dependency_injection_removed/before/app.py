events = []
def monitor(x):
    events.append(["monitor", x])
def protected(x):
    events.append(["protected", x])

class Worker:
    def __init__(self, policy):
        self.policy = policy
    def work(self):
        self.policy(1)
        protected(1)
def run():
    Worker(monitor).work()
