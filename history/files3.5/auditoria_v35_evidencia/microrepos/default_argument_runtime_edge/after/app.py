events=[]
def monitor(): events.append('M')
def protected(): events.append('P')
def run(token=monitor()):
    protected()
