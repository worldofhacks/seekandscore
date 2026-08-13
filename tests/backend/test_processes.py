"""Worker, scheduler, and entrypoint behavior tests."""

import pytest

from seekandscore.api.__main__ import main as api_main
from seekandscore.platform.settings import Settings
from seekandscore.scheduler.__main__ import main as scheduler_main
from seekandscore.scheduler.runtime import SchedulerRuntime
from seekandscore.worker.__main__ import main as worker_main
from seekandscore.worker.runtime import QueueName, WorkerRuntime, parse_queues


def test_api_configuration_check() -> None:
    assert api_main(["--check"]) == 1


def test_queue_parser_rejects_unknown_and_duplicate_names() -> None:
    assert parse_queues("acquire,parse") == (QueueName.ACQUIRE, QueueName.PARSE)
    with pytest.raises(ValueError, match="unknown queue"):
        parse_queues("unknown")
    with pytest.raises(ValueError, match="must be unique"):
        parse_queues("score,score")


def test_worker_blocks_external_effect_queues_by_default() -> None:
    runtime = WorkerRuntime(
        Settings(app_env="test"),
        (QueueName.ACQUIRE, QueueName.PARSE, QueueName.ENGAGE, QueueName.SCORE),
    )

    report = runtime.run_cycle()

    assert report.runnable_queues == ("score",)
    assert report.blocked_queues == ("acquire", "parse", "engage")
    assert report.jobs_claimed == 0


def test_worker_once_command_is_runnable() -> None:
    assert worker_main(["--queues", "acquire,parse", "--once"]) == 0


def test_scheduler_skips_external_effects_by_default() -> None:
    report = SchedulerRuntime(Settings(app_env="test")).dispatch_due()

    assert report.requested == 0
    assert report.dispatched == 0
    assert report.skipped == (
        "ingestion_disabled",
        "external_alert_delivery_disabled",
        "outreach_send_disabled",
    )


def test_scheduler_commands_are_runnable() -> None:
    assert scheduler_main(["check"]) == 0
    assert scheduler_main(["dispatch-due"]) == 0
