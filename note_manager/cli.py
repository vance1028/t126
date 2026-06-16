from __future__ import annotations
import argparse
import sys
from pathlib import Path
from typing import Optional

from .link_graph import GraphBuilder
from .detector import IssueDetector
from .file_ops import FileManager
from .fixer import LinkFixer
from .reporter import Reporter


def _build_vault(vault_dir: Path):
    builder = GraphBuilder(vault_dir)
    return builder.build()


def cmd_scan(args):
    vault_dir = Path(args.vault).resolve()
    if not vault_dir.is_dir():
        print(f"错误: {vault_dir} 不是有效目录", file=sys.stderr)
        sys.exit(1)

    graph = _build_vault(vault_dir)
    detector = IssueDetector(graph, vault_dir)
    result = detector.detect_all()
    reporter = Reporter(graph, vault_dir)

    fmt = getattr(args, "format", "text")
    print(reporter.generate_issues_report(result, fmt=fmt))


def cmd_backlinks(args):
    vault_dir = Path(args.vault).resolve()
    if not vault_dir.is_dir():
        print(f"错误: {vault_dir} 不是有效目录", file=sys.stderr)
        sys.exit(1)

    graph = _build_vault(vault_dir)
    reporter = Reporter(graph, vault_dir)
    fmt = getattr(args, "format", "text")
    print(reporter.generate_backlinks_report(fmt=fmt))


def cmd_index(args):
    vault_dir = Path(args.vault).resolve()
    if not vault_dir.is_dir():
        print(f"错误: {vault_dir} 不是有效目录", file=sys.stderr)
        sys.exit(1)

    graph = _build_vault(vault_dir)
    reporter = Reporter(graph, vault_dir)
    content = reporter.generate_index()
    if args.output:
        out = Path(args.output).resolve()
        out.write_text(content, encoding="utf-8")
        print(f"索引已写入: {out}")
    else:
        print(content)


def cmd_rename(args):
    vault_dir = Path(args.vault).resolve()
    if not vault_dir.is_dir():
        print(f"错误: {vault_dir} 不是有效目录", file=sys.stderr)
        sys.exit(1)

    old_path = Path(args.source).resolve()
    new_path = Path(args.dest).resolve()

    if not old_path.exists():
        print(f"错误: 源文件不存在 {old_path}", file=sys.stderr)
        sys.exit(1)
    if new_path.exists() and old_path != new_path:
        print(f"错误: 目标文件已存在 {new_path}", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run
    no_backup = args.no_backup

    graph = _build_vault(vault_dir)
    fm = FileManager(vault_dir, backup=not no_backup)
    fixer = LinkFixer(graph, fm)
    reporter = Reporter(graph, vault_dir)

    result = fixer.rename_note(old_path, new_path, dry_run=dry_run)
    fmt = getattr(args, "format", "text")
    print(reporter.generate_fix_report(result, fmt=fmt))

    if dry_run:
        print("\n[dry-run] 未实际修改任何文件")


def cmd_fix(args):
    vault_dir = Path(args.vault).resolve()
    if not vault_dir.is_dir():
        print(f"错误: {vault_dir} 不是有效目录", file=sys.stderr)
        sys.exit(1)

    dry_run = args.dry_run
    no_backup = args.no_backup

    graph = _build_vault(vault_dir)
    detector = IssueDetector(graph, vault_dir)
    detection = detector.detect_all()

    fm = FileManager(vault_dir, backup=not no_backup)
    fixer = LinkFixer(graph, fm)
    reporter = Reporter(graph, vault_dir)

    result = fixer.fix_broken_links(detection, dry_run=dry_run)
    fmt = getattr(args, "format", "text")
    print(reporter.generate_fix_report(result, fmt=fmt))

    if dry_run:
        print("\n[dry-run] 未实际修改任何文件")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="note-manager",
        description="Markdown 笔记库链接管理工具 - 纯本地离线运行",
    )
    parser.add_argument(
        "-v", "--vault",
        required=True,
        help="笔记库根目录路径",
    )
    parser.add_argument(
        "--format",
        choices=["text", "json"],
        default="text",
        help="输出格式 (默认: text)",
    )

    sub = parser.add_subparsers(dest="command", required=True)

    p_scan = sub.add_parser("scan", help="扫描笔记库，检测死链、孤儿、歧义、未引用附件")
    p_scan.set_defaults(func=cmd_scan)

    p_bl = sub.add_parser("backlinks", help="生成每篇笔记的反向链接清单")
    p_bl.set_defaults(func=cmd_backlinks)

    p_idx = sub.add_parser("index", help="生成整库索引页")
    p_idx.add_argument("-o", "--output", help="输出文件路径，不传则打印到标准输出")
    p_idx.set_defaults(func=cmd_index)

    p_ren = sub.add_parser("rename", help="重命名/移动笔记，联动更新所有指向它的链接")
    p_ren.add_argument("source", help="源笔记文件路径")
    p_ren.add_argument("dest", help="目标笔记文件路径")
    p_ren.add_argument("--dry-run", action="store_true", help="只报告不实际修改文件")
    p_ren.add_argument("--no-backup", action="store_true", help="修改前不创建备份")
    p_ren.set_defaults(func=cmd_rename)

    p_fix = sub.add_parser("fix", help="自动修复能唯一匹配的死链")
    p_fix.add_argument("--dry-run", action="store_true", help="只报告不实际修改文件")
    p_fix.add_argument("--no-backup", action="store_true", help="修改前不创建备份")
    p_fix.set_defaults(func=cmd_fix)

    return parser


def main(argv: Optional[list] = None):
    parser = build_parser()
    args = parser.parse_args(argv)
    args.func(args)


if __name__ == "__main__":
    main()
