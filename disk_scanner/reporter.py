import csv
import json
import os
from typing import List

from .scanner import FileInfo, ScanStats
from .utils import format_size


class Reporter:
    """
    Handles formatting and exporting scan results to Console, CSV, and JSON.
    """

    @staticmethod
    def print_summary(stats: ScanStats, target_path: str, min_size_mb: float) -> None:
        """
        Prints a summary of the scan results to stdout.
        """
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
        """
        Prints status of available server storage drives.
        """
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
        """
        Prints top large files in a formatted console table.
        """
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
        """
        Exports large files list to a CSV file.
        """
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
        """
        Exports large files and scan stats to a JSON file.
        """
        abs_path = os.path.abspath(file_path)
        data = {
            "statistics": {
                "target_path": getattr(stats, "target_path", ""),
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
