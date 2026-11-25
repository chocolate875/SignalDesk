"""Interactive cleanup for the data directory used by the desktop app."""

from __future__ import annotations

import argparse
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from .launcher import active_instance, claim_instance, stop_desktop
from .security import data_directory

DATABASE = "signaldesk.sqlite3"
CACHE_MODE = "cache"
FULL_MODE = "all"
DATABASE_FILES = (DATABASE, f"{DATABASE}-wal", f"{DATABASE}-shm", f"{DATABASE}-journal")
CREDENTIAL_FILES = tuple(
    f"credentials/{service}.{suffix}"
    for service in ("longport", "longbridge_client", "qq")
    for suffix in ("encrypted", "tmp")
)
EXPORT_DIRS = ("codex-exports", "agent-exports")


def _check_paths(directory: Path, files: tuple[str, ...], folders: tuple[str, ...]) -> None:
    for name in (*files, *folders):
        path = directory / name
        # An override may point at a directory shared with other applications.
        if path.resolve() != path or path.is_symlink() or path.is_junction():
            raise RuntimeError(f"清理路径经过符号链接或目录联接，请核对：{path}")
        if path.exists() and not (path.is_dir() if name in folders else path.is_file()):
            raise RuntimeError(f"清理路径的文件类型异常，请核对：{path}")


def clean_data(directory: Path, *, cache_only: bool) -> str:
    directory = directory.resolve()
    if not directory.exists():
        return "没有找到本地数据目录。"

    files = DATABASE_FILES if cache_only else (*DATABASE_FILES, *CREDENTIAL_FILES)
    folders = () if cache_only else ("credentials", *EXPORT_DIRS)
    checked_files = ("instance.lock", *files)
    _check_paths(directory, checked_files, folders)
    if active_instance(directory) is not None:
        stop_desktop(directory)

    # Use the same lock as both the tray and headless entry points.
    with claim_instance(directory, 0) as maintenance:
        if maintenance is None:
            raise RuntimeError("SignalDesk 正在运行或启动，请退出后重试。")
        _check_paths(directory, checked_files, folders)
        if cache_only:
            database = directory / DATABASE
            if not database.exists():
                return "没有找到本地数据库。"
            with closing(sqlite3.connect(f"{database.as_uri()}?mode=rw", uri=True)) as db, db:
                count = db.execute("DELETE FROM bars").rowcount
            return f"已清理 {count:,} 条 K 线缓存。下次实盘同步会重新拉取。"

        for name in files:
            (directory / name).unlink(missing_ok=True)
        for name in EXPORT_DIRS:
            path = directory / name
            if path.exists():
                shutil.rmtree(path)
        return "已重置本地数据。下次启动会重新创建数据库。"


def main() -> None:
    parser = argparse.ArgumentParser(description="清理 SignalDesk 本地数据")
    parser.add_argument(
        "mode", nargs="?", choices=(CACHE_MODE, FULL_MODE),
        help="cache 清理所有市场的 K 线缓存，all 重置数据库、凭据和 AI 复核导出文件",
    )
    args = parser.parse_args()
    directory = data_directory().resolve()
    print(f"SignalDesk 数据目录\n{directory}\n")
    mode = args.mode
    try:
        if mode is None:
            print("1. 只清理 K 线缓存")
            print("2. 重置全部本地数据")
            mode = {"1": CACHE_MODE, "2": FULL_MODE}.get(input("请选择，直接回车取消：").strip())
        if mode is None:
            print("已取消。")
            return
        cache_only = mode == CACHE_MODE
        if cache_only:
            print("将删除所有市场的本地 K 线缓存。设定、持仓分类、自选和凭据会保留。")
        else:
            print("将删除数据库（包括设置、持仓分类、自选、提醒记录和缓存）、券商与 QQ 凭据及 AI 复核导出。")
        print("确认后会停止这个数据目录正在运行的 SignalDesk。")
        if input("输入 CLEAN 确认清理：").strip() != "CLEAN":
            print("已取消。")
            return
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。")
        return

    try:
        print(clean_data(directory, cache_only=cache_only))
    except (OSError, RuntimeError, sqlite3.Error) as error:
        parser.exit(1, f"清理未完成。{error}\n")


if __name__ == "__main__":
    main()
