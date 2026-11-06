events = []
def protected(x):
    events.append(["protected", x])
class Base:
    def check(self, x):
        events.append(["monitor", x])
class Unrelated:
    def check(self, x):
        return False
class Worker(Base):
    def work(self):
        self.check(1)
        protected(1)
def run():
    Worker().work()
