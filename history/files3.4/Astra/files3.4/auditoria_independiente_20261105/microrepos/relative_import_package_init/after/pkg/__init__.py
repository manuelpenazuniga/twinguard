from .guard import check as gate
from .guard import events
def run():
    protected(1)
def protected(x):
    events.append(["protected", x])
