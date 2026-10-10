# 🗄️ Server Disk Manager - Large File Scanner & TUI

A high-performance, modular, zero-dependency Python tool to inspect server storage disks, locate heavy files (>= 100 MB by default), display formatted summaries, export results to CSV and JSON formats, and manage files interactively via a **Bashtop-inspired TUI with real-time file deletion**.

All console output, reports, and table headers are in **English**, and the tool features a full **Interactive Menu**, a **Bashtop-style TUI Dashboard**, and **Command-Line (CLI)** capabilities.

---

## ⚡ Quick Start / Run Instructions (دستور اجرا)

### 🚀 One-Line Temporary Run with `curl` (اجرای موقت بدون نیاز به کلون):

Run directly on any server without cloning or leaving residue:

#### 🐧 Linux / macOS:
```bash
# Interactive menu with Bashtop TUI (Zero-trace, auto-deletes when done)
bash <(curl -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/run.sh)

# Or directly launch the Bashtop TUI with file deletion:
curl -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py | python3 - -t

# Or scan root / for >= 100MB and save report.csv:
curl -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py | python3 - -p / -s 100 -c /tmp/large_files.csv
```

#### 🪟 Windows (PowerShell):
```powershell
# Interactive menu (Temporary run, auto-cleans up)
curl.exe -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py -o $env:TEMP\dm.py; python $env:TEMP\dm.py; Remove-Item $env:TEMP\dm.py

# Or directly launch the Bashtop TUI with file deletion:
curl.exe -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py -o $env:TEMP\dm.py; python $env:TEMP\dm.py -t; Remove-Item $env:TEMP\dm.py
```

---

### 📦 Standard Clone & Run:
```bash
# Clone the repository
git clone https://github.com/samaelleo/server-disk-manager.git

# Navigate into project directory
cd server-disk-manager

# Run Interactive Menu
python main.py

# Or launch Bashtop-Style TUI directly
python main.py -t
```

> 💡 **Requirements**: Python 3.8+ (No external pip dependencies required - pure Python standard library).

---

## 🖥️ Bashtop-Style Interactive TUI Mode (`Option 1` or `-t`)

An interactive visual dashboard inspired by `bashtop`/`btop` for live disk navigation and disk space reclamation:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│          🗄️  SERVER DISK MANAGER - INTERACTIVE TUI (BASHTOP MODE)            │
├─────────────────────────────────────────────────────────────────────────────┤
│ Storage [C:\] [████████████████████░░░░] 84.2% | Used: 400 GB | Free: 75 GB│
├─────────────────────────────────────────────────────────────────────────────┤
│ Path: C:\ (Threshold: >= 100 MB)          Files: 42 | Total: 88.50 GB       │
├─────────────────────────────────────────────────────────────────────────────┤
│  #    | SIZE        | EXT    | MODIFIED            | FILE PATH              │
├─────────────────────────────────────────────────────────────────────────────┤
│  1    | 14.50 GB    | .iso   | 2026-08-14 12:30:10 | C:\backups\db.iso      │
│  2    | 4.20 GB     | .tar   | 2026-09-02 09:15:22 | C:\logs\archive.tar    │
│  3    | 2.10 GB     | .mp4   | 2026-09-18 18:40:00 | C:\media\video.mp4     │
├─────────────────────────────────────────────────────────────────────────────┤
│ Ready. Use arrows to browse, 'd' to delete selected file.                   │
│ [↑/↓] Move  [d/DEL] Delete  [o] Details  [/] Search  [s] Sort  [r] Rescan   │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 🎮 TUI Keybindings:
- **`↑` / `↓`**: Move selection cursor up / down.
- **`Page Up` / `Page Down`**: Scroll 15 files up / down.
- **`d` or `Delete`**: **Delete the selected file** (prompts with safety confirmation dialog `yes`/`y` and updates disk space immediately).
- **`o` or `ENTER`**: Open full file details (exact size in bytes, read/write permissions, timestamps).
- **`/`**: Search / Filter files in real-time by keyword or extension (e.g. `.iso`, `backup`). Press `ESC` to clear.
- **`s`**: Toggle sort modes (Largest first, Smallest first, Name A-Z, Modified date).
- **`r`**: Re-scan directory and refresh live file list.
- **`q` or `ESC`**: Exit TUI and return to main menu.

---

## 📁 Project Structure

```text
server-disk-manager/
│
├── disk_scanner/
│   ├── __init__.py
│   ├── scanner.py      # Core iterative directory scanner & stat collector
│   ├── reporter.py     # Console tables, CSV & JSON exporter (English)
│   ├── utils.py        # Storage calculations, drive detection & formatters
│   └── tui.py          # Bashtop-style interactive TUI with file deletion
│
├── tests/
│   └── test_scanner.py # Automated unit test suite
│
├── disk_manager.py     # Self-contained single-file script (for curl runs)
├── run.sh              # Zero-trace temporary runner for Linux/macOS
├── main.py             # Main entry point (Interactive Menu + CLI)
├── .gitignore
└── README.md
```

---

## 🎮 Main Menu Overview

When running `python main.py`, the interactive menu provides:

```text
===========================================================================
                 SERVER DISK MANAGER - MAIN MENU
===========================================================================
  [1] Bashtop-Style TUI Dashboard (Live Navigation & File Deletion) ⭐
  [2] Guided Scan (Configure drive, threshold & export to CSV/JSON)
  [3] Quick Scan Primary Drive (>= 100 MB -> Export to CSV)
  [4] View Server Storage Drives & Free Space
  [5] Scan Current Directory (.)
  [0] Exit
===========================================================================
```

---

## ⚙️ Command-Line Reference (CLI Flags)

| Flag | Long Option | Default | Description |
| :--- | :--- | :--- | :--- |
| `-t` | `--tui` | - | Launch interactive Bashtop-style TUI dashboard directly |
| `-p` | `--path` | `.` | Target folder or drive to scan (e.g. `C:\` or `/var`) |
| `-s` | `--min-size` | `100` | Minimum file size threshold in Megabytes (MB) |
| `-c` | `--csv` | `None` | Save output to a CSV file (e.g. `report.csv`) |
| `-j` | `--json` | `None` | Save output and statistics to a JSON file |
| `-l` | `--limit` | `50` | Maximum rows displayed in console table |
| `-d` | `--drives` | - | Display storage drives and free space only |
| `-m` | `--menu` | - | Force launch the interactive menu |
| `--follow-symlinks` | `--follow-symlinks` | `False` | Follow symbolic links during traversal |

---

## 🧪 Running Unit Tests

Run the test suite to verify file scanning, size calculations, export, and TUI filtering:
```bash
python -m unittest tests/test_scanner.py
```
