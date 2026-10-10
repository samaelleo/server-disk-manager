"""
Interactive TUI Dashboard (Bashtop / Btop style) for Server Disk Manager.
Allows real-time inspection, sorting, filtering, and deletion of heavy files.
Zero external dependencies.
"""

import os
import shutil
import sys
import time
from typing import List, Optional

from .scanner import DiskScanner, FileInfo
from .utils import format_size, format_timestamp, get_available_drives

# ANSI Color and Styling constants
C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_INVERT = "\033[7m"

C_CYAN = "\033[36m"
C_BLUE = "\033[34m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"
C_WHITE = "\033[37m"

BG_CYAN = "\033[46m\033[30m"
BG_BLUE = "\033[44m\033[37m"
BG_RED = "\033[41m\033[37m"


def get_key() -> str:
    """
    Cross-platform single keypress reader.
    Returns strings like 'UP', 'DOWN', 'PAGE_UP', 'PAGE_DOWN', 'DELETE', 'ENTER', 'ESC', 'q', 'd', etc.
    """
    if os.name == "nt":
        import msvcrt
        ch = msvcrt.getch()
        if ch in (b"\x00", b"\xe0"):
            ch2 = msvcrt.getch()
            mapping = {
                b"H": "UP",
                b"P": "DOWN",
                b"K": "LEFT",
                b"M": "RIGHT",
                b"S": "DELETE",
                b"I": "PAGE_UP",
                b"Q": "PAGE_DOWN",
            }
            return mapping.get(ch2, "SPECIAL")
        if ch == b"\r":
            return "ENTER"
        if ch == b"\x1b":
            return "ESC"
        if ch == b"\x08":
            return "BACKSPACE"
        try:
            return ch.decode("utf-8", errors="ignore")
        except Exception:
            return ""
    else:
        import termios
        import tty
        import select

        fd = sys.stdin.fileno()
        old_settings = termios.tcgetattr(fd)
        try:
            tty.setraw(fd)
            ch = sys.stdin.read(1)
            if ch == "\x1b":
                r, _, _ = select.select([sys.stdin], [], [], 0.05)
                if r:
                    ch2 = sys.stdin.read(1)
                    if ch2 == "[":
                        ch3 = sys.stdin.read(1)
                        mapping = {
                            "A": "UP",
                            "B": "DOWN",
                            "C": "RIGHT",
                            "D": "LEFT",
                        }
                        if ch3 in mapping:
                            return mapping[ch3]
                        if ch3 == "3":
                            sys.stdin.read(1)  # ~
                            return "DELETE"
                        if ch3 == "5":
                            sys.stdin.read(1)
                            return "PAGE_UP"
                        if ch3 == "6":
                            sys.stdin.read(1)
                            return "PAGE_DOWN"
                return "ESC"
            if ch in ("\r", "\n"):
                return "ENTER"
            if ch in ("\x7f", "\x08"):
                return "BACKSPACE"
            return ch
        finally:
            termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def make_gauge_bar(used_bytes: int, total_bytes: int, length: int = 24) -> str:
    """
    Builds a visual colored usage gauge bar like bashtop.
    """
    if total_bytes <= 0:
        return "[ " + "░" * length + " ]"
    pct = min(1.0, max(0.0, used_bytes / total_bytes))
    fill_len = int(pct * length)
    empty_len = length - fill_len

    color = C_GREEN
    if pct >= 0.90:
        color = C_RED
    elif pct >= 0.70:
        color = C_YELLOW

    bar = f"[{color}{'█' * fill_len}{C_RESET}{C_DIM}{'░' * empty_len}{C_RESET}] {color}{pct * 100:.1f}%{C_RESET}"
    return bar


class DiskManagerTUI:
    """
    Bashtop-inspired Terminal User Interface for managing heavy files.
    """

    def __init__(self, target_path: str, min_size_mb: float = 100.0):
        self.target_path = os.path.abspath(target_path)
        self.min_size_mb = min_size_mb
        self.files: List[FileInfo] = []
        self.filtered_files: List[FileInfo] = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.status_msg = ""
        self.status_color = C_GREEN
        self.filter_query = ""
        self.sort_mode = "size_desc"  # size_desc, size_asc, name, date
        self.total_freed_bytes = 0

    def load_files(self) -> None:
        """Runs the scan to collect large files."""
        scanner = DiskScanner(target_path=self.target_path, min_size_mb=self.min_size_mb)
        self.files = scanner.scan()
        self.apply_filter_and_sort()
        self.selected_idx = 0
        self.scroll_offset = 0

    def apply_filter_and_sort(self) -> None:
        """Filters and sorts the loaded files list."""
        if self.filter_query:
            q = self.filter_query.lower()
            self.filtered_files = [
                f for f in self.files if q in f.path.lower() or q in f.extension.lower()
            ]
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

        # Bounds check
        if self.selected_idx >= len(self.filtered_files):
            self.selected_idx = max(0, len(self.filtered_files) - 1)

    def draw(self) -> None:
        """Renders the full TUI screen."""
        term_cols, term_lines = shutil.get_terminal_size((100, 30))
        lines = []

        # Header Box
        w = max(70, min(term_cols, 130))
        header_title = " 🗄️  SERVER DISK MANAGER - INTERACTIVE TUI (BASHTOP MODE) "
        lines.append(f"{C_CYAN}┌" + "─" * (w - 2) + f"┐{C_RESET}")
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{header_title.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Drive Storage Info Bar
        drives = get_available_drives()
        if drives:
            d = drives[0]
            for candidate in drives:
                if self.target_path.startswith(candidate["path"]):
                    d = candidate
                    break
            gauge = make_gauge_bar(d["used"], d["total"], length=max(15, w // 5))
            storage_text = (
                f" Storage [{d['path']}] {gauge} "
                f"| Used: {format_size(d['used'])} | Free: {C_GREEN}{format_size(d['free'])}{C_RESET} | Total: {format_size(d['total'])}"
            )
            lines.append(f"{C_CYAN}│{C_RESET} {storage_text.ljust(w - 4)[:w - 4]} {C_CYAN}│{C_RESET}")
            lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Scan Meta Info
        total_size_bytes = sum(f.size_bytes for f in self.filtered_files)
        sort_names = {
            "size_desc": "Size (Largest First)",
            "size_asc": "Size (Smallest First)",
            "name": "File Name (A-Z)",
            "date": "Modified Date (Newest)",
        }
        meta_left = f" Path: {self.target_path} (Threshold: >= {self.min_size_mb:.0f} MB)"
        meta_right = f"Files: {len(self.filtered_files):,} | Total: {format_size(total_size_bytes)} | Sort: {sort_names.get(self.sort_mode)} "
        spacing = max(1, w - len(meta_left) - len(meta_right) - 2)
        meta_line = meta_left + " " * spacing + meta_right
        lines.append(f"{C_CYAN}│{C_RESET}{C_DIM}{meta_line[:w - 2].ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        if self.filter_query:
            filter_text = f" Filter Active: '{self.filter_query}' (Press '/' to change, ESC to clear)"
            lines.append(f"{C_CYAN}│{C_RESET}{C_YELLOW}{filter_text.ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Table Header
        h_idx = "#"
        h_size = "SIZE"
        h_ext = "EXT"
        h_date = "MODIFIED"
        h_path = "FILE PATH"
        table_hdr = f"  {h_idx:<4} | {h_size:<11} | {h_ext:<6} | {h_date:<19} | {h_path}"
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{table_hdr.ljust(w - 2)[:w - 2]}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Calculate Available Table Rows
        footer_height = 5
        header_height = len(lines)
        table_height = max(5, term_lines - header_height - footer_height)

        # Adjust scroll offset
        if self.selected_idx < self.scroll_offset:
            self.scroll_offset = self.selected_idx
        elif self.selected_idx >= self.scroll_offset + table_height:
            self.scroll_offset = self.selected_idx - table_height + 1

        # Table Rows
        visible_files = self.filtered_files[self.scroll_offset : self.scroll_offset + table_height]

        if not self.filtered_files:
            empty_msg = "[ No files match current criteria or directory is empty ]"
            lines.append(f"{C_CYAN}│{C_RESET}{empty_msg.center(w - 2)}{C_CYAN}│{C_RESET}")
            for _ in range(table_height - 1):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")
        else:
            for i, f in enumerate(visible_files):
                actual_idx = self.scroll_offset + i
                is_selected = actual_idx == self.selected_idx

                num_str = f"{actual_idx + 1}"
                size_str = f.size_formatted
                ext_str = f.extension
                date_str = f.modified_time
                max_path_w = max(20, w - 52)
                path_str = f.path
                if len(path_str) > max_path_w:
                    path_str = "..." + path_str[-(max_path_w - 3) :]

                row_content = f"  {num_str:<4} | {size_str:<11} | {ext_str:<6} | {date_str:<19} | {path_str}"
                row_padded = row_content.ljust(w - 2)[: w - 2]

                if is_selected:
                    prefix = f"{C_CYAN}│{C_RESET}{BG_CYAN}{C_BOLD}"
                    suffix = f"{C_RESET}{C_CYAN}│{C_RESET}"
                    lines.append(f"{prefix}{row_padded}{suffix}")
                else:
                    lines.append(f"{C_CYAN}│{C_RESET}{row_padded}{C_CYAN}│{C_RESET}")

            # Fill remaining rows if any
            for _ in range(table_height - len(visible_files)):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")

        # Table Bottom Border
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Status Notification Line
        status_line = self.status_msg if self.status_msg else "Ready. Use arrows to browse, 'd' to delete selected file."
        if self.total_freed_bytes > 0:
            freed_str = f"[Total Space Freed: {format_size(self.total_freed_bytes)}] "
            status_line = freed_str + status_line
        lines.append(f"{C_CYAN}│{C_RESET} {self.status_color}{status_line.ljust(w - 4)[:w - 4]}{C_RESET} {C_CYAN}│{C_RESET}")

        # Controls & Hotkeys Footer
        hotkeys = " [↑/↓] Move  [d/DEL] Delete  [o] Details  [/] Search  [s] Sort  [r] Rescan  [q] Quit "
        lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}└" + "─" * (w - 2) + f"┘{C_RESET}")

        # Render buffer to terminal
        sys.stdout.write("\033[H" + "\n".join(lines) + "\033[J")
        sys.stdout.flush()

    def show_details(self) -> None:
        """Displays full details of the selected file."""
        if not self.filtered_files:
            return
        f = self.filtered_files[self.selected_idx]
        term_cols, term_lines = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 90)

        sys.stdout.write("\033[2J\033[H")
        print("\n" + "=" * w)
        print(f"{C_BOLD}                       FILE DETAILS{C_RESET}".center(w))
        print("=" * w)
        print(f"{C_CYAN}Path         :{C_RESET} {f.path}")
        print(f"{C_CYAN}Exact Bytes  :{C_RESET} {f.size_bytes:,} bytes")
        print(f"{C_CYAN}Formatted    :{C_RESET} {f.size_formatted}")
        print(f"{C_CYAN}Extension    :{C_RESET} {f.extension}")
        print(f"{C_CYAN}Last Modified:{C_RESET} {f.modified_time}")
        print(f"{C_CYAN}Readable     :{C_RESET} {'Yes' if os.access(f.path, os.R_OK) else 'No'}")
        print(f"{C_CYAN}Writable     :{C_RESET} {'Yes' if os.access(f.path, os.W_OK) else 'No'}")
        print("=" * w)
        print(f"\n{C_YELLOW}Press any key to return to dashboard...{C_RESET}")
        get_key()

    def delete_selected(self) -> None:
        """Prompts for confirmation and deletes the selected file."""
        if not self.filtered_files:
            return

        f = self.filtered_files[self.selected_idx]
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 95)

        # Clear screen and display danger box
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

        sys.stdout.write(f"Type '{C_BOLD}yes{C_RESET}' or press '{C_BOLD}y{C_RESET}' to confirm deletion (anything else cancels): ")
        sys.stdout.flush()

        ans = input().strip().lower()

        if ans in ("y", "yes"):
            try:
                os.remove(f.path)
                self.total_freed_bytes += f.size_bytes
                self.status_msg = f"[DELETED] Successfully deleted '{os.path.basename(f.path)}' (Freed: {f.size_formatted})"
                self.status_color = C_GREEN

                # Remove from lists
                self.files = [item for item in self.files if item.path != f.path]
                self.apply_filter_and_sort()
            except PermissionError:
                self.status_msg = f"[ERROR] Permission Denied: Cannot delete '{os.path.basename(f.path)}'. Run as Administrator/root."
                self.status_color = C_RED
            except FileNotFoundError:
                self.status_msg = f"[WARN] File was already removed by another process."
                self.status_color = C_YELLOW
                self.files = [item for item in self.files if item.path != f.path]
                self.apply_filter_and_sort()
            except Exception as e:
                self.status_msg = f"[ERROR] Could not delete file: {str(e)}"
                self.status_color = C_RED
        else:
            self.status_msg = "[CANCELLED] Deletion cancelled by user."
            self.status_color = C_YELLOW

    def prompt_filter(self) -> None:
        """Prompts for a filter query."""
        sys.stdout.write("\033[H\033[2J")
        print("\n" + "=" * 60)
        print("                   FILTER FILES")
        print("=" * 60)
        print("Enter keyword or extension to filter (e.g. '.iso', 'backup', 'log'):")
        print("Leave empty to clear filter.")
        print("-" * 60)
        sys.stdout.write("Search query: ")
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
        """Cycles through sort modes."""
        modes = ["size_desc", "size_asc", "name", "date"]
        curr_idx = modes.index(self.sort_mode)
        self.sort_mode = modes[(curr_idx + 1) % len(modes)]
        self.apply_filter_and_sort()
        self.status_msg = f"Sort mode changed to: {self.sort_mode}"
        self.status_color = C_CYAN

    def run(self) -> None:
        """Main TUI event loop."""
        # Hide cursor & clear screen
        sys.stdout.write("\033[?25l\033[2J")
        sys.stdout.flush()

        try:
            print(f"\n[SCANNING] Initializing scan for {self.target_path} (>= {self.min_size_mb:.0f} MB)...")
            self.load_files()

            while True:
                self.draw()
                key = get_key()

                if key in ("q", "Q", "ESC"):
                    break
                elif key == "UP":
                    if self.selected_idx > 0:
                        self.selected_idx -= 1
                elif key == "DOWN":
                    if self.selected_idx < len(self.filtered_files) - 1:
                        self.selected_idx += 1
                elif key == "PAGE_UP":
                    self.selected_idx = max(0, self.selected_idx - 15)
                elif key == "PAGE_DOWN":
                    self.selected_idx = min(len(self.filtered_files) - 1, self.selected_idx + 15)
                elif key in ("d", "D", "DELETE"):
                    self.delete_selected()
                elif key in ("o", "O", "ENTER"):
                    self.show_details()
                elif key == "/":
                    self.prompt_filter()
                elif key in ("s", "S"):
                    self.toggle_sort()
                elif key in ("r", "R"):
                    self.status_msg = "[RESCANNING] Refreshing file list..."
                    self.status_color = C_YELLOW
                    self.draw()
                    self.load_files()
                    self.status_msg = "[REFRESHED] Scan complete."
                    self.status_color = C_GREEN
        finally:
            # Show cursor & clear screen on exit
            sys.stdout.write("\033[?25h\033[2J\033[H")
            sys.stdout.flush()


def launch_tui(target_path: str = ".", min_size_mb: float = 100.0) -> None:
    """Helper entry point to start the TUI."""
    tui = DiskManagerTUI(target_path=target_path, min_size_mb=min_size_mb)
    tui.run()
