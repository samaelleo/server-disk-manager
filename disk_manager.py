#!/usr/bin/env python3
"""
Server Disk Manager - Standalone Single-File Version
Zero external dependencies. Ideal for one-line curl/wget temporary execution on servers.
"""

import argparse
import csv
import json
import os
import shutil
import string
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Callable, List, Optional

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


def progress_display(scanned_files: int, found_large: int, current_path: str) -> None:
    max_path_len = 45
    if len(current_path) > max_path_len:
        short_path = "..." + current_path[-(max_path_len - 3):]
    else:
        short_path = current_path.ljust(max_path_len)

    msg = f"\r[Scanning...] Files: {scanned_files:,} | Large Found: {found_large} | {short_path}"
    sys.stdout.write(msg[:105].ljust(105))
    sys.stdout.flush()


def run_scan(
    target_path: str,
    min_size_mb: float = 100.0,
    csv_output: str = None,
    json_output: str = None,
    limit: int = 50,
    follow_symlinks: bool = False,
) -> None:
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

    scanner = DiskScanner(
        target_path=abs_path,
        min_size_mb=min_size_mb,
        follow_symlinks=follow_symlinks,
        progress_callback=progress_display,
    )

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
    default_path = drives[0]["path"] if drives else ("C:\\" if os.name == "nt" else "/")

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

    run_scan(
        target_path=target_path,
        min_size_mb=min_size,
        csv_output=csv_file,
        json_output=json_file,
        limit=limit,
        follow_symlinks=follow_symlinks,
    )


def quick_scan_default() -> None:
    drives = get_available_drives()
    target_path = drives[0]["path"] if drives else ("C:\\" if os.name == "nt" else "/")
    print(f"\n[QUICK SCAN] Scanning {target_path} for files >= 100 MB...")
    run_scan(
        target_path=target_path,
        min_size_mb=100.0,
        csv_output="large_files_report.csv",
        limit=50,
        follow_symlinks=False,
    )


def interactive_menu() -> None:
    while True:
        print("\n" + "=" * 75)
        print("                 SERVER DISK MANAGER - MAIN MENU")
        print("=" * 75)
        print("  [1] Guided Scan (Configure drive, threshold & export options)")
        print("  [2] Quick Scan Primary Drive (>= 100 MB -> Export to CSV)")
        print("  [3] View Server Storage Drives & Free Space")
        print("  [4] Scan Current Directory (.)")
        print("  [0] Exit")
        print("=" * 75)

        choice = input("Please select an option [0-4]: ").strip()

        if choice == "1":
            prompt_guided_scan()
        elif choice == "2":
            quick_scan_default()
        elif choice == "3":
            drives = get_available_drives()
            Reporter.print_drives(drives)
        elif choice == "4":
            run_scan(
                target_path=".",
                min_size_mb=100.0,
                csv_output="current_dir_large_files.csv",
                limit=50,
            )
        elif choice in ("0", "exit", "quit", "q"):
            print("\nExiting Server Disk Manager. Goodbye!\n")
            break
        else:
            print("\n[WARN] Invalid choice. Please enter a number between 0 and 4.")

        input("\nPress [Enter] to return to the menu...")


def main():
    parser = argparse.ArgumentParser(
        description="Server Disk Manager: Scan hard drives for large files (>= 100 MB by default) and generate reports."
    )
    parser.add_argument("-p", "--path", type=str, help="Target directory or drive to scan (e.g. C:\\ or /var/log)")
    parser.add_argument("-s", "--min-size", type=float, default=100.0, help="Minimum file size in megabytes (MB) to report (default: 100)")
    parser.add_argument("-c", "--csv", type=str, help="Path to export CSV report (e.g. report.csv)")
    parser.add_argument("-j", "--json", type=str, help="Path to export JSON report (e.g. report.json)")
    parser.add_argument("-l", "--limit", type=int, default=50, help="Maximum number of rows to display in terminal table (default: 50)")
    parser.add_argument("--follow-symlinks", action="store_true", help="Follow symbolic links during scan (default: False)")
    parser.add_argument("-d", "--drives", action="store_true", help="Display list of server storage drives and usage without scanning")
    parser.add_argument("-m", "--menu", action="store_true", help="Force launch the interactive menu")

    args = parser.parse_args()

    if args.drives:
        drives = get_available_drives()
        Reporter.print_drives(drives)
        sys.exit(0)

    cli_flags_used = any([args.path, args.csv, args.json, "--min-size" in sys.argv, "-s" in sys.argv])

    if cli_flags_used and not args.menu:
        target = args.path if args.path else "."
        run_scan(
            target_path=target,
            min_size_mb=args.min_size,
            csv_output=args.csv,
            json_output=args.json,
            limit=args.limit,
            follow_symlinks=args.follow_symlinks,
        )
    else:
        interactive_menu()


if __name__ == "__main__":
    main()
