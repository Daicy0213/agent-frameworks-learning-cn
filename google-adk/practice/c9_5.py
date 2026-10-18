"""练习 5（综合）：把单写入方换成幂等键服务。

题目：用带 UNIQUE 约束的表模拟一个外部幂等键服务，让两个进程并发归档同一个 digest。

验收：
- 断言最终"一个版本 + 一条回执"；
- 用文字指出这仍然不等于分布式事务——还需要外部存储提供什么能力。

本练习不调用模型，也不需要 ADK：它验证的是**存储层**的幂等能力，
而这一层恰恰是 checkpoint 帮不上忙的地方。
"""

from __future__ import annotations

import asyncio
import sqlite3
from contextlib import closing
from pathlib import Path
from tempfile import TemporaryDirectory

from _common import run

SCHEMA = """
CREATE TABLE artifacts (
    digest    TEXT PRIMARY KEY,   -- 归档身份：内容摘要
    filename  TEXT NOT NULL,
    version   INTEGER NOT NULL,
    text      TEXT NOT NULL
);
CREATE TABLE receipts (
    op_key    TEXT PRIMARY KEY,   -- 幂等键：同一个业务操作只能有一条回执
    digest    TEXT NOT NULL,
    filename  TEXT NOT NULL,
    version   INTEGER NOT NULL,
    count     INTEGER NOT NULL
);
"""


def archive_once(db_path: str, digest: str, filename: str, text: str, count: int, worker: str):
    """模拟一个进程尝试归档。返回 (结果, 是否本次真的写入)。"""
    with closing(sqlite3.connect(db_path, timeout=5)) as db, db:
        # 关键一：归档身份用 PRIMARY KEY 约束 —— 同一个 digest 只可能有一个版本，
        # 而且**第二次进来不会产生新版本**，只会读到已经存在的那个。
        db.execute(
            "INSERT INTO artifacts (digest, filename, version, text) "
            "VALUES (?, ?, 0, ?) ON CONFLICT(digest) DO NOTHING",
            (digest, filename, text),
        )
        row = db.execute(
            "SELECT filename, version, text FROM artifacts WHERE digest = ?", (digest,)
        ).fetchone()
        stored_filename, version, stored_text = row

        # 同一身份不能绑定不同内容 —— 这是幂等键的"守护条件"
        if stored_text != text:
            raise ValueError(f"[{worker}] 同一归档身份不能绑定不同内容")

        # 关键二：业务回执用幂等键去重，重复投递只会有一条
        cur = db.execute(
            "INSERT INTO receipts (op_key, digest, filename, version, count) "
            "VALUES (?, ?, ?, ?, ?) ON CONFLICT(op_key) DO NOTHING",
            (f"archive:{digest}", digest, stored_filename, version, count),
        )
        wrote = cur.rowcount == 1

    return {"worker": worker, "version": version, "wrote": wrote}


async def main() -> None:
    with TemporaryDirectory(prefix="adk_c8_5_") as folder:
        db_path = str(Path(folder) / "external.db")
        with closing(sqlite3.connect(db_path)) as db, db:
            db.executescript(SCHEMA)

        digest = "a" * 64
        filename = f"batch-{digest[:12]}.md"
        text = "# 标题\n\n归档正文内容。"

        # --- 第一步：顺序执行，先确认基本语义 ---
        first = archive_once(db_path, digest, filename, text, 2, "seq-1")
        second = archive_once(db_path, digest, filename, text, 2, "seq-2")
        assert first["wrote"] is True, first
        assert second["wrote"] is False, second
        assert first["version"] == second["version"] == 0, (first, second)
        print("顺序两次归档：", first, second)

        # --- 第二步：两个"进程"并发归档同一个**全新** digest ---
        # 必须换一个新的 digest，否则上面顺序执行时已经写过了，
        # 两个并发方都只会"读到已存在"，就测不出真正的竞态。
        # 用线程模拟两个独立进程同时到达；SQLite 的唯一约束负责裁决。
        race_digest = "b" * 64
        race_filename = f"batch-{race_digest[:12]}.md"
        results = await asyncio.gather(
            asyncio.to_thread(
                archive_once, db_path, race_digest, race_filename, text, 2, "concurrent-A"
            ),
            asyncio.to_thread(
                archive_once, db_path, race_digest, race_filename, text, 2, "concurrent-B"
            ),
        )
        print("\n并发两次归档（全新 digest）：", results)

        with closing(sqlite3.connect(db_path)) as db:
            artifact_rows = db.execute(
                "SELECT digest, filename, version FROM artifacts"
            ).fetchall()
            receipt_rows = db.execute(
                "SELECT op_key, digest, filename, version, count FROM receipts"
            ).fetchall()

        print("\n最终 artifacts 表：")
        for row in artifact_rows:
            print("   ", row[0][:12] + "...", row[1], "version=", row[2])
        print("最终 receipts 表：")
        for row in receipt_rows:
            print("   ", row[0][:24] + "...", "version=", row[3], "count=", row[4])

        # --- 验收：每个 digest 各一个版本、各一条回执 ---
        assert len(artifact_rows) == 2, f"两个 digest 各应有 1 个版本，实际 {len(artifact_rows)}"
        assert all(row[2] == 0 for row in artifact_rows), artifact_rows
        assert len(receipt_rows) == 2, f"两个 digest 各应有 1 条回执，实际 {len(receipt_rows)}"
        assert {row[0] for row in artifact_rows} == {digest, race_digest}, artifact_rows

        # 并发那一轮里，**恰好有一个**真正写入，另一个读回已有的
        race_results = [r for r in results if r["version"] == 0]
        assert sum(1 for r in results if r["wrote"]) == 1, results
        assert all(r["version"] == 0 for r in race_results), race_results
        print(f"\n并发的两个写入方里，恰好 {sum(1 for r in results if r['wrote'])} 个真正写入")

        # --- 守护条件也要被验证：同一身份换内容必须报错 ---
        try:
            archive_once(db_path, digest, filename, "内容被换掉了", 2, "mutator")
        except ValueError as error:
            print(f"\n同一身份换内容 -> 被拒绝 ✅ （{error}）")
        else:
            raise AssertionError("同一 digest 绑定不同内容必须被拒绝！")

        print("\n✅ 练习 5 通过：并发归档只产生一个版本、一条回执")

    print("""
题目要求说清楚的那句话：

**这仍然不等于分布式事务。**

上面成立，靠的是三个具体的存储能力：
  1. **唯一约束**（PRIMARY KEY / UNIQUE）—— 让"重复写入"变成一次可预期的冲突；
  2. **原子条件写入**（INSERT ... ON CONFLICT DO NOTHING）—— 判断与写入不是两步；
  3. **可读回**（冲突之后能 SELECT 到已有那一条）—— 才能复用而不是新建版本。

缺了任何一条，上面的结论就不成立。例如把"先查有没有、没有再插入"写成两步操作，
在并发下就会出现竞态：两个进程都查到"没有"，然后都去插入。

再往外一步，还有这些窗口需要外部存储提供更强的能力：
  - **多机、多副本**：单文件 SQLite 不共享，需要支持条件写入的共享存储
    （带唯一索引的数据库、对象存储的 If-None-Match、Redis SETNX 等）；
  - **跨资源事务**：归档正文和业务回执在两个系统里时，需要事务协调或对账补偿；
  - **幂等键的生命周期**：幂等键要保留多久？过期后重复投递会怎样？
    这决定了你能覆盖多长的时间窗口 —— 而 checkpoint 对此一无所知。

一句话：**checkpoint 保证"这一步不会白跑"，外部幂等键保证"这一步跑两次也只算一次"。
两件事，两套机制，缺一不可。**
""")


if __name__ == "__main__":
    run(main, need_api_key=False)
