from __future__ import annotations
import os
import re
import shutil
import hashlib
from datetime import datetime
from pathlib import Path
from typing import Dict, Optional, Tuple


class FileManager:
    def __init__(self, vault_root: Path, backup: bool = True):
        self.vault_root = vault_root.resolve()
        self.backup = backup
        self.backup_dir = self.vault_root / ".note_manager_backups"
        self._file_cache: Dict[Path, str] = {}
        self._content_hashes: Dict[Path, str] = {}

    def read_file(self, path: Path) -> str:
        path = path.resolve()
        if path in self._file_cache:
            return self._file_cache[path]
        try:
            content = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            content = path.read_text(encoding="utf-8", errors="replace")
        self._file_cache[path] = content
        self._content_hashes[path] = self._hash_content(content)
        return content

    def write_file(self, path: Path, content: str, dry_run: bool = False) -> bool:
        path = path.resolve()
        old_content = self._file_cache.get(path)
        if old_content is None and path.exists():
            old_content = self.read_file(path)

        if old_content == content:
            return False

        if old_content is not None:
            old_hash = self._content_hashes.get(path, self._hash_content(old_content))
            new_hash = self._hash_content(content)
            if old_hash == new_hash:
                return False

        if dry_run:
            self._file_cache[path] = content
            self._content_hashes[path] = self._hash_content(content)
            return True

        if self.backup and path.exists():
            self._create_backup(path)

        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        self._file_cache[path] = content
        self._content_hashes[path] = self._hash_content(content)
        return True

    def rename_file(self, old_path: Path, new_path: Path, dry_run: bool = False) -> bool:
        old_path = old_path.resolve()
        new_path = new_path.resolve()
        if old_path == new_path:
            return False
        if not old_path.exists():
            return False
        if new_path.exists() and new_path != old_path:
            return False

        if dry_run:
            content = self.read_file(old_path)
            self._file_cache[new_path] = content
            self._content_hashes[new_path] = self._content_hashes.get(
                old_path, self._hash_content(content)
            )
            return True

        if self.backup and old_path.exists():
            self._create_backup(old_path)

        new_path.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(old_path), str(new_path))

        if old_path in self._file_cache:
            self._file_cache[new_path] = self._file_cache.pop(old_path)
        if old_path in self._content_hashes:
            self._content_hashes[new_path] = self._content_hashes.pop(old_path)

        return True

    def move_file(self, src: Path, dst: Path, dry_run: bool = False) -> bool:
        return self.rename_file(src, dst, dry_run)

    def _create_backup(self, path: Path):
        if not path.exists():
            return
        self.backup_dir.mkdir(parents=True, exist_ok=True)
        rel_path = path.relative_to(self.vault_root)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        backup_name = f"{rel_path.as_posix().replace('/', '__')}.{timestamp}.bak"
        backup_path = self.backup_dir / backup_name
        counter = 1
        while backup_path.exists():
            backup_name = f"{rel_path.as_posix().replace('/', '__')}.{timestamp}_{counter}.bak"
            backup_path = self.backup_dir / backup_name
            counter += 1
        shutil.copy2(str(path), str(backup_path))

    @staticmethod
    def _hash_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def invalidate_cache(self, path: Optional[Path] = None):
        if path:
            path = path.resolve()
            self._file_cache.pop(path, None)
            self._content_hashes.pop(path, None)
        else:
            self._file_cache.clear()
            self._content_hashes.clear()

    def get_relative_path(self, from_path: Path, to_path: Path) -> Path:
        from_path = from_path.resolve()
        to_path = to_path.resolve()
        try:
            rel = Path(
                re.sub(
                    r"^\\./",
                    "",
                    str(Path(os.path.relpath(to_path, from_path.parent))).replace("\\", "/"),
                )
            )
            return rel
        except ValueError:
            return to_path
