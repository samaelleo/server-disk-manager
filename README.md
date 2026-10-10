# 🗄️ Server Disk Manager - Large File Scanner

A high-performance, modular, zero-dependency Python tool to inspect server storage disks, locate heavy files (>= 100 MB by default), display formatted summaries, and export results to CSV and JSON formats.

All console output, reports, and table headers are in **English**, and the tool features a full **Interactive Menu** alongside **Command-Line (CLI)** capabilities.

---

## ⚡ Quick Start / Run Instructions (دستور اجرا)

### Clone & Run:
```bash
# Clone the repository
git clone https://github.com/samaelleo/server-disk-manager.git

# Navigate into project directory
cd server-disk-manager

# Run Interactive Menu
python main.py
```

### Windows & Linux One-Liners:
- **Interactive Menu (Recommended):**
  ```bash
  python main.py
  ```
- **Direct Scan Drive `C:\` for files >= 100 MB and save to CSV:**
  ```bash
  python main.py -p C:\ -s 100 -c large_files.csv
  ```
- **Linux Server Scan `/var/log` for files >= 200 MB:**
  ```bash
  python3 main.py -p /var/log -s 200 -c report.csv
  ```
- **Check Server Storage Drives & Free Space:**
  ```bash
  python main.py -d
  ```

> 💡 **Requirements**: Python 3.8+ (No external pip dependencies required - pure Python standard library).

---

## ✨ Key Features

- 🖥️ **Interactive Terminal Menu**: Choose tasks via an easy numeric menu (`Guided Scan`, `Quick Scan`, `View Storage Drives`, etc.).
- 🚀 **High Performance & Low Memory**: Built using `os.scandir` and an iterative stack traversal to prevent recursion limits and maximize I/O speed.
- 🛡️ **Graceful Permission Handling**: Skips system-restricted or inaccessible paths without crashing, tracking them under `Permission Denied`.
- 📊 **Clean English Console Tables**: Displays ranked tables sorted by size descending, complete with human-readable sizes (MB, GB), extensions, modification timestamps, and full absolute paths.
- 💾 **Export Options**: Export scan results directly to **CSV** (for Excel/spreadsheets) and **JSON** (for automation/APIs).
- 💽 **Drive Detection & Health**: Automatic detection of server drive mount points (`C:\`, `D:\`, `/`, `/home`, etc.) and storage utilization.
- 🌐 **Cross-Platform**: Ready for Windows Server and Linux environments.

---

## 📁 Project Structure

```text
server-disk-manager/
│
├── disk_scanner/
│   ├── __init__.py
│   ├── scanner.py      # Core iterative directory scanner & stat collector
│   ├── reporter.py     # Console tables, CSV & JSON exporter (English)
│   └── utils.py        # Storage calculations, drive detection & formatters
│
├── tests/
│   └── test_scanner.py # Automated unit test suite
│
├── main.py             # Main entry point (Interactive Menu + CLI)
├── .gitignore
└── README.md
```

---

## 🎮 How to Use

### 1. Interactive Menu Mode
Simply run the script with no arguments:
```bash
python main.py
```

**Main Menu Interface:**
```text
===========================================================================
                 SERVER DISK MANAGER - MAIN MENU
===========================================================================
  [1] Guided Scan (Configure drive, threshold & export options)
  [2] Quick Scan Primary Drive (>= 100 MB -> Export to CSV)
  [3] View Server Storage Drives & Free Space
  [4] Scan Current Directory (.)
  [0] Exit
===========================================================================
```

#### Guided Scan Wizard (`Option 1`):
The interactive wizard guides you step-by-step:
1. **Target Location**: Select a detected server drive by number or enter a custom path.
2. **Size Threshold**: Enter minimum size in MB (e.g. `100`, `500`, `1024` for 1 GB).
3. **Export Format**: Choose `Console only`, `CSV`, `JSON`, or `Both`.
4. **Display Limit**: Choose maximum rows to print on screen (default `50`).
5. **Symlinks**: Choose whether to traverse symbolic links.

---

### 2. Command-Line Arguments (CLI Mode)
You can automate or script scans without interactive prompts:

#### Scan drive `C:\` for files >= 100 MB and export to CSV:
```bash
python main.py -p C:\ -s 100 -c large_files.csv
```

#### Scan `/var/log` on Linux for files >= 200 MB with both CSV and JSON output:
```bash
python3 main.py -p /var/log -s 200 -c logs_report.csv -j logs_report.json
```

#### View available drives and free space without scanning:
```bash
python main.py -d
```

---

## ⚙️ Command-Line Reference (CLI Flags)

| Flag | Long Option | Default | Description |
| :--- | :--- | :--- | :--- |
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

Run the test suite to verify file scanning, size calculations, and export functionality:
```bash
python -m unittest tests/test_scanner.py
```
