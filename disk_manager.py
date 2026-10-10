#!/usr/bin/env python3
"""
Server Disk Manager - Standalone Single-File Version
Includes:
- Large file scanner & CSV/JSON exporter
- Bashtop-style interactive TUI with arrow key navigation
- File inspection & deletion
- Docker images & dangling/unused image cleanup
Zero external dependencies. Ideal for one-line curl/wget execution on servers.
"""

import argparse
import csv
import json
import os
import re
import shutil
import string
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional, Tuple

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass


def format_size(bytes_size: int) -> str:
    """Format a byte size into human readable string (B, KB, MB, GB, TB)."""
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_size < 1024.0 or unit == 'PB':
            if unit in ['B']:
                return f"{bytes_size} {unit}"
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def format_timestamp(timestamp: float) -> str:
    """Convert a posix timestamp to a readable date/time string."""
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "Unknown"


def is_symlink_or_reparse(entry: os.DirEntry) -> bool:
    """Check if a DirEntry is a symlink or reparse point."""
    try:
        return entry.is_symlink()
    except OSError:
        return False


def get_available_drives() -> list:
    """Returns list of mounted drives with total, used, and free space."""
    drives = []
    if os.name == "nt":
        for letter in string.ascii_uppercase:
            drive_path = f"{letter}:\\"
            if os.path.exists(drive_path):
                try:
                    usage = shutil.disk_usage(drive_path)
                    drives.append({
                        "path": drive_path,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                    })
                except (PermissionError, OSError):
                    pass
    else:
        for root in ["/", "/home", "/var"]:
            if os.path.exists(root):
                try:
                    usage = shutil.disk_usage(root)
                    drives.append({
                        "path": root,
                        "total": usage.total,
                        "used": usage.used,
                        "free": usage.free,
                    })
                except (PermissionError, OSError):
                    pass
    return drives


def get_default_scan_path() -> str:
    """Returns the root storage path of the server ('/' on Linux/Unix, 'C:\\' on Windows)."""
    if os.name == "nt":
        drives = get_available_drives()
        return drives[0]["path"] if drives else "C:\\"
    return "/"


# --- DOCKER MANAGER ---
def parse_size_to_bytes(size_str: str) -> int:
    s = size_str.strip().upper()
    match = re.match(r"^([0-9.]+)\s*([A-Z]+)$", s)
    if not match:
        return 0
    val, unit = match.groups()
    try:
        num = float(val)
    except ValueError:
        return 0

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
        "KIB": 1024,
        "MIB": 1024 * 1024,
        "GIB": 1024 * 1024 * 1024,
    }
    return int(num * multipliers.get(unit, 1))


@dataclass
class DockerImage:
    repository: str
    tag: str
    image_id: str
    size_str: str
    size_bytes: int
    created: str
    in_use: bool
    is_dangling: bool

    @property
    def full_name(self) -> str:
        if self.is_dangling or self.repository == "<none>":
            return f"<none>:<none> ({self.image_id[:12]})"
        return f"{self.repository}:{self.tag}"


class DockerManager:
    @staticmethod
    def is_docker_running() -> Tuple[bool, str]:
        if not shutil.which("docker"):
            return False, "Docker CLI is not installed or not in PATH."
        try:
            res = subprocess.run(["docker", "info"], capture_output=True, text=True, timeout=4)
            if res.returncode == 0:
                return True, "Docker daemon is running."
            return False, f"Docker daemon not responding: {res.stderr.strip()[:100]}"
        except subprocess.TimeoutExpired:
            return False, "Docker daemon check timed out."
        except Exception as e:
            return False, f"Docker check failed: {str(e)}"

    @staticmethod
    def list_images() -> Tuple[List[DockerImage], str]:
        running, msg = DockerManager.is_docker_running()
        if not running:
            return [], msg
        try:
            used_images = set()
            ps_res = subprocess.run(["docker", "ps", "-a", "--format", "{{.Image}}"], capture_output=True, text=True, timeout=5)
            if ps_res.returncode == 0:
                for line in ps_res.stdout.splitlines():
                    img = line.strip()
                    if img:
                        used_images.add(img)

            img_res = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if img_res.returncode != 0:
                return [], f"Failed to list images: {img_res.stderr.strip()}"

            images: List[DockerImage] = []
            for line in img_res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 5:
                    repo, tag, img_id, size_str, created = parts[:5]
                    is_dangling = repo == "<none>" or tag == "<none>"
                    in_use = (img_id in used_images) or (f"{repo}:{tag}" in used_images) or (repo in used_images)
                    images.append(
                        DockerImage(
                            repository=repo,
                            tag=tag,
                            image_id=img_id,
                            size_str=size_str,
                            size_bytes=parse_size_to_bytes(size_str),
                            created=created,
                            in_use=in_use,
                            is_dangling=is_dangling,
                        )
                    )
            images.sort(key=lambda x: x.size_bytes, reverse=True)
            return images, ""
        except Exception as e:
            return [], f"Error querying Docker: {str(e)}"

    @staticmethod
    def remove_image(image_id: str, force: bool = False) -> Tuple[bool, str]:
        cmd = ["docker", "rmi"]
        if force:
            cmd.append("-f")
        cmd.append(image_id)
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return True, f"Successfully removed image {image_id}"
            return False, res.stderr.strip() or res.stdout.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def prune_unused_images(all_unused: bool = True) -> Tuple[bool, str]:
        cmd = ["docker", "image", "prune", "-f"]
        if all_unused:
            cmd.append("-a")
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                match = re.search(r"Total reclaimed space:\s*(.+)", res.stdout)
                reclaimed = match.group(1) if match else "images pruned"
                return True, f"Prune successful: Reclaimed {reclaimed}"
            return False, res.stderr.strip()
        except Exception as e:
            return False, str(e)


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


IGNORED_SYSTEM_DIRS = {"/proc", "/sys", "/dev", "/run"}


class DiskScanner:
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
        self.large_files.sort(key=lambda x: x.size_bytes, reverse=True)
        return self.large_files


class Reporter:
    @staticmethod
    def print_summary(stats: ScanStats, target_path: str, min_size_mb: float) -> None:
        print("\n" + "=" * 75)
        print("                         SERVER DISK SCAN SUMMARY")
        print("=" * 75)
        print(f"Target Path                      : {target_path}")
        print(f"Size Threshold                   : >= {min_size_mb:.2f} MB")
        print(f"Scan Duration                    : {stats.duration_seconds:.2f} seconds")
        print(f"Total Files Scanned              : {stats.total_files_scanned:,}")
        print(f"Total Directories Scanned        : {stats.total_dirs_scanned:,}")
        print(f"Large Files Found                : {stats.large_files_found:,}")
        print(f"Total Size of Large Files        : {format_size(stats.total_large_files_bytes)}")
        if stats.permission_denied_count > 0:
            print(f"Permission Denied Paths          : {stats.permission_denied_count:,}")
        if stats.error_count > 0:
            print(f"Operating System Errors          : {stats.error_count:,}")
        print("=" * 75 + "\n")

    @staticmethod
    def print_drives(drives: list) -> None:
        if not drives:
            print("No storage drives detected.")
            return

        print("\n" + "=" * 75)
        print("                    SERVER STORAGE DRIVES & USAGE")
        print("=" * 75)
        header = f"{'Drive / Path':<16} | {'Total Size':<12} | {'Used Space':<12} | {'Free Space':<12} | {'Usage %'}"
        print(header)
        print("-" * 75)
        for d in drives:
            pct = (d['used'] / d['total'] * 100) if d['total'] > 0 else 0
            row = (
                f"{d['path']:<16} | "
                f"{format_size(d['total']):<12} | "
                f"{format_size(d['used']):<12} | "
                f"{format_size(d['free']):<12} | "
                f"{pct:.1f}%"
            )
            print(row)
        print("=" * 75 + "\n")

    @staticmethod
    def print_table(files: List[FileInfo], max_rows: int = 50) -> None:
        if not files:
            print("[INFO] No files found matching the minimum size criteria.")
            return

        shown_count = min(len(files), max_rows)
        print(f"\n[RESULTS] Large Files List (Showing top {shown_count} of {len(files)} files):")
        print("-" * 115)
        header = f"{'#':<5} | {'Size':<12} | {'Ext':<6} | {'Last Modified':<20} | {'Full File Path'}"
        print(header)
        print("-" * 115)

        for idx, f in enumerate(files[:max_rows], start=1):
            row = f"{idx:<5} | {f.size_formatted:<12} | {f.extension:<6} | {f.modified_time:<20} | {f.path}"
            print(row)

        print("-" * 115)
        if len(files) > max_rows:
            remaining = len(files) - max_rows
            print(f"... and {remaining:,} more files. Export to CSV or JSON to inspect all files.")

    @staticmethod
    def export_to_csv(files: List[FileInfo], file_path: str) -> str:
        abs_path = os.path.abspath(file_path)
        with open(abs_path, mode="w", newline="", encoding="utf-8-sig") as f:
            writer = csv.writer(f)
            writer.writerow(["#", "File Path", "Size (Bytes)", "Formatted Size", "Extension", "Last Modified"])
            for idx, item in enumerate(files, start=1):
                writer.writerow([
                    idx,
                    item.path,
                    item.size_bytes,
                    item.size_formatted,
                    item.extension,
                    item.modified_time,
                ])
        return abs_path

    @staticmethod
    def export_to_json(files: List[FileInfo], stats: ScanStats, file_path: str) -> str:
        abs_path = os.path.abspath(file_path)
        data = {
            "statistics": {
                "total_files_scanned": stats.total_files_scanned,
                "total_dirs_scanned": stats.total_dirs_scanned,
                "large_files_found": stats.large_files_found,
                "total_large_files_bytes": stats.total_large_files_bytes,
                "total_large_files_formatted": format_size(stats.total_large_files_bytes),
                "duration_seconds": round(stats.duration_seconds, 2),
                "permission_denied_count": stats.permission_denied_count,
                "error_count": stats.error_count,
            },
            "files": [f.to_dict() for f in files],
        }
        with open(abs_path, mode="w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return abs_path


# --- TUI / BASHTOP IMPLEMENTATION ---
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_WHITE = "\033[37m"
BG_CYAN = "\033[46m\033[30m"


DOS_KEY_MAP = {
    b"H": "UP",
    b"\x48": "UP",
    b"8": "UP",
    b"\x8d": "UP",      # Ctrl+Up
    b"P": "DOWN",
    b"\x50": "DOWN",
    b"2": "DOWN",
    b"\x91": "DOWN",    # Ctrl+Down
    b"K": "LEFT",
    b"\x4b": "LEFT",
    b"4": "LEFT",
    b"s": "LEFT",       # Ctrl+Left
    b"M": "RIGHT",
    b"\x4d": "RIGHT",
    b"6": "RIGHT",
    b"t": "RIGHT",      # Ctrl+Right
    b"S": "DELETE",
    b"\x53": "DELETE",
    b".": "DELETE",
    b"\x93": "DELETE",  # Ctrl+Del
    b"I": "PAGE_UP",
    b"\x49": "PAGE_UP",
    b"9": "PAGE_UP",
    b"\x84": "PAGE_UP", # Ctrl+PgUp
    b"Q": "PAGE_DOWN",
    b"\x51": "PAGE_DOWN",
    b"3": "PAGE_DOWN",
    b"v": "PAGE_DOWN",  # Ctrl+PgDn
    b"G": "HOME",
    b"\x47": "HOME",
    b"7": "HOME",
    b"w": "HOME",       # Ctrl+Home
    b"O": "END",
    b"\x4f": "END",
    b"1": "END",
    b"u": "END",        # Ctrl+End
    b"R": "INSERT",
    b"\x52": "INSERT",
    b"0": "INSERT",
}


def parse_escape_sequence(full: bytes) -> str:
    """
    Decodes an ANSI/VT escape sequence into a normalized key action name.
    Supports standard VT100, xterm, ConPTY, rxvt, and cursor application modes.
    """
    if not full or full == b"\x1b":
        return "ESC"

    # Arrow keys across terminal emulators
    if full.endswith((b"A", b"a")):
        return "UP"
    if full.endswith((b"B", b"b")):
        return "DOWN"
    if full.endswith((b"C", b"c")):
        return "RIGHT"
    if full.endswith((b"D", b"d")):
        return "LEFT"

    # Paging and special navigation keys
    if b"5~" in full or full.endswith(b"I"):
        return "PAGE_UP"
    if b"6~" in full or full.endswith(b"Q"):
        return "PAGE_DOWN"
    if b"3~" in full or full.endswith(b"S"):
        return "DELETE"
    if b"1~" in full or b"7~" in full or full.endswith((b"H", b"G")):
        return "HOME"
    if b"4~" in full or b"8~" in full or full.endswith((b"F", b"O")):
        return "END"

    return "UNKNOWN"


def get_key() -> str:
    """
    Cross-platform single keypress reader.
    Handles DOS scancodes (\\xe0, \\x00) and ANSI escape sequences (\\x1b[A, \\x1bOA, etc.)
    preventing accidental exit in modern terminals (PyCharm, Windows Terminal, VS Code, SSH).
    """
    if os.name == "nt":
        import msvcrt

        ch = msvcrt.getch()

        # 1. DOS special keys (\x00 or \xe0)
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            return DOS_KEY_MAP.get(ch2, "UNKNOWN")

        # 2. ANSI VT escape sequences (Windows Terminal, PyCharm, ConPTY, VS Code, SSH)
        if ch == b"\x1b":
            seq = [b"\x1b"]
            start_time = time.time()
            while (time.time() - start_time) < 0.15:
                if msvcrt.kbhit():
                    seq.append(msvcrt.getch())
                    start_time = time.time()
                    if len(seq) >= 10:
                        break
                else:
                    time.sleep(0.005)

            return parse_escape_sequence(b"".join(seq))

        if ch in (b"\t",):
            return "TAB"
        if ch in (b"\r", b"\n"):
            return "ENTER"
        if ch in (b"\x08", b"\x7f"):
            return "BACKSPACE"

        try:
            return ch.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    else:
        import select
        import termios
        import tty

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                seq = [b"\x1b"]
                start_time = time.time()
                while (time.time() - start_time) < 0.15:
                    r, _, _ = select.select([sys.stdin], [], [], 0.03)
                    if r:
                        c = sys.stdin.read(1)
                        seq.append(c.encode("utf-8", errors="ignore"))
                        start_time = time.time()
                        if len(seq) >= 10:
                            break
                    else:
                        break

                return parse_escape_sequence(b"".join(seq))

            if ch == "\t":
                return "TAB"
            if ch in ("\r", "\n"):
                return "ENTER"
            if ch in ("\x7f", "\x08"):
                return "BACKSPACE"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def make_gauge_bar(used_bytes: int, total_bytes: int, length: int = 24) -> str:
    if total_bytes <= 0:
        return "[ " + "░" * length + " ]"
    pct = min(1.0, max(0.0, used_bytes / total_bytes))
    fill_len = int(pct * length)
    empty_len = length - fill_len
    color = C_GREEN if pct < 0.70 else (C_YELLOW if pct < 0.90 else C_RED)
    return f"[{color}{'█' * fill_len}{C_RESET}{C_DIM}{'░' * empty_len}{C_RESET}] {color}{pct * 100:.1f}%{C_RESET}"


class DiskManagerTUI:
    def __init__(self, target_path: Optional[str] = None, min_size_mb: float = 100.0):
        if not target_path or target_path == ".":
            target_path = get_default_scan_path()
        self.target_path = os.path.abspath(target_path)
        self.min_size_mb = min_size_mb
        self.active_tab = "files"

        # Files state
        self.files: List[FileInfo] = []
        self.filtered_files: List[FileInfo] = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.filter_query = ""
        self.sort_mode = "size_desc"
        self.total_freed_bytes = 0

        # Docker state
        self.docker_images: List[DockerImage] = []
        self.docker_selected_idx = 0
        self.docker_scroll_offset = 0
        self.docker_error = ""

        # Status notification
        self.status_msg = ""
        self.status_color = C_GREEN

    def load_files(self) -> None:
        scanner = DiskScanner(target_path=self.target_path, min_size_mb=self.min_size_mb)
        self.files = scanner.scan()
        self.apply_filter_and_sort()
        self.selected_idx = 0
        self.scroll_offset = 0

    def load_docker(self) -> None:
        imgs, err = DockerManager.list_images()
        self.docker_images = imgs
        self.docker_error = err
        self.docker_selected_idx = 0
        self.docker_scroll_offset = 0

    def apply_filter_and_sort(self) -> None:
        if self.filter_query:
            q = self.filter_query.lower()
            self.filtered_files = [f for f in self.files if q in f.path.lower() or q in f.extension.lower()]
        else:
            self.filtered_files = list(self.files)

        if self.sort_mode == "size_desc":
            self.filtered_files.sort(key=lambda x: x.size_bytes, reverse=True)
        elif self.sort_mode == "size_asc":
            self.filtered_files.sort(key=lambda x: x.size_bytes)
        elif self.sort_mode == "name":
            self.filtered_files.sort(key=lambda x: os.path.basename(x.path).lower())
        elif self.sort_mode == "date":
            self.filtered_files.sort(key=lambda x: x.modified_time, reverse=True)

        if self.selected_idx >= len(self.filtered_files):
            self.selected_idx = max(0, len(self.filtered_files) - 1)

    def draw(self) -> None:
        term_cols, term_lines = shutil.get_terminal_size((100, 30))
        lines = []
        w = max(75, min(term_cols, 130))

        header_title = " 🗄️  SERVER DISK MANAGER - BASHTOP DASHBOARD  "
        lines.append(f"{C_CYAN}┌" + "─" * (w - 2) + f"┐{C_RESET}")
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{header_title.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        tab1_style = f"{BG_CYAN}{C_BOLD} [1] 📁 Large Files Disk Scan {C_RESET}" if self.active_tab == "files" else f"{C_DIM} [1] 📁 Large Files Disk Scan {C_RESET}"
        tab2_style = f"{BG_CYAN}{C_BOLD} [2] 🐳 Docker Images & Storage {C_RESET}" if self.active_tab == "docker" else f"{C_DIM} [2] 🐳 Docker Images & Storage {C_RESET}"
        tab_hint = f"{C_YELLOW}(Press TAB or 1/2 to switch tabs){C_RESET}"
        clean_tab_line = f"  [1] 📁 Large Files Disk Scan     [2] 🐳 Docker Images & Storage     (Press TAB or 1/2 to switch tabs)"
        spacing = max(1, w - len(clean_tab_line) - 2)
        lines.append(f"{C_CYAN}│{C_RESET} {tab1_style}   {tab2_style}    {tab_hint}{' ' * spacing}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        if self.active_tab == "files":
            self._draw_files_tab(lines, w, term_lines)
        else:
            self._draw_docker_tab(lines, w, term_lines)

        lines.append(f"{C_CYAN}└" + "─" * (w - 2) + f"┘{C_RESET}")
        output_str = "\033[H" + "\n".join(lines) + "\033[J"
        try:
            sys.stdout.write(output_str)
            sys.stdout.flush()
        except UnicodeEncodeError:
            try:
                sys.stdout.buffer.write(output_str.encode("utf-8", errors="replace"))
                sys.stdout.buffer.flush()
            except Exception:
                pass
        except Exception:
            pass

    def _draw_files_tab(self, lines: List[str], w: int, term_lines: int) -> None:
        drives = get_available_drives()
        if drives:
            d = drives[0]
            for candidate in drives:
                if self.target_path.startswith(candidate["path"]):
                    d = candidate
                    break
            gauge = make_gauge_bar(d["used"], d["total"], length=max(15, w // 5))
            storage_text = f" Storage [{d['path']}] {gauge} | Used: {format_size(d['used'])} | Free: {C_GREEN}{format_size(d['free'])}{C_RESET} | Total: {format_size(d['total'])}"
            lines.append(f"{C_CYAN}│{C_RESET} {storage_text.ljust(w - 4)[:w - 4]} {C_CYAN}│{C_RESET}")
            lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        total_size_bytes = sum(f.size_bytes for f in self.filtered_files)
        sort_names = {"size_desc": "Size (Largest)", "size_asc": "Size (Smallest)", "name": "Name (A-Z)", "date": "Date"}
        meta_left = f" Path: {self.target_path} (>= {self.min_size_mb:.0f} MB)"
        meta_right = f"Files: {len(self.filtered_files):,} | Total: {format_size(total_size_bytes)} | Sort: {sort_names.get(self.sort_mode)} "
        spacing = max(1, w - len(meta_left) - len(meta_right) - 2)
        lines.append(f"{C_CYAN}│{C_RESET}{C_DIM}{(meta_left + ' ' * spacing + meta_right)[:w - 2].ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        if self.filter_query:
            lines.append(f"{C_CYAN}│{C_RESET}{C_YELLOW}{f' Filter: {self.filter_query}'.ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
        table_hdr = f"  {'#':<4} | {'SIZE':<11} | {'EXT':<6} | {'MODIFIED':<19} | FILE PATH"
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{table_hdr.ljust(w - 2)[:w - 2]}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        footer_height = 5
        header_height = len(lines)
        table_height = max(5, term_lines - header_height - footer_height)

        if self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx
        elif self.selected_idx >= self.scroll_offset + table_height:
            self.scroll_offset = self.selected_idx - table_height + 1

        visible_files = self.filtered_files[self.scroll_offset : self.scroll_offset + table_height]

        if not self.filtered_files:
            empty_msg = "[ No files match current criteria ]"
            lines.append(f"{C_CYAN}│{C_RESET}{empty_msg.center(w - 2)}{C_CYAN}│{C_RESET}")
            for _ in range(table_height - 1):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")
        else:
            for i, f in enumerate(visible_files):
                actual_idx = self.scroll_offset + i
                is_selected = actual_idx == self.selected_idx
                max_path_w = max(20, w - 52)
                path_str = f.path if len(f.path) <= max_path_w else "..." + f.path[-(max_path_w - 3):]
                row_content = f"  {actual_idx + 1:<4} | {f.size_formatted:<11} | {f.extension:<6} | {f.modified_time:<19} | {path_str}"
                row_padded = row_content.ljust(w - 2)[: w - 2]
                if is_selected:
                    lines.append(f"{C_CYAN}│{C_RESET}{BG_CYAN}{C_BOLD}{row_padded}{C_RESET}{C_CYAN}│{C_RESET}")
                else:
                    lines.append(f"{C_CYAN}│{C_RESET}{row_padded}{C_CYAN}│{C_RESET}")

            for _ in range(table_height - len(visible_files)):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
        status_line = self.status_msg if self.status_msg else "Ready. Use arrows to browse, 'd' to delete selected file."
        if self.total_freed_bytes > 0:
            status_line = f"[Freed: {format_size(self.total_freed_bytes)}] " + status_line
        lines.append(f"{C_CYAN}│{C_RESET} {self.status_color}{status_line.ljust(w - 4)[:w - 4]}{C_RESET} {C_CYAN}│{C_RESET}")

        hotkeys = " [TAB] Docker  [↑/↓] Move  [d/DEL] Delete File  [o] Details  [/] Search  [s] Sort  [r] Rescan  [q] Quit "
        lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

    def _draw_docker_tab(self, lines: List[str], w: int, term_lines: int) -> None:
        if self.docker_error:
            err_box = f" [!] Docker Status: {self.docker_error} "
            lines.append(f"{C_CYAN}│{C_RESET}{C_RED}{err_box.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
            lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
            hint = "Please start Docker Desktop or the Docker daemon, then press [r] to refresh."
            lines.append(f"{C_CYAN}│{C_RESET}{hint.center(w - 2)}{C_CYAN}│{C_RESET}")
            for _ in range(max(6, term_lines - 16)):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")
            lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
            hotkeys = " [TAB] Switch to Files  [r] Retry Docker Check  [q] Quit "
            lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
            return

        total_docker_bytes = sum(img.size_bytes for img in self.docker_images)
        unused_count = sum(1 for img in self.docker_images if not img.in_use)
        dangling_count = sum(1 for img in self.docker_images if img.is_dangling)

        meta_left = f" Docker Images: {len(self.docker_images)} (Total: {format_size(total_docker_bytes)})"
        meta_right = f"Unused Images: {unused_count} | Dangling: {dangling_count} "
        spacing = max(1, w - len(meta_left) - len(meta_right) - 2)
        lines.append(f"{C_CYAN}│{C_RESET}{C_DIM}{(meta_left + ' ' * spacing + meta_right)[:w - 2].ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        table_hdr = f"  {'#':<4} | {'STATUS':<10} | {'REPOSITORY:TAG':<35} | {'IMAGE ID':<14} | {'SIZE':<10} | CREATED"
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{table_hdr.ljust(w - 2)[:w - 2]}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        footer_height = 5
        header_height = len(lines)
        table_height = max(5, term_lines - header_height - footer_height)

        if self.docker_selected_idx < self.docker_scroll_offset:
            self.docker_scroll_offset = self.docker_selected_idx
        elif self.docker_selected_idx >= self.docker_scroll_offset + table_height:
            self.docker_scroll_offset = self.docker_selected_idx - table_height + 1

        visible_imgs = self.docker_images[self.docker_scroll_offset : self.docker_scroll_offset + table_height]

        if not self.docker_images:
            empty_msg = "[ No Docker images found on this server ]"
            lines.append(f"{C_CYAN}│{C_RESET}{empty_msg.center(w - 2)}{C_CYAN}│{C_RESET}")
            for _ in range(table_height - 1):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")
        else:
            for i, img in enumerate(visible_imgs):
                actual_idx = self.docker_scroll_offset + i
                is_selected = actual_idx == self.docker_selected_idx

                if img.in_use:
                    status_lbl = f"{C_GREEN}[IN USE]{C_RESET}"
                    status_plain = "[IN USE]  "
                elif img.is_dangling:
                    status_lbl = f"{C_RED}[DANGLING]{C_RESET}"
                    status_plain = "[DANGLING]"
                else:
                    status_lbl = f"{C_YELLOW}[UNUSED]{C_RESET}"
                    status_plain = "[UNUSED]  "

                full_repo = img.full_name
                if len(full_repo) > 33:
                    full_repo = full_repo[:30] + "..."

                row_plain = f"  {actual_idx + 1:<4} | {status_plain:<10} | {full_repo:<35} | {img.image_id[:12]:<14} | {img.size_str:<10} | {img.created}"
                row_padded = row_plain.ljust(w - 2)[: w - 2]

                if is_selected:
                    lines.append(f"{C_CYAN}│{C_RESET}{BG_CYAN}{C_BOLD}{row_padded}{C_RESET}{C_CYAN}│{C_RESET}")
                else:
                    row_color = f"  {actual_idx + 1:<4} | {status_lbl:<19} | {full_repo:<35} | {img.image_id[:12]:<14} | {img.size_str:<10} | {img.created}"
                    lines.append(f"{C_CYAN}│{C_RESET}{row_color.ljust(w + 7)[:w + 7]}{C_CYAN}│{C_RESET}")

            for _ in range(table_height - len(visible_imgs)):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
        status_line = self.status_msg if self.status_msg else "Use 'd' to delete selected image, 'p' to prune all unused images."
        lines.append(f"{C_CYAN}│{C_RESET} {self.status_color}{status_line.ljust(w - 4)[:w - 4]}{C_RESET} {C_CYAN}│{C_RESET}")

        hotkeys = " [TAB] Files  [↑/↓] Move  [d/DEL] Remove Image  [p] Prune Unused  [r] Refresh  [q] Quit "
        lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

    def show_details(self) -> None:
        if not self.filtered_files:
            return
        f = self.filtered_files[self.selected_idx]
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 90)
        sys.stdout.write("\033[2J\033[H")
        print("\n" + "=" * w)
        print(f"{C_BOLD}FILE DETAILS{C_RESET}".center(w))
        print("=" * w)
        print(f"{C_CYAN}Path         :{C_RESET} {f.path}")
        print(f"{C_CYAN}Exact Bytes  :{C_RESET} {f.size_bytes:,} bytes")
        print(f"{C_CYAN}Formatted    :{C_RESET} {f.size_formatted}")
        print(f"{C_CYAN}Extension    :{C_RESET} {f.extension}")
        print(f"{C_CYAN}Last Modified:{C_RESET} {f.modified_time}")
        print("=" * w)
        print(f"\n{C_YELLOW}Press any key to return...{C_RESET}")
        get_key()

    def delete_selected_file(self) -> None:
        if not self.filtered_files:
            return
        f = self.filtered_files[self.selected_idx]
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 95)
        sys.stdout.write("\033[2J\033[H")
        print("\n" + f"{C_RED}╔" + "═" * (w - 2) + f"╗{C_RESET}")
        print(f"{C_RED}║{C_BOLD}{C_WHITE}{'⚠️  CONFIRM FILE DELETION  ⚠️'.center(w - 2)}{C_RESET}{C_RED}║{C_RESET}")
        print(f"{C_RED}╠" + "═" * (w - 2) + f"╣{C_RESET}")
        print(f"{C_RED}║{C_RESET} Target File : {C_BOLD}{f.path[:w - 18]}{C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET} File Size   : {C_YELLOW}{f.size_formatted} ({f.size_bytes:,} bytes){C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET} Last Modified: {f.modified_time}".ljust(w - 1) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET}" + " " * (w - 2) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET}{C_BOLD}{C_RED} CAUTION: This will permanently erase the file from disk! {C_RESET}".center(w + 14) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}╚" + "═" * (w - 2) + f"╝{C_RESET}\n")

        sys.stdout.write(f"Type '{C_BOLD}yes{C_RESET}' or press '{C_BOLD}y{C_RESET}' to confirm deletion: ")
        sys.stdout.flush()
        ans = input().strip().lower()

        if ans in ("y", "yes"):
            try:
                os.remove(f.path)
                self.total_freed_bytes += f.size_bytes
                self.status_msg = f"[DELETED] Deleted '{os.path.basename(f.path)}' (Freed: {f.size_formatted})"
                self.status_color = C_GREEN
                self.files = [item for item in self.files if item.path != f.path]
                self.apply_filter_and_sort()
            except PermissionError:
                self.status_msg = f"[ERROR] Permission Denied: Cannot delete '{os.path.basename(f.path)}'."
                self.status_color = C_RED
            except Exception as e:
                self.status_msg = f"[ERROR] Could not delete file: {str(e)}"
                self.status_color = C_RED
        else:
            self.status_msg = "[CANCELLED] Deletion cancelled."
            self.status_color = C_YELLOW

    def delete_selected_docker_image(self) -> None:
        if not self.docker_images:
            return
        img = self.docker_images[self.docker_selected_idx]
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 95)
        sys.stdout.write("\033[2J\033[H")
        print("\n" + f"{C_RED}╔" + "═" * (w - 2) + f"╗{C_RESET}")
        print(f"{C_RED}║{C_BOLD}{C_WHITE}{'⚠️  CONFIRM DOCKER IMAGE REMOVAL  ⚠️'.center(w - 2)}{C_RESET}{C_RED}║{C_RESET}")
        print(f"{C_RED}╠" + "═" * (w - 2) + f"╣{C_RESET}")
        print(f"{C_RED}║{C_RESET} Repository:Tag : {C_BOLD}{img.full_name[:w - 20]}{C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET} Image ID       : {C_CYAN}{img.image_id}{C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET} Size           : {C_YELLOW}{img.size_str}{C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        status_txt = "IN USE BY CONTAINERS" if img.in_use else "UNUSED (Safe to delete)"
        color_st = C_RED if img.in_use else C_GREEN
        print(f"{C_RED}║{C_RESET} Status         : {color_st}{status_txt}{C_RESET}".ljust(w + 8) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET}" + " " * (w - 2) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}║{C_RESET}{C_BOLD}{C_RED} CAUTION: This will delete the Docker image from local storage! {C_RESET}".center(w + 14) + f"{C_RED}║{C_RESET}")
        print(f"{C_RED}╚" + "═" * (w - 2) + f"╝{C_RESET}\n")

        sys.stdout.write(f"Type '{C_BOLD}yes{C_RESET}' or press '{C_BOLD}y{C_RESET}' to remove this image: ")
        sys.stdout.flush()
        ans = input().strip().lower()

        if ans in ("y", "yes"):
            ok, msg = DockerManager.remove_image(img.image_id, force=img.in_use)
            if ok:
                self.status_msg = f"[DOCKER] Removed image '{img.full_name}'"
                self.status_color = C_GREEN
                self.load_docker()
            else:
                self.status_msg = f"[ERROR] Failed to remove image: {msg[:60]}"
                self.status_color = C_RED
        else:
            self.status_msg = "[CANCELLED] Docker image removal cancelled."
            self.status_color = C_YELLOW

    def prune_docker_images(self) -> None:
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 95)
        sys.stdout.write("\033[2J\033[H")
        print("\n" + f"{C_YELLOW}╔" + "═" * (w - 2) + f"╗{C_RESET}")
        print(f"{C_YELLOW}║{C_BOLD}{C_WHITE}{'⚠️  PRUNE ALL UNUSED DOCKER IMAGES  ⚠️'.center(w - 2)}{C_RESET}{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}╠" + "═" * (w - 2) + f"╣{C_RESET}")
        print(f"{C_YELLOW}║{C_RESET} This command runs: {C_BOLD}docker image prune -a -f{C_RESET}".ljust(w + 8) + f"{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}║{C_RESET} It will delete ALL images not associated with a container.".ljust(w - 1) + f"{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}╚" + "═" * (w - 2) + f"╝{C_RESET}\n")

        sys.stdout.write(f"Type '{C_BOLD}yes{C_RESET}' or press '{C_BOLD}y{C_RESET}' to prune unused images: ")
        sys.stdout.flush()
        ans = input().strip().lower()

        if ans in ("y", "yes"):
            ok, msg = DockerManager.prune_unused_images(all_unused=True)
            if ok:
                self.status_msg = f"[DOCKER PRUNE] {msg}"
                self.status_color = C_GREEN
                self.load_docker()
            else:
                self.status_msg = f"[ERROR] Prune failed: {msg[:60]}"
                self.status_color = C_RED
        else:
            self.status_msg = "[CANCELLED] Prune cancelled."
            self.status_color = C_YELLOW

    def prompt_filter(self) -> None:
        sys.stdout.write("\033[H\033[2J")
        print("\nEnter keyword or extension to filter (empty to clear):")
        sys.stdout.write("Search: ")
        sys.stdout.flush()
        try:
            query = input().strip()
            self.filter_query = query
            self.apply_filter_and_sort()
            self.selected_idx = 0
            self.scroll_offset = 0
            self.status_msg = f"Filter set to: '{query}'" if query else "Filter cleared."
            self.status_color = C_CYAN
        except Exception:
            pass

    def toggle_sort(self) -> None:
        modes = ["size_desc", "size_asc", "name", "date"]
        curr_idx = modes.index(self.sort_mode)
        self.sort_mode = modes[(curr_idx + 1) % len(modes)]
        self.apply_filter_and_sort()
        self.status_msg = f"Sort mode changed to: {self.sort_mode}"
        self.status_color = C_CYAN

    def run(self) -> None:
        sys.stdout.write("\033[?25l\033[2J")
        sys.stdout.flush()
        try:
            print(f"\n[SCANNING] Initializing scan for {self.target_path} (>= {self.min_size_mb:.0f} MB)...")
            self.load_files()
            self.load_docker()
            while True:
                self.draw()
                key = get_key()
                if key in ("q", "Q"):
                    break
                elif key == "ESC":
                    if self.filter_query:
                        self.filter_query = ""
                        self.apply_filter_and_sort()
                        self.status_msg = "Filter cleared."
                        self.status_color = C_CYAN
                    else:
                        self.status_msg = "Press 'q' to quit."
                        self.status_color = C_YELLOW
                elif key in ("TAB", "tab"):
                    self.active_tab = "docker" if self.active_tab == "files" else "files"
                    self.status_msg = f"Switched to {self.active_tab.upper()} tab."
                    self.status_color = C_CYAN
                elif key == "1":
                    self.active_tab = "files"
                    self.status_msg = "Switched to Large Files tab."
                    self.status_color = C_CYAN
                elif key == "2":
                    self.active_tab = "docker"
                    self.status_msg = "Switched to Docker Images tab."
                    self.status_color = C_CYAN
                elif key in ("UP", "k", "K", "w", "W"):
                    if self.active_tab == "files":
                        if self.selected_idx > 0:
                            self.selected_idx -= 1
                    else:
                        if self.docker_selected_idx > 0:
                            self.docker_selected_idx -= 1
                elif key in ("DOWN", "j", "J"):
                    if self.active_tab == "files":
                        if self.selected_idx < len(self.filtered_files) - 1:
                            self.selected_idx += 1
                    else:
                        if self.docker_selected_idx < len(self.docker_images) - 1:
                            self.docker_selected_idx += 1
                elif key in ("PAGE_UP", "LEFT"):
                    if self.active_tab == "files":
                        self.selected_idx = max(0, self.selected_idx - 15)
                    else:
                        self.docker_selected_idx = max(0, self.docker_selected_idx - 15)
                elif key in ("PAGE_DOWN", "RIGHT"):
                    if self.active_tab == "files":
                        self.selected_idx = min(len(self.filtered_files) - 1, self.selected_idx + 15)
                    else:
                        self.docker_selected_idx = min(len(self.docker_images) - 1, self.docker_selected_idx + 15)
                elif key in ("d", "D", "DELETE"):
                    if self.active_tab == "files":
                        self.delete_selected_file()
                    else:
                        self.delete_selected_docker_image()
                elif key in ("p", "P"):
                    if self.active_tab == "docker":
                        self.prune_docker_images()
                elif key in ("o", "O", "ENTER"):
                    if self.active_tab == "files":
                        self.show_details()
                elif key == "/":
                    if self.active_tab == "files":
                        self.prompt_filter()
                elif key in ("s", "S"):
                    if self.active_tab == "files":
                        self.toggle_sort()
                elif key in ("r", "R"):
                    self.status_msg = "[REFRESHING] Scanning files and Docker..."
                    self.status_color = C_YELLOW
                    self.draw()
                    self.load_files()
                    self.load_docker()
                    self.status_msg = "[REFRESHED] Refresh complete."
                    self.status_color = C_GREEN
        except Exception as e:
            import traceback
            sys.stdout.write("\033[?25h\033[0m\n")
            sys.stdout.flush()
            print(f"\n[ERROR] An unexpected error occurred: {e}")
            traceback.print_exc()
            try:
                input("\nPress [Enter] to exit...")
            except Exception:
                pass
        finally:
            sys.stdout.write("\033[?25h\033[2J\033[H")
            sys.stdout.flush()


def launch_tui(target_path: Optional[str] = None, min_size_mb: float = 100.0) -> None:
    if not target_path or target_path == ".":
        target_path = get_default_scan_path()
    tui = DiskManagerTUI(target_path=target_path, min_size_mb=min_size_mb)
    tui.run()


def progress_display(scanned_files: int, found_large: int, current_path: str) -> None:
    max_path_len = 45
    short_path = ("..." + current_path[-(max_path_len - 3):]) if len(current_path) > max_path_len else current_path.ljust(max_path_len)
    msg = f"\r[Scanning...] Files: {scanned_files:,} | Large Found: {found_large} | {short_path}"
    sys.stdout.write(msg[:105].ljust(105))
    sys.stdout.flush()


def run_scan(target_path: str, min_size_mb: float = 100.0, csv_output: str = None, json_output: str = None, limit: int = 50, follow_symlinks: bool = False) -> None:
    abs_path = os.path.abspath(target_path)
    if not os.path.exists(abs_path):
        print(f"\n[ERROR] Path does not exist: {abs_path}", file=sys.stderr)
        return

    print("\n" + "=" * 75)
    print("                      STARTING DISK SCAN")
    print("=" * 75)
    print(f"Target Directory : {abs_path}")
    print(f"Size Threshold   : >= {min_size_mb:.2f} MB")
    print(f"Follow Symlinks  : {'Yes' if follow_symlinks else 'No'}")
    print("Please wait, scanning files...\n")

    scanner = DiskScanner(target_path=abs_path, min_size_mb=min_size_mb, follow_symlinks=follow_symlinks, progress_callback=progress_display)
    try:
        large_files = scanner.scan()
    except KeyboardInterrupt:
        print("\n\n[CANCELLED] Scan was interrupted by user.")
        return

    sys.stdout.write("\r" + " " * 105 + "\r")
    sys.stdout.flush()

    Reporter.print_summary(scanner.stats, abs_path, min_size_mb)
    Reporter.print_table(large_files, max_rows=limit)

    if csv_output:
        saved_csv = Reporter.export_to_csv(large_files, csv_output)
        print(f"\n[EXPORT] CSV report successfully saved to:\n -> {saved_csv}")

    if json_output:
        saved_json = Reporter.export_to_json(large_files, scanner.stats, json_output)
        print(f"\n[EXPORT] JSON report successfully saved to:\n -> {saved_json}")


def prompt_guided_scan() -> None:
    print("\n" + "-" * 75)
    print("                GUIDED SCAN CONFIGURATION")
    print("-" * 75)

    drives = get_available_drives()
    default_path = get_default_scan_path()

    print("\n[Step 1/5] Select Target Location:")
    if drives:
        for idx, d in enumerate(drives, start=1):
            free_str = format_size(d["free"])
            total_str = format_size(d["total"])
            print(f"  [{idx}] {d['path']} (Free: {free_str} / Total: {total_str})")
        print("  [C] Custom path or directory")

    choice = input(f"\nEnter drive number or custom path [Default: {default_path}]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(drives):
        target_path = drives[int(choice) - 1]["path"]
    elif choice.upper() == "C":
        custom_p = input("Enter custom directory path: ").strip()
        target_path = custom_p if custom_p else default_path
    elif choice:
        target_path = choice
    else:
        target_path = default_path

    if not os.path.exists(target_path):
        print(f"[ERROR] Path does not exist: {target_path}")
        return

    print("\n[Step 2/5] File Size Threshold:")
    size_input = input("Enter minimum file size in MB [Default: 100]: ").strip()
    try:
        min_size = float(size_input) if size_input else 100.0
        if min_size <= 0:
            min_size = 100.0
    except ValueError:
        print("[WARN] Invalid input, defaulting to 100 MB.")
        min_size = 100.0

    print("\n[Step 3/5] Report Export Options:")
    print("  [1] Console table only")
    print("  [2] Export to CSV file (Spreadsheet / Excel)")
    print("  [3] Export to JSON file")
    print("  [4] Both CSV and JSON files")
    export_choice = input("Select export option [Default: 2 - CSV]: ").strip() or "2"

    csv_file = None
    json_file = None
    if export_choice in ("2", "4"):
        csv_name = input("Enter CSV file name [Default: large_files_report.csv]: ").strip()
        csv_file = csv_name if csv_name else "large_files_report.csv"
    if export_choice in ("3", "4"):
        json_name = input("Enter JSON file name [Default: large_files_report.json]: ").strip()
        json_file = json_name if json_name else "large_files_report.json"

    print("\n[Step 4/5] Console Display Limit:")
    limit_input = input("Enter max rows to display on screen [Default: 50]: ").strip()
    try:
        limit = int(limit_input) if limit_input else 50
    except ValueError:
        limit = 50

    print("\n[Step 5/5] Advanced:")
    symlink_input = input("Follow symbolic links? (y/N) [Default: N]: ").strip().lower()
    follow_symlinks = symlink_input in ("y", "yes")

    run_scan(target_path=target_path, min_size_mb=min_size, csv_output=csv_file, json_output=json_file, limit=limit, follow_symlinks=follow_symlinks)


def prompt_tui_mode() -> None:
    print("\n" + "-" * 75)
    print("          LAUNCH BASHTOP-STYLE TUI DASHBOARD")
    print("-" * 75)
    drives = get_available_drives()
    default_path = get_default_scan_path()

    if drives:
        print("Available Storage Drives:")
        for idx, d in enumerate(drives, start=1):
            print(f"  [{idx}] {d['path']} (Free: {format_size(d['free'])} / Total: {format_size(d['total'])})")
        print("  [C] Custom directory\n")

    choice = input(f"Select drive or enter path to inspect [Default: {default_path}]: ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(drives):
        target_path = drives[int(choice) - 1]["path"]
    elif choice.upper() == "C":
        custom_p = input("Enter custom directory path: ").strip()
        target_path = custom_p if custom_p else default_path
    elif choice:
        target_path = choice
    else:
        target_path = default_path

    size_input = input("Minimum file size in MB to display [Default: 100]: ").strip()
    try:
        min_size = float(size_input) if size_input else 100.0
    except ValueError:
        min_size = 100.0

    launch_tui(target_path=target_path, min_size_mb=min_size)


def quick_scan_default() -> None:
    target_path = get_default_scan_path()
    print(f"\n[QUICK SCAN] Scanning {target_path} for files >= 100 MB...")
    run_scan(target_path=target_path, min_size_mb=100.0, csv_output="large_files_report.csv", limit=50, follow_symlinks=False)


def interactive_menu() -> None:
    while True:
        print("\n" + "=" * 75)
        print("                 SERVER DISK MANAGER - MAIN MENU")
        print("=" * 75)
        print("  [1] Bashtop-Style TUI Dashboard (Live Navigation & File Deletion) ⭐")
        print("  [2] Guided Scan (Configure drive, threshold & export to CSV/JSON)")
        print("  [3] Quick Scan Primary Drive (>= 100 MB -> Export to CSV)")
        print("  [4] View Server Storage Drives & Free Space")
        print("  [5] Scan Current Directory (.)")
        print("  [0] Exit")
        print("=" * 75)

        choice = input("Please select an option [0-5]: ").strip()
        if choice == "1":
            prompt_tui_mode()
        elif choice == "2":
            prompt_guided_scan()
        elif choice == "3":
            quick_scan_default()
        elif choice == "4":
            drives = get_available_drives()
            Reporter.print_drives(drives)
        elif choice == "5":
            run_scan(target_path=".", min_size_mb=100.0, csv_output="current_dir_large_files.csv", limit=50)
        elif choice in ("0", "exit", "quit", "q"):
            print("\nExiting Server Disk Manager. Goodbye!\n")
            break
        else:
            print("\n[WARN] Invalid choice. Please enter a number between 0 and 5.")

        input("\nPress [Enter] to return to the menu...")


def main():
    parser = argparse.ArgumentParser(
        description="Server Disk Manager: Scan hard drives for large files and clean unused Docker images."
    )
    parser.add_argument("-p", "--path", type=str, help="Target directory or drive to scan (e.g. C:\\ or /var/log)")
    parser.add_argument("-s", "--min-size", type=float, default=100.0, help="Minimum file size in megabytes (MB) to report (default: 100)")
    parser.add_argument("-c", "--csv", type=str, help="Path to export CSV report (e.g. report.csv)")
    parser.add_argument("-j", "--json", type=str, help="Path to export JSON report (e.g. report.json)")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Maximum number of rows to display in terminal table (default: 50)")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow symbolic links during scan (default: False)")
    parser.add_argument("-d", "--drives", action="store_true", help="Display list of server storage drives and usage without scanning")
    parser.add_argument("-t", "--tui", action="store_true", help="Launch interactive Bashtop-style TUI dashboard directly (Default)")
    parser.add_argument("-m", "--menu", action="store_true", help="Launch the text-based interactive menu instead of TUI")

    args = parser.parse_args()

    if args.drives:
        drives = get_available_drives()
        Reporter.print_drives(drives)
        sys.exit(0)

    if args.menu:
        interactive_menu()
        sys.exit(0)

    headless_export = any([args.csv, args.json, "--limit" in sys.argv, "-l" in sys.argv])
    default_target = get_default_scan_path()
    if headless_export:
        target = args.path if args.path else default_target
        run_scan(target_path=target, min_size_mb=args.min_size, csv_output=args.csv, json_output=args.json, limit=args.limit, follow_symlinks=args.follow_symlinks)
    else:
        # DEFAULT: Launch TUI directly!
        target = args.path if args.path else default_target
        launch_tui(target_path=target, min_size_mb=args.min_size)


if __name__ == "__main__":
    main()
