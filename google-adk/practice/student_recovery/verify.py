"""独立验收存储协议：不同进程的并发、进程退出后的重复投递及冲突拒绝。"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import os
import sqlite3
import sys
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

SCHEMA = """
CREATE TABLE artifacts (
    digest TEXT PRIMARY KEY, filename TEXT NOT NULL,
    version INTEGER NOT NULL, text TEXT NOT NULL
);
CREATE TABLE receipts (
    op_key TEXT PRIMARY KEY, digest TEXT NOT NULL, filename TEXT NOT NULL,
    version INTEGER NOT NULL, count INTEGER NOT NULL
);
"""


def load_solution(path: Path):
    spec = importlib.util.spec_from_file_location("student_recovery_answer", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"无法加载作业：{path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


async def workers(path: Path, request: dict, count: int = 2) -> list[dict]:
    processes = []
    try:
        for _ in range(count):
            processes.append(await asyncio.create_subprocess_exec(
                sys.executable, "-X", "utf8", str(Path(__file__).resolve()),
                "--worker", str(path), stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE,
            ))
        ready = await asyncio.wait_for(
            asyncio.gather(*(process.stdout.readline() for process in processes)), 20
        )
        pids = [json.loads(line)["pid"] for line in ready]
        assert len(set(pids)) == count and os.getpid() not in pids
        outputs = await asyncio.wait_for(asyncio.gather(*(
            process.communicate(json.dumps({
                **request, "worker": f"worker-{index}"
            }).encode("utf-8"))
            for index, process in enumerate(processes)
        )), 30)
        results = []
        for pid, process, (stdout, stderr) in zip(pids, processes, outputs):
            assert process.returncode == 0, stderr.decode("utf-8")
            result = json.loads(stdout)
            assert result["pid"] == pid, "结果必须来自这个子进程"
            results.append(result)
        return results
    finally:
        for process in processes:
            if process.returncode is None:
                process.kill()
            await process.wait()


async def verify(path: Path) -> None:
    with TemporaryDirectory(prefix="adk_student_recovery_") as folder:
        db_path = str(Path(folder) / "exercise.db")
        with closing(sqlite3.connect(db_path)) as db:
            db.executescript(SCHEMA)
        request = {
            "db_path": db_path, "digest": "exercise-operation-01",
            "filename": "report.md", "text": "已批准的正文", "count": 2,
        }
        results = await workers(path, request)
        assert len({result["pid"] for result in results}) == 2
        assert sum(result["wrote"] for result in results) == 1
        assert {result["version"] for result in results} == {0}
        assert {result["op_key"] for result in results} == {"archive:exercise-operation-01"}

        # 前两个子进程已经退出；新进程只能从存储恢复既有结果。
        resumed = (await workers(path, request, count=1))[0]
        assert resumed["wrote"] is False and resumed["version"] == 0
        answer = load_solution(path)
        for changed in [
            {"text": "未批准的替换正文"}, {"filename": "other.md"}, {"count": 9}
        ]:
            try:
                answer.archive_once(**(request | changed), worker="conflict")
            except ValueError:
                pass
            else:
                raise AssertionError(f"同键异参数必须明确拒绝：{changed}")

        with closing(sqlite3.connect(db_path)) as db:
            assert db.execute("SELECT * FROM artifacts").fetchall() == [
                (request["digest"], "report.md", 0, "已批准的正文")
            ]
            assert db.execute("SELECT * FROM receipts").fetchall() == [
                ("archive:exercise-operation-01", request["digest"], "report.md", 0, 2)
            ]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--reference", action="store_true", help="只验证现有参考答案")
    parser.add_argument("--worker", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.worker:
        answer = load_solution(args.worker)
        print(json.dumps({"pid": os.getpid()}), flush=True)
        print(json.dumps(answer.archive_once(**json.load(sys.stdin))), flush=True)
        return
    path = Path(__file__).with_name("solution.py")
    if args.reference:
        path = Path(__file__).resolve().parents[1] / "c9_5.py"
    asyncio.run(verify(path))
    print("通过：两个并发进程、重启重投、唯一版本/回执及同键异参数拒绝。")


if __name__ == "__main__":
    main()
