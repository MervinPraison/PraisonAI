from praisonai.scheduler import DeploymentScheduler


class _NoopDeployer:
    def deploy(self) -> bool:
        return True


def test_deployment_scheduler_start_and_stop():
    scheduler = DeploymentScheduler()
    scheduler.set_deployer(_NoopDeployer())

    assert scheduler.start("60") is True
    assert scheduler.is_running is True

    assert scheduler.stop() is True
    assert scheduler.is_running is False
