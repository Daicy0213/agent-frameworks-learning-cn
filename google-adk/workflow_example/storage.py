"""记录真实执行次数、模型用量和归档业务回执。"""

from contextlib import closing, contextmanager
from pathlib import Path
import sqlite3


class Ledger:
    """独立于 ADK checkpoint 的 SQLite 业务存储。"""

    def __init__(self, path: Path):
        self.path = path
        path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as database:
            database.executescript("""
                CREATE TABLE IF NOT EXISTS counters (
                    name TEXT PRIMARY KEY, value INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS model_responses (
                    id INTEGER PRIMARY KEY, agent TEXT NOT NULL,
                    tokens INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS receipts (
                    operation_key TEXT PRIMARY KEY, digest TEXT NOT NULL,
                    filename TEXT NOT NULL, version INTEGER NOT NULL,
                    article_count INTEGER NOT NULL
                );
                CREATE TABLE IF NOT EXISTS faults (
                    name TEXT PRIMARY KEY
                );
            """)

    @contextmanager
    def connection(self):
        with closing(sqlite3.connect(self.path)) as database, database:
            database.row_factory = sqlite3.Row
            yield database

    def count(self, name: str) -> None:
        with self.connection() as database:
            database.execute(
                "INSERT INTO counters VALUES (?, 1) "
                "ON CONFLICT(name) DO UPDATE SET value=value+1",
                (name,),
            )

    def record_peak(self, active: int) -> None:
        with self.connection() as database:
            database.execute(
                "INSERT INTO counters VALUES ('worker_peak', ?) "
                "ON CONFLICT(name) DO UPDATE SET value=MAX(value, excluded.value)",
                (active,),
            )

    def record_model(self, agent: str, tokens: int) -> None:
        with self.connection() as database:
            database.execute(
                "INSERT INTO model_responses (agent, tokens) VALUES (?, ?)",
                (agent, tokens),
            )

    def save_receipt(
        self,
        operation_key: str,
        digest: str,
        filename: str,
        version: int,
        article_count: int,
    ) -> None:
        with self.connection() as database:
            database.execute(
                "INSERT INTO receipts VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(operation_key) DO NOTHING",
                (operation_key, digest, filename, version, article_count),
            )
            existing = database.execute(
                "SELECT * FROM receipts WHERE operation_key=?",
                (operation_key,),
            ).fetchone()
            if (
                existing["digest"],
                existing["filename"],
                existing["version"],
            ) != (
                digest,
                filename,
                version,
            ):
                raise ValueError("同一业务操作不能代表不同稿件或归档版本")

    def claim_fault(self) -> bool:
        """持久记录一次故障注入，重启后不会再次注入。"""
        with self.connection() as database:
            cursor = database.execute(
                "INSERT INTO faults VALUES ('after_archive') "
                "ON CONFLICT(name) DO NOTHING"
            )
            return cursor.rowcount == 1

    def snapshot(self) -> dict:
        with self.connection() as database:
            counts = dict(database.execute("SELECT name, value FROM counters"))
            responses = database.execute(
                "SELECT agent, tokens FROM model_responses ORDER BY id"
            ).fetchall()
            receipts = database.execute("SELECT * FROM receipts").fetchall()
        return {
            "counts": counts,
            "model_responses": len(responses),
            "tokens": sum(row["tokens"] for row in responses),
            "model_usage": [dict(row) for row in responses],
            "receipt_count": len(receipts),
            "receipts": [dict(row) for row in receipts],
        }
