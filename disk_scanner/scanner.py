import os
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Generator, List, Optional

from .utils import format_size, format_timestamp, is_symlink_or_reparse

# Virtual pseudo-filesystems in Linux that should be skipped during disk scans
IGNORED_SYSTEM_DIRS = {"/proc", "/sys", "/dev", "/run"}


@dataclass
class FileInfo:
    path: str
    size_bytes: int
    size_formatted: str
    modified_time: str
    extension: str

    def to_dict(self) -> dict:
        return {
            "path": self.path,
            "size_bytes": self.size_bytes,
            "size_formatted": self.size_formatted,
            "modified_time": self.modified_time,
            "extension": self.extension,
        }


@dataclass
class ScanStats:
    total_files_scanned: int = 0
    total_dirs_scanned: int = 0
    permission_denied_count: int = 0
    error_count: int = 0
    duration_seconds: float = 0.0
    large_files_found: int = 0
    total_large_files_bytes: int = 0


class DiskScanner:
    """
    High-performance disk scanner using os.scandir and an iterative stack.
    Handles permission errors gracefully on Windows and Linux servers.
    """

    def __init__(
        self,
        target_path: str,
        min_size_mb: float = 100.0,
        follow_symlinks: bool = False,
        progress_callback: Optional[Callable[[int, int, str], None]] = None,
    ):
        self.target_path = os.path.abspath(target_path)
        self.min_size_bytes = int(min_size_mb * 1024 * 1024)
        self.follow_symlinks = follow_symlinks
        self.progress_callback = progress_callback
        self.stats = ScanStats()
        self.large_files: List[FileInfo] = []

    def scan(self) -> List[FileInfo]:
        """
        Executes scan and returns sorted list of FileInfo (largest first).
        """
        start_time = time.time()
        self.stats = ScanStats()
        self.large_files = []

        stack = [self.target_path]
        last_progress_update = 0.0

        while stack:
            current_dir = stack.pop()
            self.stats.total_dirs_scanned += 1

            try:
                with os.scandir(current_dir) as it:
                    for entry in it:
                        try:
                            # Avoid symlink loops if follow_symlinks is False
                            if not self.follow_symlinks and is_symlink_or_reparse(entry):
                                continue

                            if entry.is_dir(follow_symlinks=self.follow_symlinks):
                                if os.name != "nt":
                                    norm_p = os.path.normpath(entry.path)
                                    if norm_p in IGNORED_SYSTEM_DIRS:
                                        continue
                                stack.append(entry.path)
                            elif entry.is_file(follow_symlinks=self.follow_symlinks):
                                self.stats.total_files_scanned += 1

                                try:
                                    stat_res = entry.stat(follow_symlinks=self.follow_symlinks)
                                    file_size = stat_res.st_size

                                    if file_size >= self.min_size_bytes:
                                        _, ext = os.path.splitext(entry.name)
                                        file_info = FileInfo(
                                            path=entry.path,
                                            size_bytes=file_size,
                                            size_formatted=format_size(file_size),
                                            modified_time=format_timestamp(stat_res.st_mtime),
                                            extension=ext.lower() if ext else "N/A",
                                        )
                                        self.large_files.append(file_info)
                                        self.stats.large_files_found += 1
                                        self.stats.total_large_files_bytes += file_size
                                except (PermissionError, OSError):
                                    self.stats.error_count += 1

                                # Periodic progress notification
                                now = time.time()
                                if self.progress_callback and (now - last_progress_update > 0.15):
                                    self.progress_callback(
                                        self.stats.total_files_scanned,
                                        self.stats.large_files_found,
                                        entry.path,
                                    )
                                    last_progress_update = now

                        except PermissionError:
                            self.stats.permission_denied_count += 1
                        except OSError:
                            self.stats.error_count += 1

            except PermissionError:
                self.stats.permission_denied_count += 1
            except (FileNotFoundError, OSError):
                self.stats.error_count += 1

        self.stats.duration_seconds = time.time() - start_time

        # Sort large files by size descending
        self.large_files.sort(key=lambda x: x.size_bytes, reverse=True)
        return self.large_files
