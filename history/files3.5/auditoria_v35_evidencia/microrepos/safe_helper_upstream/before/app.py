events=[]
def monitor(): events.append('M')
def inner(): monitor()
def run(): inner()
