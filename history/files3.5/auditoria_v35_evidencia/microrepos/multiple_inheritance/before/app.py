events=[]
def protected(): events.append('P')
class A:
    def check(self): events.append('M')
class B(A): pass
class C(A):
    def check(self): pass
class D(B):
    def run(self):
        self.check()
        protected()
def run(): D().run()
