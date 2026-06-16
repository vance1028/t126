import re
from pathlib import Path
from typing import List, Tuple, Dict
from .models import Link, LinkType, Note


class LinkParser:
    WIKILINK_RE = re.compile(
        r"""\[\[
            (?P<target>[^\[\]|#]+?)
            (?:\#(?P<anchor>[^\[\]|]+?))?
            (?:\|(?P<alias>[^\[\]]+?))?
        \]\]""",
        re.VERBOSE,
    )

    MD_LINK_RE = re.compile(
        r"""(?P<prefix>!?)\[(?P<text>[^\]]*)\]\((?P<target>[^)]+)\)""",
        re.VERBOSE,
    )

    @staticmethod
    def _is_image(match) -> bool:
        return match.group("prefix") == "!"

    HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*#*\s*$", re.MULTILINE)

    @staticmethod
    def parse_wikilinks(content: str, source_path: Path) -> List[Link]:
        links = []
        for line_idx, line in enumerate(content.splitlines(), 1):
            for match in LinkParser.WIKILINK_RE.finditer(line):
                target = match.group("target").strip()
                anchor = match.group("anchor")
                alias = match.group("alias")

                if anchor and alias:
                    link_type = LinkType.WIKILINK_ANCHOR_ALIAS
                elif anchor:
                    link_type = LinkType.WIKILINK_ANCHOR
                elif alias:
                    link_type = LinkType.WIKILINK_ALIAS
                else:
                    link_type = LinkType.WIKILINK

                links.append(
                    Link(
                        source_path=source_path,
                        target_raw=match.group(0),
                        target_note_name=target,
                        anchor=anchor.strip() if anchor else None,
                        alias=alias.strip() if alias else None,
                        link_type=link_type,
                        line_number=line_idx,
                    )
                )
        return links

    @staticmethod
    def parse_markdown_links(content: str, source_path: Path) -> List[Link]:
        links = []
        for line_idx, line in enumerate(content.splitlines(), 1):
            for match in LinkParser.MD_LINK_RE.finditer(line):
                text = match.group("text")
                target = match.group("target").strip()
                is_image = LinkParser._is_image(match)

                if target.startswith("http://") or target.startswith("https://") or target.startswith("mailto:"):
                    continue

                p = Path(target)
                suffix = p.suffix.lower()

                if is_image:
                    link_type = LinkType.IMAGE
                elif suffix and suffix != ".md":
                    link_type = LinkType.ATTACHMENT
                else:
                    link_type = LinkType.MARKDOWN_LINK

                links.append(
                    Link(
                        source_path=source_path,
                        target_raw=match.group(0),
                        target_note_name=None,
                        target_path=p,
                        anchor=None,
                        alias=text if text else None,
                        link_type=link_type,
                        line_number=line_idx,
                    )
                )

                if suffix == ".md":
                    links[-1].target_note_name = p.stem
        return links

    @staticmethod
    def parse_attachments(content: str, source_path: Path) -> List[Link]:
        return []

    @staticmethod
    def parse_headings(content: str) -> Dict[str, str]:
        anchors = {}
        for match in LinkParser.HEADING_RE.finditer(content):
            title = match.group(2).strip()
            anchor = LinkParser._title_to_anchor(title)
            anchors[title] = anchor
            anchors[anchor] = anchor
        return anchors

    @staticmethod
    def _title_to_anchor(title: str) -> str:
        anchor = title.lower()
        anchor = re.sub(r"[^\w\u4e00-\u9fff\s-]", "", anchor)
        anchor = re.sub(r"\s+", "-", anchor)
        return anchor.strip("-")

    @staticmethod
    def parse_all(content: str, source_path: Path) -> Tuple[List[Link], Dict[str, str]]:
        wikilinks = LinkParser.parse_wikilinks(content, source_path)
        md_links = LinkParser.parse_markdown_links(content, source_path)
        attachments = LinkParser.parse_attachments(content, source_path)
        headings = LinkParser.parse_headings(content)
        all_links = wikilinks + md_links + attachments
        return all_links, headings
