#!/usr/bin/env python3
"""
Server Disk Manager - Large File Scanner
Scans disks and directories for files exceeding a specified threshold (>= 100MB by default).
Provides an interactive menu as well as full command-line argument support.
"""

import argparse
import os
import sys
import time

# Ensure UTF-8 output on Windows consoles
if sys.platform == "win32":
    try:
        if sys.stdout and hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if sys.stderr and hasattr(sys.stderr, "reconfigure"):
            sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

from disk_scanner.scanner import DiskScanner
from disk_scanner.reporter import Reporter
from disk_scanner.utils import get_available_drives, format_size
from disk_scanner.tui import launch_tui



def progress_display(scanned_files: int, found_large: int, current_path: str) -> None:
    """
    Renders an in-place progress update on stdout.
    """
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
    """
    Executes a scan with the given parameters and outputs the results.
    """
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

    # Clear progress line
    sys.stdout.write("\r" + " " * 105 + "\r")
    sys.stdout.flush()

    # Output Summary and Table
    Reporter.print_summary(scanner.stats, abs_path, min_size_mb)
    Reporter.print_table(large_files, max_rows=limit)

    # Export CSV if requested
    if csv_output:
        saved_csv = Reporter.export_to_csv(large_files, csv_output)
        print(f"\n[EXPORT] CSV report successfully saved to:\n -> {saved_csv}")

    # Export JSON if requested
    if json_output:
        saved_json = Reporter.export_to_json(large_files, scanner.stats, json_output)
        print(f"\n[EXPORT] JSON report successfully saved to:\n -> {saved_json}")


def prompt_guided_scan() -> None:
    """
    Interactively guides the user to configure all scan parameters.
    """
    print("\n" + "-" * 75)
    print("                GUIDED SCAN CONFIGURATION")
    print("-" * 75)

    # 1. Target Path Selection
    drives = get_available_drives()
    default_path = drives[0]["path"] if drives else ("C:\\" if os.name == "nt" else "/")

    print("\n[Step 1/5] Select Target Location:")
    if drives:
        for idx, d in enumerate(drives, start=1):
            free_str = format_size(d["free"])
            total_str = format_size(d["total"])
            print(f"  [{idx}] {d['path']} (Free: {free_str} / Total: {total_str})")
        print(f"  [C] Custom path or directory")

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

    # 2. File Size Threshold
    print("\n[Step 2/5] File Size Threshold:")
    size_input = input("Enter minimum file size in MB [Default: 100]: ").strip()
    try:
        min_size = float(size_input) if size_input else 100.0
        if min_size <= 0:
            min_size = 100.0
    except ValueError:
        print("[WARN] Invalid input, defaulting to 100 MB.")
        min_size = 100.0

    # 3. Export Format
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

    # 4. Display limit
    print("\n[Step 4/5] Console Display Limit:")
    limit_input = input("Enter max rows to display on screen [Default: 50]: ").strip()
    try:
        limit = int(limit_input) if limit_input else 50
    except ValueError:
        limit = 50

    # 5. Follow symlinks
    print("\n[Step 5/5] Advanced:")
    symlink_input = input("Follow symbolic links? (y/N) [Default: N]: ").strip().lower()
    follow_symlinks = symlink_input in ("y", "yes")

    # Execute Scan
    run_scan(
        target_path=target_path,
        min_size_mb=min_size,
        csv_output=csv_file,
        json_output=json_file,
        limit=limit,
        follow_symlinks=follow_symlinks,
    )


def quick_scan_default() -> None:
    """
    Performs an instant scan on the default system drive for files >= 100 MB.
    """
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


def prompt_tui_mode() -> None:
    """
    Selects drive or directory and launches the Bashtop-style TUI dashboard.
    """
    print("\n" + "-" * 75)
    print("          LAUNCH BASHTOP-STYLE TUI DASHBOARD")
    print("-" * 75)

    drives = get_available_drives()
    default_path = drives[0]["path"] if drives else ("C:\\" if os.name == "nt" else "/")

    if drives:
        print("Available Storage Drives:")
        for idx, d in enumerate(drives, start=1):
            free_str = format_size(d["free"])
            total_str = format_size(d["total"])
            print(f"  [{idx}] {d['path']} (Free: {free_str} / Total: {total_str})")
        print("  [C] Custom directory")
        print()

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


def interactive_menu() -> None:
    """
    Main interactive menu loop.
    """
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
            print("\n[WARN] Invalid choice. Please enter a number between 0 and 5.")

        input("\nPress [Enter] to return to the menu...")


def main():
    parser = argparse.ArgumentParser(
        description="Server Disk Manager: Scan hard drives for large files (>= 100 MB by default) and generate reports."
    )
    parser.add_argument(
        "-p", "--path",
        type=str,
        help="Target directory or drive to scan (e.g. C:\\ or /var/log)"
    )
    parser.add_argument(
        "-s", "--min-size",
        type=float,
        default=100.0,
        help="Minimum file size in megabytes (MB) to report (default: 100)"
    )
    parser.add_argument(
        "-c", "--csv",
        type=str,
        help="Path to export CSV report (e.g. report.csv)"
    )
    parser.add_argument(
        "-j", "--json",
        type=str,
        help="Path to export JSON report (e.g. report.json)"
    )
    parser.add_argument(
        "-l", "--limit",
        type=int,
        default=50,
        help="Maximum number of rows to display in terminal table (default: 50)"
    )
    parser.add_argument(
        "--follow-symlinks",
        action="store_true",
        help="Follow symbolic links during scan (default: False)"
    )
    parser.add_argument(
        "-d", "--drives",
        action="store_true",
        help="Display list of server storage drives and usage without scanning"
    )
    parser.add_argument(
        "-t", "--tui",
        action="store_true",
        help="Launch interactive Bashtop-style TUI dashboard with file deletion"
    )
    parser.add_argument(
        "-m", "--menu",
        action="store_true",
        help="Force launch the interactive menu"
    )

    args = parser.parse_args()

    # If --drives requested via CLI
    if args.drives:
        drives = get_available_drives()
        Reporter.print_drives(drives)
        sys.exit(0)

    # If --tui requested directly via CLI
    if args.tui:
        target = args.path if args.path else "."
        launch_tui(target_path=target, min_size_mb=args.min_size)
        sys.exit(0)

    # If specific CLI parameters are provided, execute directly
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
        # Launch Interactive Menu
        interactive_menu()



if __name__ == "__main__":
    main()
