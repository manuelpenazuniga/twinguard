"""Executes approved deploys through the injected deploy runner."""
from .events import Event, EventBus
from .policy import DeployRequest, DeployRunner


class ExternalExecutor:
    def __init__(self, bus: EventBus, runner: DeployRunner):
        self._bus = bus
        self._runner = runner
        bus.subscribe("deploy.approved", self.execute_deploy)

    def execute_deploy(self, event: Event) -> None:
        request: DeployRequest = event.payload
        deployment_id = self._runner.deploy(request)
        self._bus.publish("deploy.completed", request, deployment_id=deployment_id)
