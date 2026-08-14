"""Operator-safe failure details for durable receipts and API-readable ledgers."""

import sqlalchemy as sa


def durable_error_detail(
    error: Exception,
    *,
    database_fallback: str,
    limit: int = 1_000,
) -> str:
    """Never persist SQL statements or bound parameters from database exceptions."""

    if isinstance(error, sa.exc.SQLAlchemyError):
        return database_fallback
    return str(error)[:limit]
