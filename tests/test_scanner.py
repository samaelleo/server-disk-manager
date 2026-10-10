import os
import shutil
import tempfile
import unittest

from disk_scanner.scanner import DiskScanner, FileInfo
from disk_scanner.reporter import Reporter
from disk_scanner.utils import format_size, format_timestamp, get_available_drives


class TestDiskScanner(unittest.TestCase):
    def setUp(self):
        # Create a temporary directory for isolated testing
        self.test_dir = tempfile.mkdtemp(prefix="server_disk_test_")

        # Create dummy test files of specific sizes
        # 1. small file: 1 KB
        self.small_file = os.path.join(self.test_dir, "small.txt")
        with open(self.small_file, "wb") as f:
            f.write(b"0" * 1024)

        # 2. subfolder with a 2 MB file
        self.sub_dir = os.path.join(self.test_dir, "subdir")
        os.makedirs(self.sub_dir, exist_ok=True)
        self.medium_file = os.path.join(self.sub_dir, "medium.dat")
        with open(self.medium_file, "wb") as f:
            f.write(b"X" * (2 * 1024 * 1024))

        # 3. 5 MB file
        self.large_file = os.path.join(self.test_dir, "large.iso")
        with open(self.large_file, "wb") as f:
            f.write(b"Z" * (5 * 1024 * 1024))

    def tearDown(self):
        shutil.rmtree(self.test_dir, ignore_errors=True)

    def test_format_size(self):
        self.assertEqual(format_size(500), "500 B")
        self.assertEqual(format_size(1024), "1.00 KB")
        self.assertEqual(format_size(1048576), "1.00 MB")
        self.assertEqual(format_size(1073741824), "1.00 GB")

    def test_scanner_threshold(self):
        # Scan with min_size = 1.5 MB -> Should catch medium.dat (2MB) and large.iso (5MB)
        scanner = DiskScanner(target_path=self.test_dir, min_size_mb=1.5)
        results = scanner.scan()

        self.assertEqual(len(results), 2)
        # Results should be sorted descending
        self.assertGreaterEqual(results[0].size_bytes, results[1].size_bytes)
        self.assertEqual(results[0].path, self.large_file)
        self.assertEqual(results[1].path, self.medium_file)

    def test_scanner_higher_threshold(self):
        # Scan with min_size = 3.0 MB -> Should only catch large.iso
        scanner = DiskScanner(target_path=self.test_dir, min_size_mb=3.0)
        results = scanner.scan()

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0].path, self.large_file)

    def test_export_csv_and_json(self):
        scanner = DiskScanner(target_path=self.test_dir, min_size_mb=1.0)
        results = scanner.scan()

        csv_path = os.path.join(self.test_dir, "out.csv")
        json_path = os.path.join(self.test_dir, "out.json")

        Reporter.export_to_csv(results, csv_path)
        Reporter.export_to_json(results, scanner.stats, json_path)

        self.assertTrue(os.path.exists(csv_path))
        self.assertTrue(os.path.exists(json_path))

        with open(csv_path, "r", encoding="utf-8-sig") as f:
            content = f.read()
            self.assertIn("File Path", content)
            self.assertIn("large.iso", content)

    def test_get_available_drives(self):
        drives = get_available_drives()
        self.assertIsInstance(drives, list)
        self.assertGreater(len(drives), 0)
        self.assertIn("path", drives[0])
        self.assertIn("free", drives[0])

    def test_tui_filtering_and_sorting(self):
        from disk_scanner.tui import DiskManagerTUI, make_gauge_bar

        tui = DiskManagerTUI(target_path=self.test_dir, min_size_mb=1.0)
        tui.load_files()
        self.assertEqual(len(tui.files), 2)

        # Test filter
        tui.filter_query = ".iso"
        tui.apply_filter_and_sort()
        self.assertEqual(len(tui.filtered_files), 1)
        self.assertTrue(tui.filtered_files[0].path.endswith(".iso"))

        # Test gauge bar
        gauge = make_gauge_bar(50, 100, length=10)
        self.assertIn("50.0%", gauge)


if __name__ == "__main__":
    unittest.main()

