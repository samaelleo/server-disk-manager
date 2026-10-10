"""
Interactive TUI Dashboard (Bashtop / Btop style) for Server Disk Manager.
Allows real-time inspection, sorting, filtering, and deletion of heavy files,
as well as inspecting and cleaning unused Docker images.
Zero external dependencies.
"""

import os
import shutil
import sys
import time
from typing import List, Optional

from .scanner import DiskScanner, FileInfo
from .utils import format_size, format_timestamp, get_available_drives, get_default_scan_path
from .docker_manager import DockerManager, DockerImage

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


if sys.platform == "win32":
    try:
        if hasattr(sys.stdout, "reconfigure"):
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        if hasattr(sys.stdin, "reconfigure"):
            sys.stdin.reconfigure(encoding="utf-8", errors="replace")
    except Exception:
        pass

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
    Bashtop-inspired Terminal User Interface for managing heavy files and Docker images.
    """

    def __init__(self, target_path: Optional[str] = None, min_size_mb: float = 100.0):
        if not target_path or target_path == ".":
            target_path = get_default_scan_path()
        self.target_path = os.path.abspath(target_path)
        self.min_size_mb = min_size_mb
        self.active_tab = "files"  # "files" or "docker"

        # Files state
        self.files: List[FileInfo] = []
        self.filtered_files: List[FileInfo] = []
        self.selected_idx = 0
        self.scroll_offset = 0
        self.filter_query = ""
        self.sort_mode = "size_desc"  # size_desc, size_asc, name, date
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
        """Runs the scan to collect large files."""
        scanner = DiskScanner(target_path=self.target_path, min_size_mb=self.min_size_mb)
        self.files = scanner.scan()
        self.apply_filter_and_sort()
        self.selected_idx = 0
        self.scroll_offset = 0

    def load_docker(self) -> None:
        """Loads Docker images list."""
        imgs, err = DockerManager.list_images()
        self.docker_images = imgs
        self.docker_error = err
        self.docker_selected_idx = 0
        self.docker_scroll_offset = 0

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

        if self.selected_idx >= len(self.filtered_files):
            self.selected_idx = max(0, len(self.filtered_files) - 1)

    def draw(self) -> None:
        """Renders the full TUI screen with tabs."""
        term_cols, term_lines = shutil.get_terminal_size((100, 30))
        lines = []
        w = max(75, min(term_cols, 130))

        # 1. Main Header Box
        header_title = " 🗄️  SERVER DISK MANAGER - BASHTOP DASHBOARD  "
        lines.append(f"{C_CYAN}┌" + "─" * (w - 2) + f"┐{C_RESET}")
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{header_title.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # 2. Interactive Tab Navigation Bar
        tab1_style = f"{BG_CYAN}{C_BOLD} [1] 📁 Large Files Disk Scan {C_RESET}" if self.active_tab == "files" else f"{C_DIM} [1] 📁 Large Files Disk Scan {C_RESET}"
        tab2_style = f"{BG_CYAN}{C_BOLD} [2] 🐳 Docker Images & Storage {C_RESET}" if self.active_tab == "docker" else f"{C_DIM} [2] 🐳 Docker Images & Storage {C_RESET}"
        tab_hint = f"{C_YELLOW}(Press TAB or 1/2 to switch tabs){C_RESET}"

        tab_line = f" {tab1_style}   {tab2_style}    {tab_hint}"
        # Measure printable width without ANSI
        clean_tab_line = f"  [1] 📁 Large Files Disk Scan     [2] 🐳 Docker Images & Storage     (Press TAB or 1/2 to switch tabs)"
        spacing = max(1, w - len(clean_tab_line) - 2)
        lines.append(f"{C_CYAN}│{C_RESET}{tab_line}{' ' * spacing}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Render Active Tab Content
        if self.active_tab == "files":
            self._draw_files_tab(lines, w, term_lines)
        else:
            self._draw_docker_tab(lines, w, term_lines)

        # Bottom Border
        lines.append(f"{C_CYAN}└" + "─" * (w - 2) + f"┘{C_RESET}")

        # Write buffer safely (handles Windows terminal encoding without crashing)
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
        """Renders the Large Files tab."""
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
            "size_desc": "Size (Largest)",
            "size_asc": "Size (Smallest)",
            "name": "Name (A-Z)",
            "date": "Date (Newest)",
        }
        meta_left = f" Path: {self.target_path} (>= {self.min_size_mb:.0f} MB)"
        meta_right = f"Files: {len(self.filtered_files):,} | Total: {format_size(total_size_bytes)} | Sort: {sort_names.get(self.sort_mode)} "
        spacing = max(1, w - len(meta_left) - len(meta_right) - 2)
        lines.append(f"{C_CYAN}│{C_RESET}{C_DIM}{(meta_left + ' ' * spacing + meta_right)[:w - 2].ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        if self.filter_query:
            filter_text = f" Filter Active: '{self.filter_query}' (Press '/' to change, ESC to clear)"
            lines.append(f"{C_CYAN}│{C_RESET}{C_YELLOW}{filter_text.ljust(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Table Header
        table_hdr = f"  {'#':<4} | {'SIZE':<11} | {'EXT':<6} | {'MODIFIED':<19} | FILE PATH"
        lines.append(f"{C_CYAN}│{C_BOLD}{C_WHITE}{table_hdr.ljust(w - 2)[:w - 2]}{C_RESET}{C_CYAN}│{C_RESET}")
        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")

        # Calculate Available Table Rows
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

        # Status Notification Line
        status_line = self.status_msg if self.status_msg else "Ready. Use arrows to browse, 'd' to delete selected file."
        if self.total_freed_bytes > 0:
            status_line = f"[Freed: {format_size(self.total_freed_bytes)}] " + status_line
        lines.append(f"{C_CYAN}│{C_RESET} {self.status_color}{status_line.ljust(w - 4)[:w - 4]}{C_RESET} {C_CYAN}│{C_RESET}")

        # Controls & Hotkeys Footer
        hotkeys = " [TAB] Docker  [↑/↓ or k/j] Move  [d/DEL] Delete File  [o] Details  [/] Search  [s] Sort  [r] Rescan  [q] Quit "
        lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

    def _draw_docker_tab(self, lines: List[str], w: int, term_lines: int) -> None:
        """Renders the Docker Images tab."""
        if self.docker_error:
            # Docker not running or error
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

        # Docker Table Header
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
                    # Colorized status version
                    row_color = f"  {actual_idx + 1:<4} | {status_lbl:<19} | {full_repo:<35} | {img.image_id[:12]:<14} | {img.size_str:<10} | {img.created}"
                    lines.append(f"{C_CYAN}│{C_RESET}{row_color.ljust(w + 7)[:w + 7]}{C_CYAN}│{C_RESET}")

            for _ in range(table_height - len(visible_imgs)):
                lines.append(f"{C_CYAN}│{C_RESET}" + " " * (w - 2) + f"{C_CYAN}│{C_RESET}")

        lines.append(f"{C_CYAN}├" + "─" * (w - 2) + f"┤{C_RESET}")
        status_line = self.status_msg if self.status_msg else "Use 'd' to delete selected image, 'p' to prune all unused images."
        lines.append(f"{C_CYAN}│{C_RESET} {self.status_color}{status_line.ljust(w - 4)[:w - 4]}{C_RESET} {C_CYAN}│{C_RESET}")

        hotkeys = " [TAB] Files  [↑/↓ or k/j] Move  [d/DEL] Remove Image  [p] Prune Unused  [r] Refresh  [q] Quit "
        lines.append(f"{C_CYAN}│{C_BOLD}{C_YELLOW}{hotkeys.center(w - 2)}{C_RESET}{C_CYAN}│{C_RESET}")

    def show_details(self) -> None:
        """Displays full details of the selected file."""
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
        print(f"{C_CYAN}Readable     :{C_RESET} {'Yes' if os.access(f.path, os.R_OK) else 'No'}")
        print(f"{C_CYAN}Writable     :{C_RESET} {'Yes' if os.access(f.path, os.W_OK) else 'No'}")
        print("=" * w)
        print(f"\n{C_YELLOW}Press any key to return...{C_RESET}")
        get_key()

    def delete_selected_file(self) -> None:
        """Prompts for confirmation and deletes the selected file."""
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
        """Prompts for confirmation and deletes the selected Docker image."""
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
        """Prompts for confirmation and prunes all unused Docker images."""
        term_cols, _ = shutil.get_terminal_size((80, 24))
        w = min(term_cols - 4, 95)

        sys.stdout.write("\033[2J\033[H")
        print("\n" + f"{C_YELLOW}╔" + "═" * (w - 2) + f"╗{C_RESET}")
        print(f"{C_YELLOW}║{C_BOLD}{C_WHITE}{'⚠️  PRUNE ALL UNUSED DOCKER IMAGES  ⚠️'.center(w - 2)}{C_RESET}{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}╠" + "═" * (w - 2) + f"╣{C_RESET}")
        print(f"{C_YELLOW}║{C_RESET} This command runs: {C_BOLD}docker image prune -a -f{C_RESET}".ljust(w + 8) + f"{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}║{C_RESET} It will delete ALL images not associated with a container.".ljust(w - 1) + f"{C_YELLOW}║{C_RESET}")
        print(f"{C_YELLOW}║{C_RESET} Active containers and their images will NOT be harmed.".ljust(w - 1) + f"{C_YELLOW}║{C_RESET}")
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
        """Prompts for a filter query."""
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
        """Cycles through sort modes."""
        modes = ["size_desc", "size_asc", "name", "date"]
        curr_idx = modes.index(self.sort_mode)
        self.sort_mode = modes[(curr_idx + 1) % len(modes)]
        self.apply_filter_and_sort()
        self.status_msg = f"Sort mode changed to: {self.sort_mode}"
        self.status_color = C_CYAN

    def run(self) -> None:
        """Main TUI event loop."""
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
                    # Toggle between tabs
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
    """Helper entry point to start the TUI."""
    if not target_path or target_path == ".":
        target_path = get_default_scan_path()
    tui = DiskManagerTUI(target_path=target_path, min_size_mb=min_size_mb)
    tui.run()
