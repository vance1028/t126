from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import re

from .models import Note, Link, NoteGraph, LinkType
from .detector import DetectionResult, BrokenLink, AmbiguousLink
from .file_ops import FileManager
from .link_parser import LinkParser


@dataclass
class FixAction:
    file_path: Path
    old_text: str
    new_text: str
    line_number: int
    description: str


@dataclass
class FixResult:
    actions: List[FixAction] = field(default_factory=list)
    renamed_files: List[Tuple[Path, Path]] = field(default_factory=list)
    unresolved_broken_links: List[BrokenLink] = field(default_factory=list)
    unresolved_ambiguous_links: List[AmbiguousLink] = field(default_factory=list)

    @property
    def files_modified(self) -> Set[Path]:
        return {a.file_path for a in self.actions}

    @property
    def total_changes(self) -> int:
        return len(self.actions) + len(self.renamed_files)


class LinkFixer:
    WIKILINK_RE = LinkParser.WIKILINK_RE
    MD_LINK_RE = LinkParser.MD_LINK_RE

    def __init__(self, graph: NoteGraph, file_manager: FileManager):
        self.graph = graph
        self.fm = file_manager

    def rename_note(
        self,
        old_path: Path,
        new_path: Path,
        dry_run: bool = False,
    ) -> FixResult:
        old_path = old_path.resolve()
        new_path = new_path.resolve()
        result = FixResult()

        if old_path not in self.graph.notes:
            return result

        backlinks = self.graph.get_backlinks(old_path)
        old_note = self.graph.notes[old_path]
        old_name = old_note.stem
        new_name = new_path.stem

        for source_path in backlinks:
            actions = self._update_links_in_file(
                source_path, old_path, new_path, old_name, new_name
            )
            result.actions.extend(actions)

        renamed = self.fm.rename_file(old_path, new_path, dry_run=dry_run)
        if renamed or dry_run:
            result.renamed_files.append((old_path, new_path))

        self._apply_actions(result, dry_run=dry_run)
        return result

    def fix_broken_links(
        self,
        detection: DetectionResult,
        dry_run: bool = False,
    ) -> FixResult:
        result = FixResult()

        for broken in detection.broken_links:
            fix = self._try_fix_broken_link(broken)
            if fix:
                result.actions.append(fix)
            else:
                result.unresolved_broken_links.append(broken)

        result.unresolved_ambiguous_links = list(detection.ambiguous_links)
        self._apply_actions(result, dry_run=dry_run)
        return result

    def _try_fix_broken_link(self, broken: BrokenLink) -> Optional[FixAction]:
        link = broken.link
        note_path = link.source_path

        if link.is_wikilink and broken.suggestion:
            old_text = link.target_raw
            new_text = self._rebuild_wikilink(link, broken.suggestion)
            if old_text != new_text:
                return FixAction(
                    file_path=note_path,
                    old_text=old_text,
                    new_text=new_text,
                    line_number=link.line_number,
                    description=f"修正死链: {old_text} -> {new_text}",
                )

        return None

    def _rebuild_wikilink(self, link: Link, new_name: str) -> str:
        parts = [new_name]
        if link.anchor:
            parts.append(f"#{link.anchor}")
        if link.alias:
            parts.append(f"|{link.alias}")
        return f"[[{''.join(parts)}]]"

    def _update_links_in_file(
        self,
        source_path: Path,
        old_target: Path,
        new_target: Path,
        old_name: str,
        new_name: str,
    ) -> List[FixAction]:
        actions = []
        content = self.fm.read_file(source_path)
        source_note = self.graph.notes.get(source_path)

        if not source_note:
            return actions

        for link in source_note.outgoing_links:
            target_match = False
            if link.target_path and link.target_path.resolve() == old_target.resolve():
                target_match = True
            elif link.is_wikilink and link.target_note_name == old_name:
                candidates = self.graph.name_to_paths.get(old_name, [])
                if len(candidates) == 1 and candidates[0].resolve() == old_target.resolve():
                    target_match = True

            if not target_match:
                continue

            old_text = link.target_raw

            if link.is_wikilink:
                new_text = self._rebuild_wikilink(link, new_name)
            else:
                new_rel = self.fm.get_relative_path(source_path, new_target)
                new_text = self._rebuild_md_link(link, str(new_rel))

            if old_text != new_text:
                actions.append(
                    FixAction(
                        file_path=source_path,
                        old_text=old_text,
                        new_text=new_text,
                        line_number=link.line_number,
                        description=f"更新链接: {old_text} -> {new_text}",
                    )
                )

        return actions

    def _rebuild_md_link(self, link: Link, new_target: str) -> str:
        text = link.alias if link.alias else ""
        prefix = "!" if link.link_type in {LinkType.IMAGE, LinkType.ATTACHMENT} else ""
        return f"{prefix}[{text}]({new_target})"

    def _apply_actions(self, result: FixResult, dry_run: bool = False):
        file_contents: Dict[Path, str] = {}
        for action in sorted(result.actions, key=lambda a: a.line_number, reverse=True):
            path = action.file_path
            if path not in file_contents:
                file_contents[path] = self.fm.read_file(path)
            content = file_contents[path]
            new_content = self._replace_on_line(
                content, action.line_number, action.old_text, action.new_text
            )
            if new_content != content:
                file_contents[path] = new_content

        for path, new_content in file_contents.items():
            self.fm.write_file(path, new_content, dry_run=dry_run)

    def _replace_on_line(
        self, content: str, line_number: int, old_text: str, new_text: str
    ) -> str:
        lines = content.splitlines(keepends=True)
        if 1 <= line_number <= len(lines):
            idx = line_number - 1
            lines[idx] = lines[idx].replace(old_text, new_text, 1)
        return "".join(lines)
