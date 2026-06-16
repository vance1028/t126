from __future__ import annotations
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Set, Optional, Tuple
from .models import Note, Link, NoteGraph, Attachment, LinkType


@dataclass
class BrokenLink:
    link: Link
    reason: str
    suggestion: Optional[str] = None


@dataclass
class AmbiguousLink:
    link: Link
    candidates: List[Path]


@dataclass
class DetectionResult:
    broken_links: List[BrokenLink] = field(default_factory=list)
    orphan_notes: Set[Path] = field(default_factory=set)
    ambiguous_links: List[AmbiguousLink] = field(default_factory=list)
    unreferenced_attachments: Set[Path] = field(default_factory=set)


class IssueDetector:
    def __init__(self, graph: NoteGraph, vault_root: Path):
        self.graph = graph
        self.vault_root = vault_root.resolve()
        self.index_files = {"index", "索引", "README", "目录"}

    def detect_all(self) -> DetectionResult:
        result = DetectionResult()
        result.broken_links = self.detect_broken_links()
        result.orphan_notes = self.detect_orphan_notes()
        result.ambiguous_links = self.detect_ambiguous_links()
        result.unreferenced_attachments = self.detect_unreferenced_attachments()
        return result

    def detect_broken_links(self) -> List[BrokenLink]:
        broken = []
        for note in self.graph.notes.values():
            for link in note.outgoing_links:
                issue = self._check_link(link, note)
                if issue:
                    broken.append(issue)
        return broken

    def _check_link(self, link: Link, note: Note) -> Optional[BrokenLink]:
        if link.link_type in {LinkType.ATTACHMENT, LinkType.IMAGE}:
            return self._check_attachment_link(link, note)
        return self._check_note_link(link, note)

    def _check_note_link(self, link: Link, note: Note) -> Optional[BrokenLink]:
        target_path = None
        if link.target_path and link.target_path in self.graph.notes:
            target_path = link.target_path
        elif link.is_wikilink and link.target_note_name:
            candidates = self.graph.name_to_paths.get(link.target_note_name, [])
            if len(candidates) == 1:
                target_path = candidates[0]
            elif len(candidates) > 1:
                return None

        if not target_path:
            suggestion = self._find_fuzzy_match(link)
            if link.is_wikilink:
                return BrokenLink(
                    link=link,
                    reason=f"笔记不存在: '{link.target_note_name}'",
                    suggestion=suggestion,
                )
            else:
                return BrokenLink(
                    link=link,
                    reason=f"链接目标不存在: '{link.target_raw}'",
                    suggestion=suggestion,
                )

        if link.anchor:
            target_note = self.graph.notes[target_path]
            if not self._anchor_exists(link.anchor, target_note):
                suggestion = self._find_fuzzy_anchor(link.anchor, target_note)
                return BrokenLink(
                    link=link,
                    reason=f"锚点不存在: '{link.anchor}' (在笔记 {target_note.name})",
                    suggestion=suggestion,
                )

        return None

    def _check_attachment_link(self, link: Link, note: Note) -> Optional[BrokenLink]:
        if not link.target_path:
            return BrokenLink(link=link, reason=f"附件路径无效: '{link.target_raw}'")

        try:
            abs_path = (note.path.parent / link.target_path).resolve()
        except Exception:
            return BrokenLink(link=link, reason=f"附件路径无法解析: '{link.target_path}'")

        if abs_path not in self.graph.attachments and not abs_path.exists():
            return BrokenLink(
                link=link,
                reason=f"附件不存在: '{link.target_path}'",
            )
        return None

    def _anchor_exists(self, anchor: str, note: Note) -> bool:
        return anchor in note.title_anchors

    def _find_fuzzy_match(self, link: Link) -> Optional[str]:
        target = link.target_note_name or (link.target_path.stem if link.target_path else "")
        if not target:
            return None
        all_names = self.graph.all_note_names()
        matches = []
        target_lower = target.lower()
        for name in all_names:
            name_lower = name.lower()
            if target_lower in name_lower or name_lower in target_lower:
                matches.append(name)
        if len(matches) == 1:
            return matches[0]
        return None

    def _find_fuzzy_anchor(self, anchor: str, note: Note) -> Optional[str]:
        if not anchor or not note.title_anchors:
            return None
        anchor_lower = anchor.lower()
        for title in note.title_anchors:
            if anchor_lower in title.lower() or title.lower() in anchor_lower:
                return title
        return None

    def detect_orphan_notes(self) -> Set[Path]:
        orphans = set()
        for note_path, note in self.graph.notes.items():
            if note.stem in self.index_files:
                continue
            backlinks = self.graph.get_backlinks(note_path)
            if not backlinks:
                orphans.add(note_path)
        return orphans

    def detect_ambiguous_links(self) -> List[AmbiguousLink]:
        ambiguous = []
        seen = set()
        for note in self.graph.notes.values():
            for link in note.outgoing_links:
                if link.is_wikilink and link.target_note_name:
                    candidates = self.graph.name_to_paths.get(link.target_note_name, [])
                    if len(candidates) > 1:
                        key = (note.path, link.target_raw, link.line_number)
                        if key not in seen:
                            seen.add(key)
                            ambiguous.append(AmbiguousLink(link=link, candidates=list(candidates)))
        return ambiguous

    def detect_unreferenced_attachments(self) -> Set[Path]:
        unreferenced = set()
        for att_path, att in self.graph.attachments.items():
            if not att.referenced_by:
                unreferenced.add(att_path)
        return unreferenced
