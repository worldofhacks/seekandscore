# Worker and scheduler service

Long-running workers use `python -m seekandscore.worker --queues <queues>`.
Railway cron runs one scheduler pass with
`python -m seekandscore.scheduler dispatch-due`. Both stay idle without
external services when their feature gates are disabled.
