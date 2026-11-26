import pytest

from scripts.check_commits import valid_title


@pytest.mark.parametrize(
    "title",
    [
        "fix(chart): 修复缩放范围",
        "fix:修复缩放范围",
        "修复（图表）：解决缩放丢失",
        "Fix(UI)! : 更新界面",
        "ci: 简化检查",
    ],
)
def test_accepts_flexible_chinese_titles(title):
    assert valid_title("提交", title)


@pytest.mark.parametrize("title", ["fix: fix zoom", "修复缩放范围", "fix:", ": 修复缩放范围"])
def test_rejects_titles_without_type_or_chinese_summary(title):
    assert not valid_title("提交", title)
