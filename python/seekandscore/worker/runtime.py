"""Queue worker lifecycle with external effects disabled by configuration."""

import logging
import signal
import threading
from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum

from seekandscore.platform.settings import AlertDeliveryMode, Settings

logger = logging.getLogger(__name__)


class QueueName(StrEnum):
    ACQUIRE = "acquire"
    PARSE = "parse"
    RESOLVE = "resolve"
    GEO = "geo"
    MARKET = "market"
    SCORE = "score"
    DELIVER = "deliver"
    ENGAGE = "engage"


@dataclass(frozen=True, slots=True)
class CycleReport:
    queues: tuple[str, ...]
    runnable_queues: tuple[str, ...]
    blocked_queues: tuple[str, ...]
    jobs_claimed: int = 0
    jobs_completed: int = 0


def parse_queues(value: str) -> tuple[QueueName, ...]:
    names = tuple(part.strip() for part in value.split(",") if part.strip())
    if not names:
        raise ValueError("at least one queue is required")
    try:
        parsed = tuple(QueueName(name) for name in names)
    except ValueError as error:
        allowed = ", ".join(queue.value for queue in QueueName)
        raise ValueError(f"unknown queue; expected one of: {allowed}") from error
    if len(set(parsed)) != len(parsed):
        raise ValueError("queue names must be unique")
    return parsed


class WorkerRuntime:
    """A safe polling shell ready for durable job adapters in a later slice."""

    def __init__(self, settings: Settings, queues: Iterable[QueueName]) -> None:
        self.settings = settings
        self.queues = tuple(queues)
        if not self.queues:
            raise ValueError("worker requires at least one queue")
        self._stop = threading.Event()

    def run_cycle(self) -> CycleReport:
        blocked = tuple(queue for queue in self.queues if self._is_blocked(queue))
        runnable = tuple(queue for queue in self.queues if queue not in blocked)
        return CycleReport(
            queues=tuple(queue.value for queue in self.queues),
            runnable_queues=tuple(queue.value for queue in runnable),
            blocked_queues=tuple(queue.value for queue in blocked),
        )

    def run_forever(self, poll_interval: float, max_cycles: int | None = None) -> int:
        if poll_interval <= 0 or poll_interval > 60:
            raise ValueError("poll interval must be between 0 and 60 seconds")
        self._install_signal_handlers()
        cycles = 0
        while not self._stop.is_set():
            self.run_cycle()
            cycles += 1
            logger.debug(
                "worker cycle completed",
                extra={"event": "worker.cycle", "service": "worker"},
            )
            if max_cycles is not None and cycles >= max_cycles:
                break
            self._stop.wait(poll_interval)
        return 0

    def stop(self) -> None:
        self._stop.set()

    def _is_blocked(self, queue: QueueName) -> bool:
        if queue in {QueueName.ACQUIRE, QueueName.PARSE}:
            return not self.settings.ingestion_enabled
        if queue is QueueName.ENGAGE:
            return not self.settings.outreach_send_enabled
        if queue is QueueName.DELIVER:
            return self.settings.alert_delivery_mode is not AlertDeliveryMode.PROVIDER
        return False

    def _install_signal_handlers(self) -> None:
        if threading.current_thread() is not threading.main_thread():
            return

        def request_stop(_signum: int, _frame: object) -> None:
            self.stop()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)
