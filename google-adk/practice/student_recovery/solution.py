"""学生作业：让恢复后的重复归档复用已有结果。只完成 archive_once。"""


def archive_once(
    db_path: str, digest: str, filename: str, text: str, count: int, worker: str
) -> dict:
    """成功返回 worker、pid、op_key、version、wrote。

    op_key = f"archive:{digest}"。首次归档 version 为 0，wrote 为 True；
    完全相同的重复请求返回原版本和 wrote=False。
    同键但 text、filename 或 count 不同，必须抛出 ValueError 或其子类。

    验收器已建好两张表：
      artifacts(digest PRIMARY KEY, filename, version, text)
      receipts(op_key PRIMARY KEY, digest, filename, version, count)
    """
    # TODO 1：打开 SQLite，在同一个事务内检查和写入。
    # TODO 2：重复请求要核对全部参数，不能只根据主键就返回成功。
    # TODO 3：首次执行原子写入正文和回执；重复执行读回已有版本。
    # TODO 4：返回 os.getpid()，让验收器证明执行来自不同进程。
    raise NotImplementedError("请先完成 archive_once，再运行 verify.py")
