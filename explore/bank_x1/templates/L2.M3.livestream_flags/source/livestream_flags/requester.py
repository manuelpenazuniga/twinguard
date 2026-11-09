"""Queue worker that applies requested actions to livestreams."""
from collections import deque

from .models import Action, ActionRequest


class ActionRequester:
    """Drains the request queue, reviewing each request before it is applied.

    ``controller`` is the stream controller client (``keep_live`` / ``restart``);
    ``monitor`` is the RiskMonitor that reviews every request.
    """

    def __init__(self, queue, controller, monitor):
        self.queue = deque(queue)
        self.controller = controller
        self.monitor = monitor
        self.applied = []

    def process(self, request: ActionRequest):
        self.monitor.review(request)
        handlers = {
            Action.KEEP_LIVE: self.controller.keep_live,
            Action.RESTART: self.controller.restart,
        }
        handlers[request.action](request.stream_id)
        self.applied.append(request.request_id)
        return request.request_id

    def process_queue(self):
        done = []
        while self.queue:
            done.append(self.process(self.queue.popleft()))
        return done
