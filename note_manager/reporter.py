from __future__ import annotations
import json
from dataclasses import asdict
from pathlib import Path
from typing import Dict, List, Set, Any
from datetime import datetime

from .models import Note, NoteGraph
from .detector import DetectionResult, BrokenLink, AmbiguousLink
from .fixer import FixResult, FixAction


class Reporter:
    def __init__(self, graph: NoteGraph, vault_root: Path):
        self.graph = graph
        self.vault_root = vault_root.resolve()

    def _rel(self, p: Path) -> str:
        try:
            return str(p.resolve().relative_to(self.vault_root)).replace("\\", "/")
        except ValueError:
            return str(p).replace("\\", "/")

    def generate_backlinks_report(self, fmt: str = "text") -> str:
        data: Dict[str, Any] = {}
        for note_path, note in sorted(self.graph.notes.items()):
            backlinks = self.graph.get_backlinks(note_path)
            rel = self._rel(note_path)
            data[rel] = {
                "note": rel,
                "title": note.name,
                "backlink_count": len(backlinks),
                "backlinks": sorted(self._rel(p) for p in backlinks),
            }

        if fmt == "json":
            return json.dumps(data, ensure_ascii=False, indent=2)

        lines = ["# 反向链接报告\n"]
        for rel, info in sorted(data.items()):
            lines.append(f"## {info['title']} ({rel})")
            lines.append(f"被引用次数: {info['backlink_count']}")
            if info["backlinks"]:
                lines.append("")
                for bl in info["backlinks"]:
                    lines.append(f"- [[{bl}]]")
            lines.append("")
        return "\n".join(lines)

    def generate_index(self) -> str:
        lines = [
            "# 笔记库索引",
            f"",
            f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}",
            f"笔记总数: {len(self.graph.notes)}",
            f"",
            "## 笔记列表",
            "",
        ]
        for note_path in sorted(self.graph.notes.keys()):
            note = self.graph.notes[note_path]
            rel = self._rel(note_path)
            bl_count = len(self.graph.get_backlinks(note_path))
            out_count = len(note.outgoing_links)
            lines.append(f"- [{note.name}]({rel}) - 入链:{bl_count} 出链:{out_count}")
        return "\n".join(lines)

    def generate_issues_report(
        self,
        detection: DetectionResult,
        fmt: str = "text",
    ) -> str:
        if fmt == "json":
            return self._issues_json(detection)
        return self._issues_text(detection)

    def _issues_json(self, d: DetectionResult) -> str:
        data = {
            "broken_links": [
                {
                    "source": self._rel(b.link.source_path),
                    "line": b.link.line_number,
                    "raw": b.link.target_raw,
                    "type": b.link.link_type.value,
                    "reason": b.reason,
                    "suggestion": b.suggestion,
                }
                for b in d.broken_links
            ],
            "orphan_notes": sorted(self._rel(p) for p in d.orphan_notes),
            "ambiguous_links": [
                {
                    "source": self._rel(a.link.source_path),
                    "line": a.link.line_number,
                    "raw": a.link.target_raw,
                    "target_name": a.link.target_note_name,
                    "candidates": sorted(self._rel(c) for c in a.candidates),
                }
                for a in d.ambiguous_links
            ],
            "unreferenced_attachments": sorted(
                self._rel(p) for p in d.unreferenced_attachments
            ),
            "summary": {
                "broken_links_count": len(d.broken_links),
                "orphan_notes_count": len(d.orphan_notes),
                "ambiguous_links_count": len(d.ambiguous_links),
                "unreferenced_attachments_count": len(d.unreferenced_attachments),
            },
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _issues_text(self, d: DetectionResult) -> str:
        lines = ["# 笔记库问题报告\n"]

        lines.append("## 摘要")
        lines.append(f"- 死链数量: {len(d.broken_links)}")
        lines.append(f"- 孤儿笔记数量: {len(d.orphan_notes)}")
        lines.append(f"- 歧义链接数量: {len(d.ambiguous_links)}")
        lines.append(f"- 未引用附件数量: {len(d.unreferenced_attachments)}")
        lines.append("")

        if d.broken_links:
            lines.append("## 死链")
            lines.append("")
            for b in d.broken_links:
                src = self._rel(b.link.source_path)
                lines.append(f"- **{src}** 第{b.link.line_number}行: `{b.link.target_raw}`")
                lines.append(f"  - 原因: {b.reason}")
                if b.suggestion:
                    lines.append(f"  - 建议: {b.suggestion}")
            lines.append("")

        if d.orphan_notes:
            lines.append("## 孤儿笔记（无其他笔记引用）")
            lines.append("")
            for p in sorted(d.orphan_notes):
                lines.append(f"- {self._rel(p)}")
            lines.append("")

        if d.ambiguous_links:
            lines.append("## 歧义链接（重名冲突）")
            lines.append("")
            for a in d.ambiguous_links:
                src = self._rel(a.link.source_path)
                lines.append(f"- **{src}** 第{a.link.line_number}行: `{a.link.target_raw}`")
                lines.append("  候选文件:")
                for c in a.candidates:
                    lines.append(f"    - {self._rel(c)}")
            lines.append("")

        if d.unreferenced_attachments:
            lines.append("## 未引用的附件（可清理）")
            lines.append("")
            for p in sorted(d.unreferenced_attachments):
                lines.append(f"- {self._rel(p)}")
            lines.append("")

        return "\n".join(lines)

    def generate_fix_report(
        self,
        fix_result: FixResult,
        fmt: str = "text",
    ) -> str:
        if fmt == "json":
            return self._fix_json(fix_result)
        return self._fix_text(fix_result)

    def _fix_json(self, r: FixResult) -> str:
        data = {
            "files_modified": sorted(self._rel(p) for p in r.files_modified),
            "actions": [
                {
                    "file": self._rel(a.file_path),
                    "line": a.line_number,
                    "old": a.old_text,
                    "new": a.new_text,
                    "description": a.description,
                }
                for a in r.actions
            ],
            "renamed_files": [
                {"from": self._rel(o), "to": self._rel(n)} for o, n in r.renamed_files
            ],
            "unresolved_broken_links": [
                {
                    "source": self._rel(b.link.source_path),
                    "line": b.link.line_number,
                    "raw": b.link.target_raw,
                    "reason": b.reason,
                }
                for b in r.unresolved_broken_links
            ],
            "unresolved_ambiguous_links": [
                {
                    "source": self._rel(a.link.source_path),
                    "line": a.link.line_number,
                    "raw": a.link.target_raw,
                    "candidates": sorted(self._rel(c) for c in a.candidates),
                }
                for a in r.unresolved_ambiguous_links
            ],
            "total_changes": r.total_changes,
        }
        return json.dumps(data, ensure_ascii=False, indent=2)

    def _fix_text(self, r: FixResult) -> str:
        lines = ["# 修复操作报告\n"]

        lines.append(f"## 摘要")
        lines.append(f"- 修改文件数: {len(r.files_modified)}")
        lines.append(f"- 链接更新数: {len(r.actions)}")
        lines.append(f"- 文件重命名数: {len(r.renamed_files)}")
        lines.append(f"- 未解决死链数: {len(r.unresolved_broken_links)}")
        lines.append(f"- 未解决歧义数: {len(r.unresolved_ambiguous_links)}")
        lines.append("")

        if r.actions:
            lines.append("## 链接更新")
            lines.append("")
            for a in r.actions:
                lines.append(f"- **{self._rel(a.file_path)}** 第{a.line_number}行")
                lines.append(f"  `{a.old_text}` -> `{a.new_text}`")
                lines.append(f"  ({a.description})")
            lines.append("")

        if r.renamed_files:
            lines.append("## 文件重命名/移动")
            lines.append("")
            for old, new in r.renamed_files:
                lines.append(f"- {self._rel(old)}  ->  {self._rel(new)}")
            lines.append("")

        if r.unresolved_broken_links:
            lines.append("## 未解决的死链（需人工处理）")
            lines.append("")
            for b in r.unresolved_broken_links:
                lines.append(
                    f"- **{self._rel(b.link.source_path)}** 第{b.link.line_number}行: "
                    f"`{b.link.target_raw}` ({b.reason})"
                )
            lines.append("")

        if r.unresolved_ambiguous_links:
            lines.append("## 未解决的歧义链接（需人工处理）")
            lines.append("")
            for a in r.unresolved_ambiguous_links:
                lines.append(
                    f"- **{self._rel(a.link.source_path)}** 第{a.link.line_number}行: "
                    f"`{a.link.target_raw}`"
                )
                for c in a.candidates:
                    lines.append(f"    候选: {self._rel(c)}")
            lines.append("")

        return "\n".join(lines)
