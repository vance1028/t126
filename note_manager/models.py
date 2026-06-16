from __future__ import annotations
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple


class LinkType(Enum):
    WIKILINK = "wikilink"
    WIKILINK_ANCHOR = "wikilink_anchor"
    WIKILINK_ALIAS = "wikilink_alias"
    WIKILINK_ANCHOR_ALIAS = "wikilink_anchor_alias"
    MARKDOWN_LINK = "markdown_link"
    ATTACHMENT = "attachment"
    IMAGE = "image"


@dataclass
class Link:
    source_path: Path
    target_raw: str
    target_note_name: Optional[str] = None
    target_path: Optional[Path] = None
    anchor: Optional[str] = None
    alias: Optional[str] = None
    link_type: LinkType = LinkType.WIKILINK
    line_number: int = 0
    is_broken: bool = False

    @property
    def is_wikilink(self) -> bool:
        return self.link_type in {
            LinkType.WIKILINK,
            LinkType.WIKILINK_ANCHOR,
            LinkType.WIKILINK_ALIAS,
            LinkType.WIKILINK_ANCHOR_ALIAS,
        }


@dataclass
class Attachment:
    path: Path
    referenced_by: Set[Path] = field(default_factory=set)


@dataclass
class Note:
    path: Path
    name: str
    title_anchors: Dict[str, str] = field(default_factory=dict)
    outgoing_links: List[Link] = field(default_factory=list)
    content: str = ""

    @property
    def stem(self) -> str:
        return self.path.stem


@dataclass
class NoteGraph:
    notes: Dict[Path, Note] = field(default_factory=dict)
    attachments: Dict[Path, Attachment] = field(default_factory=dict)
    name_to_paths: Dict[str, List[Path]] = field(default_factory=dict)
    backlinks: Dict[Path, Set[Path]] = field(default_factory=dict)

    def get_note_by_name(self, name: str) -> Optional[Note]:
        paths = self.name_to_paths.get(name, [])
        if len(paths) == 1:
            return self.notes[paths[0]]
        return None

    def get_notes_by_name(self, name: str) -> List[Note]:
        return [self.notes[p] for p in self.name_to_paths.get(name, [])]

    def get_backlinks(self, note_path: Path) -> Set[Path]:
        return self.backlinks.get(note_path, set())

    def all_note_names(self) -> Set[str]:
        return set(self.name_to_paths.keys())
