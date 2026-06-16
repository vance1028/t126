from pathlib import Path
from typing import Set, Dict, List, Optional
from .models import Note, Link, NoteGraph, Attachment, LinkType
from .link_parser import LinkParser


class GraphBuilder:
    def __init__(self, vault_root: Path):
        self.vault_root = vault_root.resolve()
        self.attachment_extensions = {
            ".png", ".jpg", ".jpeg", ".gif", ".bmp", ".svg",
            ".pdf", ".doc", ".docx", ".xls", ".xlsx",
            ".txt", ".csv", ".zip", ".mp4", ".mp3",
        }

    def build(self) -> NoteGraph:
        graph = NoteGraph()
        md_files = self._find_markdown_files()
        attachment_files = self._find_attachments()

        for md_path in md_files:
            content = self._read_file(md_path)
            note = self._build_note(md_path, content)
            graph.notes[note.path] = note

            name = note.stem
            if name not in graph.name_to_paths:
                graph.name_to_paths[name] = []
            graph.name_to_paths[name].append(note.path)

        for att_path in attachment_files:
            graph.attachments[att_path] = Attachment(path=att_path)

        for note in graph.notes.values():
            self._resolve_links(note, graph)
            for link in note.outgoing_links:
                target = self._get_target_path(link, graph)
                if target and target in graph.notes:
                    if target not in graph.backlinks:
                        graph.backlinks[target] = set()
                    graph.backlinks[target].add(note.path)
                if link.link_type in {LinkType.ATTACHMENT, LinkType.IMAGE}:
                    att_path = self._resolve_attachment_path(link, note)
                    if att_path and att_path in graph.attachments:
                        graph.attachments[att_path].referenced_by.add(note.path)

        return graph

    def _find_markdown_files(self) -> List[Path]:
        return sorted(p for p in self.vault_root.rglob("*.md") if p.is_file())

    def _find_attachments(self) -> Set[Path]:
        attachments = set()
        for p in self.vault_root.rglob("*"):
            if p.is_file() and p.suffix.lower() in self.attachment_extensions:
                attachments.add(p.resolve())
        return attachments

    def _read_file(self, path: Path) -> str:
        try:
            return path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            return path.read_text(encoding="utf-8", errors="replace")

    def _build_note(self, path: Path, content: str) -> Note:
        resolved_path = path.resolve()
        note = Note(
            path=resolved_path,
            name=path.stem,
            content=content,
        )
        links, headings = LinkParser.parse_all(content, resolved_path)
        note.outgoing_links = links
        note.title_anchors = headings
        return note

    def _resolve_links(self, note: Note, graph: NoteGraph):
        for link in note.outgoing_links:
            if link.is_wikilink:
                candidates = graph.name_to_paths.get(link.target_note_name, [])
                if len(candidates) == 1:
                    link.target_path = candidates[0]
            elif link.link_type == LinkType.MARKDOWN_LINK and link.target_path:
                abs_path = (note.path.parent / link.target_path).resolve()
                if abs_path in graph.notes:
                    link.target_path = abs_path
                    link.target_note_name = abs_path.stem

    def _get_target_path(self, link: Link, graph: NoteGraph) -> Optional[Path]:
        if link.target_path and link.target_path in graph.notes:
            candidates = graph.name_to_paths.get(link.target_note_name, []) if link.target_note_name else []
            if link.is_wikilink and len(candidates) != 1:
                return None
            return link.target_path
        if link.is_wikilink and link.target_note_name:
            candidates = graph.name_to_paths.get(link.target_note_name, [])
            if len(candidates) == 1:
                return candidates[0]
        return None

    def _resolve_attachment_path(self, link: Link, note: Note) -> Optional[Path]:
        if not link.target_path:
            return None
        try:
            abs_path = (note.path.parent / link.target_path).resolve()
            return abs_path
        except Exception:
            return None
