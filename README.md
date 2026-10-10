# 🗄️ Server Disk Manager - Large File Scanner & Docker Image Cleaner

[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Python: 3.8+](https://img.shields.io/badge/python-3.8+-green.svg)](https://www.python.org/)

A high-performance, modular, zero-dependency server maintenance tool to inspect storage disks, find heavy files (>= 100 MB by default), export CSV/JSON reports, and reclaim disk space using a **Bashtop-style interactive TUI with live file deletion and Docker image pruning**.

**By default, running `python main.py` directly launches the interactive Bashtop TUI.**

---

## ⚡ Quick Start / Run Instructions (دستور اجرا)

### 🚀 One-Line Temporary Run with `curl` (اجرای موقت بدون نیاز به کلون):

Run directly in memory or temporary folder without leaving residue:

#### 🐧 Linux / macOS:
```bash
# Directly launches the Bashtop TUI with Docker & Large File cleaner:
bash <(curl -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/run.sh)

# Or scan root / non-interactively for >= 100MB and save report.csv:
curl -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py | python3 - -p / -s 100 -c /tmp/large_files.csv
```

#### 🪟 Windows (PowerShell):
```powershell
# Directly launches the Bashtop TUI (Temporary run, auto-cleans up on exit):
curl.exe -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py -o $env:TEMP\dm.py; python $env:TEMP\dm.py; Remove-Item $env:TEMP\dm.py

# Or scan drive C:\ directly and export CSV:
curl.exe -sSL https://raw.githubusercontent.com/samaelleo/server-disk-manager/main/disk_manager.py | python - -p C:\ -s 100 -c large_files.csv
```

---

### 📦 Standard Clone & Run:
```bash
# Clone the repository
git clone https://github.com/samaelleo/server-disk-manager.git

# Navigate into project directory
cd server-disk-manager

# Directly launch the Bashtop-style TUI:
python main.py
```

> 💡 **Requirements**: Python 3.8+ (Zero pip dependencies - pure standard library).

---

## 🖥️ Bashtop-Style Interactive TUI Mode

The tool directly launches into an interactive terminal dashboard with two dedicated tabs:

```text
┌─────────────────────────────────────────────────────────────────────────────┐
│                 🗄️  SERVER DISK MANAGER - BASHTOP DASHBOARD                  │
├─────────────────────────────────────────────────────────────────────────────┤
│  [1] 📁 Large Files Disk Scan      [2] 🐳 Docker Images & Storage           │
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
│ [TAB] Docker  [↑/↓] Move  [d/DEL] Delete File  [o] Details  [/] Search      │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 🐳 Tab 2: Docker Images & Storage Manager
Press **`TAB`** or **`2`** to switch to the Docker management tab:
- **Automatic Status Detection**: Detects whether Docker daemon is running or stopped.
- **In-Use vs Unused Tracking**: Queries running and stopped containers to tag each image as `[IN USE]` (green), `[UNUSED]` (yellow), or `[DANGLING]` (red).
- **Single Image Removal (`d` or `DEL`)**: Safely removes a selected image (`docker rmi`) with confirmation.
- **Bulk Prune Unused Images (`p`)**: Runs `docker image prune -a -f` to reclaim all unreferenced Docker space with a single confirmation.

### 🎮 TUI Keybindings:
- **`TAB` / `1` / `2`**: Switch between **📁 Large Files** and **🐳 Docker Images** tabs.
- **`↑` / `↓` (or `k` / `j` / `w`)**: Move selection cursor up / down.
- **`Page Up` / `Page Down` (or `←` / `→`)**: Scroll 15 items up / down.
- **`d` or `Delete`**:
  - In Files Tab: **Delete selected file** (prompts with safety confirmation dialog `yes`/`y` and updates disk space immediately).
  - In Docker Tab: **Remove selected Docker image** (`docker rmi`).
- **`p`**: (Docker Tab) **Prune all unused Docker images** (`docker image prune -a`).
- **`o` or `ENTER`**: (Files Tab) Open file details (exact bytes, permissions, timestamps).
- **`/`**: (Files Tab) Search / Filter files in real-time by keyword or extension (e.g. `.iso`, `backup`). Press `ESC` to clear.
- **`s`**: (Files Tab) Toggle sort order (Largest first, Smallest first, Name A-Z, Date).
- **`r`**: Re-scan directory and refresh Docker images list.
- **`q`**: Exit TUI.

---

## 📁 Project Structure

```text
server-disk-manager/
│
├── disk_scanner/
│   ├── __init__.py
│   ├── scanner.py          # Core iterative directory scanner & stat collector
│   ├── reporter.py         # Console tables, CSV & JSON exporter
│   ├── utils.py            # Storage calculations, drive detection & formatters
│   ├── docker_manager.py   # Docker image inspection, unused tracking & pruning
│   └── tui.py              # Dual-tab Bashtop interactive TUI with file & Docker deletion
│
├── tests/
│   └── test_scanner.py     # Automated unit test suite
│
├── disk_manager.py         # Self-contained single-file bundle (for curl runs)
├── run.sh                  # Zero-trace temporary runner for Linux/macOS
├── main.py                 # Main entry point (defaults to TUI)
├── LICENSE                 # MIT License
├── .gitignore
└── README.md
```

---

## ⚙️ Command-Line Reference (CLI Flags)

| Flag | Long Option | Default | Description |
| :--- | :--- | :--- | :--- |
| *(no flags)* | *(default)* | - | **Launches interactive Bashtop TUI directly** |
| `-p` | `--path` | `.` | Target folder or drive to scan (e.g. `C:\` or `/var`) |
| `-s` | `--min-size` | `100` | Minimum file size threshold in Megabytes (MB) |
| `-c` | `--csv` | `None` | Save output to a CSV file (e.g. `report.csv`) |
| `-j` | `--json` | `None` | Save output and statistics to a JSON file |
| `-l` | `--limit` | `50` | Maximum rows displayed in console table |
| `-d` | `--drives` | - | Display storage drives and free space only |
| `-m` | `--menu` | - | Launch the classic text-based wizard menu instead of TUI |
| `--follow-symlinks` | `--follow-symlinks` | `False` | Follow symbolic links during traversal |

---

## 🧪 Running Unit Tests

Run the test suite to verify file scanning, size calculations, export, TUI filtering, and Docker management:
```bash
python -m unittest tests/test_scanner.py
```

---

## 📜 License

This project is licensed under the **MIT License** - see the [LICENSE](LICENSE) file for details.  
Copyright (c) 2026 Samael Leo Smith.
