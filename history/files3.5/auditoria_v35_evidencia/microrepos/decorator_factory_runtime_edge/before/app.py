events=[]
def monitor():
    events.append('M')
    return lambda f:f
def protected(): events.append('P')
def run():
    monitor()
    protected()
