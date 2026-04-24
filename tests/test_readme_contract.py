from __future__ import annotations

import re
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
README_EN = REPO_ROOT / "README.md"
README_ZH = REPO_ROOT / "README.zh-CN.md"


def section_titles(path: Path) -> list[str]:
    text = path.read_text(encoding="utf-8")
    return re.findall(r"^##\s+(.+)$", text, flags=re.MULTILINE)


class ReadmeContractTests(unittest.TestCase):
    def test_english_readme_structure_and_core_objects(self) -> None:
        text = README_EN.read_text(encoding="utf-8")
        self.assertEqual(
            section_titles(README_EN),
            [
                "What It Is",
                "Quick Start",
                "Core Commands",
                "Why It Is Different",
                "Validation",
                "Repository Layout",
                "Optional Semantic Extras",
                "Scope",
            ],
        )
        self.assertNotRegex(text, r"^##\s+Why\s*$", msg="legacy '## Why' heading must not appear")
        for needle in [
            "Who it is for:",
            "It solves one problem:",
            "Choose Codex Memory Skill if you want:",
            "Memory note",
            "Runbook",
            "Skill bundle",
            "Asset index",
            "Checkpoint",
            "Promotion",
            "L4 archive",
            ".codex/cache/memory-state.db",
        ]:
            self.assertIn(needle, text)

    def test_chinese_readme_structure_and_core_objects(self) -> None:
        text = README_ZH.read_text(encoding="utf-8")
        self.assertEqual(
            section_titles(README_ZH),
            [
                "项目定位",
                "项目简介",
                "快速开始",
                "常用命令",
                "差异点",
                "验证结果",
                "仓库结构",
                "可选依赖",
                "边界说明",
            ],
        )
        self.assertNotIn("## 它是什么", text)
        for needle in [
            "给谁用:",
            "解决什么问题",
            "核心功能",
            "核心对象与关系",
            "如果你需要以下能力, 这套更合适:",
            "记忆笔记 (Memory note)",
            "Runbook",
            "Skill bundle",
            "资产索引 (Asset index)",
            "检查点 (Checkpoint)",
            "提升 (Promotion)",
            "L4 归档 (L4 archive)",
            ".codex/cache/memory-state.db",
        ]:
            self.assertIn(needle, text)


if __name__ == "__main__":
    unittest.main()
