"""第 9 章练习 5：恢复后的重复执行，由外部幂等存储负责去重。

运行：uv run python google-adk/practice/c9_5.py
不调用模型。两个独立 Python 子进程同时准备就绪后，再提交同一归档请求。
本题只验证外部副作用存储；ADK checkpoint 的恢复实验见 workflow_example。
"""

from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

SCHEMA = """
CREATE TABLE artifacts (
    digest TEXT PRIMARY KEY,
    filename TEXT NOT NULL,
    version INTEGER NOT NULL,
    text TEXT NOT NULL
);
CREATE TABLE receipts (
    op_key TEXT PRIMARY KEY,
    digest TEXT NOT NULL,
    filename TEXT NOT NULL,
    version INTEGER NOT NULL,
    count INTEGER NOT NULL,
    FOREIGN KEY (digest) REFERENCES artifacts(digest)
);
"""


class IdempotencyConflict(ValueError):
    """同一个幂等键被再次用于不同请求；调用方必须纠正请求。"""


def archive_once(
    db_path: str, digest: str, filename: str, text: str, count: int, worker: str
) -> dict:
    """一次事务写入正文与回执，重复请求返回已有版本。

    digest 在这里作为调用方传来的归档身份。服务仍逐字段检查请求内容，
    防止调用方错误地复用身份；并不因为名字叫 digest 就盲目信任它。
    """
    op_key = f"archive:{digest}"
    with closing(sqlite3.connect(db_path, timeout=10)) as db, db:
        db.execute("PRAGMA foreign_keys = ON")
        # 事务开始就竞争写锁：读已有请求、核对、写入都在同一事务中。
        db.execute("BEGIN IMMEDIATE")
        existing = db.execute(
            "SELECT r.digest, r.filename, r.version, r.count, a.text "
            "FROM receipts r JOIN artifacts a ON a.digest = r.digest "
            "WHERE r.op_key = ?", (op_key,),
        ).fetchone()
        if existing is not None:
            old_digest, old_filename, version, old_count, old_text = existing
            if (old_digest, old_filename, old_count, old_text) != (
                digest, filename, count, text
            ):
                raise IdempotencyConflict("同一幂等键不能绑定不同内容或参数")
            wrote = False
        else:
            artifact = db.execute(
                "SELECT filename, version, text FROM artifacts WHERE digest = ?",
                (digest,),
            ).fetchone()
            if artifact is None:
                version = 0
                db.execute(
                    "INSERT INTO artifacts VALUES (?, ?, ?, ?)",
                    (digest, filename, version, text),
                )
            else:
                old_filename, version, old_text = artifact
                if (old_filename, old_text) != (filename, text):
                    raise IdempotencyConflict("同一归档身份不能绑定不同内容或文件名")
            db.execute(
                "INSERT INTO receipts VALUES (?, ?, ?, ?, ?)",
                (op_key, digest, filename, version, count),
            )
            wrote = True
    return {
        "worker": worker, "pid": os.getpid(), "op_key": op_key,
        "version": version, "wrote": wrote,
    }


async def run_workers(request: dict) -> list[dict]:
    """启动两个真正的子进程；等双方就绪后才释放请求，不用线程代替进程。"""
    processes = []
    try:
        for _ in range(2):
            processes.append(await asyncio.create_subprocess_exec(
                sys.executable, "-X", "utf8", str(Path(__file__).resolve()), "--worker",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            ))
        ready_lines = await asyncio.wait_for(
            asyncio.gather(*(process.stdout.readline() for process in processes)),
            timeout=20,
        )
        ready = [json.loads(line) for line in ready_lines]
        assert all(item["ready"] for item in ready)
        assert len({item["pid"] for item in ready}) == 2
        assert all(item["pid"] != os.getpid() for item in ready)
        outputs = await asyncio.wait_for(
            asyncio.gather(*(
                process.communicate(json.dumps({
                    **request, "worker": f"process-{index}"
                }).encode("utf-8"))
                for index, process in enumerate(processes)
            )), timeout=30,
        )
        results = []
        for process, (stdout, stderr) in zip(processes, outputs):
            if process.returncode != 0:
                raise RuntimeError(stderr.decode("utf-8"))
            results.append(json.loads(stdout))
        assert {result["pid"] for result in results} == {item["pid"] for item in ready}
        return results
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def main() -> None:
    with TemporaryDirectory(prefix="adk_c9_5_") as folder:
        db_path = str(Path(folder) / "external.db")
        with closing(sqlite3.connect(db_path)) as db:
            db.executescript(SCHEMA)
        request = {
            "db_path": db_path, "digest": "a" * 64,
            "filename": "batch-a.md", "text": "# 标题\n\n归档正文内容。", "count": 2,
        }
        # 竞态使用全新数据库，避免两个进程都只读已有结果而漏掉首次写入竞争。
        results = await run_workers(request)
        assert len({result["pid"] for result in results}) == 2, results
        assert sum(result["wrote"] for result in results) == 1, results
        assert {result["version"] for result in results} == {0}, results
        print("两个独立进程：", results)

        # 模拟恢复后的再次投递：必须复用回执，不能新增版本。
        retry = archive_once(**request, worker="after-restart")
        assert retry["wrote"] is False and retry["version"] == 0
        for changed in [{"text": "替换后的正文"}, {"filename": "other.md"}, {"count": 3}]:
            try:
                archive_once(**(request | changed), worker="conflict")
            except IdempotencyConflict:
                pass
            else:
                raise AssertionError(f"同一幂等键改变参数必须拒绝：{changed}")

        with closing(sqlite3.connect(db_path)) as db:
            artifacts = db.execute("SELECT * FROM artifacts").fetchall()
            receipts = db.execute("SELECT * FROM receipts").fetchall()
        assert artifacts == [(request["digest"], request["filename"], 0, request["text"])]
        assert receipts == [(
            f"archive:{request['digest']}", request["digest"], request["filename"], 0, 2
        )]
        print("通过：不同 PID，只产生一个版本和一条回执；同键异内容被明确拒绝。")
        print(
            "边界：本例正文与回执共享一个 SQLite 事务。跨系统写入还需要外部服务的"
            "幂等协议与对账/补偿；checkpoint 不能单独保证外部副作用恰好一次。"
        )


if __name__ == "__main__":
    if sys.argv[1:] == ["--worker"]:
        print(json.dumps({"ready": True, "pid": os.getpid()}), flush=True)
        payload = json.load(sys.stdin)
        print(json.dumps(archive_once(**payload)), flush=True)
    else:
        asyncio.run(main())
