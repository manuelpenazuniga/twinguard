events=[]
def monitor(): events.append('M')
def helper(): monitor()
def inner(): helper()
def run(): inner()
