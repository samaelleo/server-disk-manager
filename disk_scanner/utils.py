import os
from datetime import datetime
from typing import Union


def format_size(bytes_size: int) -> str:
    """
    Format a byte size into human readable string (B, KB, MB, GB, TB).
    """
    for unit in ['B', 'KB', 'MB', 'GB', 'TB', 'PB']:
        if bytes_size < 1024.0 or unit == 'PB':
            if unit in ['B']:
                return f"{bytes_size} {unit}"
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} PB"


def format_timestamp(timestamp: float) -> str:
    """
    Convert a posix timestamp to a readable date/time string.
    """
    try:
        return datetime.fromtimestamp(timestamp).strftime("%Y-%m-%d %H:%M:%S")
    except (ValueError, OSError):
        return "Unknown"


def is_symlink_or_reparse(entry: os.DirEntry) -> bool:
    """
    Check if a DirEntry is a symlink or reparse point to prevent recursion loops.
    """
    try:
        return entry.is_symlink()
    except OSError:
        return False


def get_available_drives() -> list:
    """
    Returns list of mounted drives with total, used, and free space.
    Works seamlessly on Windows and Linux/Unix.
    """
    import shutil
    drives = []

    if os.name == "nt":
        import string
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
        # Linux / Unix
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

