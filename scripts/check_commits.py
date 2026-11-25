"""校验本地提交、分支新增提交和 GitHub PR 的中文标题。"""

import argparse
import re
import subprocess
import sys
from pathlib import Path

HEADER = re.compile(
    r"(?:feat|fix|docs|style|refactor|perf|test|build|ci|chore|revert)"
    r"(?:\([a-z0-9]+(?:[.-][a-z0-9]+)*\))?!?: (?P<summary>\S(?:.*\S)?)"
)
HAN = re.compile(r"[\u3400-\u4dbf\u4e00-\u9fff\U00020000-\U0002ebef]")


def valid_title(label: str, title: str) -> bool:
    match = HEADER.fullmatch(title)
    if match and HAN.search(match["summary"]):
        return True
    print(
        f"{label} 的标题须使用「类型(可选范围): 中文摘要」，例如 fix(chart): 修复缩放范围丢失",
        file=sys.stderr,
    )
    return False


def main() -> bool:
    parser = argparse.ArgumentParser(description=__doc__)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--message-file", type=Path)
    mode.add_argument("--title")
    mode.add_argument("--range", metavar="BASE..HEAD", dest="revision_range")
    args = parser.parse_args()
    if args.message_file is not None:
        message = subprocess.check_output(
            ["git", "stripspace", "--strip-comments"], input=args.message_file.read_bytes()
        ).decode("utf-8-sig")
        return valid_title("提交", message.partition("\n")[0])
    if args.title is not None:
        return valid_title("PR", args.title)

    log = subprocess.check_output(
        ["git", "log", "-z", "--format=%h %B", "--end-of-options", args.revision_range, "--"]
    ).decode("utf-8")
    valid = True
    for record in log.split("\0"):
        if not record:
            continue
        commit, _, title = record.partition("\n")[0].partition(" ")
        if not valid_title(commit, title):
            valid = False
    return valid


if __name__ == "__main__":
    sys.exit(0 if main() else 1)
