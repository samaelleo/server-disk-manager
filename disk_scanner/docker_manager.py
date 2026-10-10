"""
Docker Image and Storage Manager for Server Disk Manager.
Inspects, parses, and safely removes unused or dangling Docker images.
Zero external dependencies (uses standard library subprocess).
"""

import os
import re
import shutil
import subprocess
from dataclasses import dataclass
from typing import List, Optional, Tuple


def parse_size_to_bytes(size_str: str) -> int:
    """
    Parses human-readable Docker size strings (e.g., '1.45GB', '450MB', '28KB') into bytes.
    """
    s = size_str.strip().upper()
    match = re.match(r"^([0-9.]+)\s*([A-Z]+)$", s)
    if not match:
        return 0
    val, unit = match.groups()
    try:
        num = float(val)
    except ValueError:
        return 0

    multipliers = {
        "B": 1,
        "KB": 1024,
        "MB": 1024 * 1024,
        "GB": 1024 * 1024 * 1024,
        "TB": 1024 * 1024 * 1024 * 1024,
        "KIB": 1024,
        "MIB": 1024 * 1024,
        "GIB": 1024 * 1024 * 1024,
    }
    return int(num * multipliers.get(unit, 1))


@dataclass
class DockerImage:
    repository: str
    tag: str
    image_id: str
    size_str: str
    size_bytes: int
    created: str
    in_use: bool
    is_dangling: bool

    @property
    def full_name(self) -> str:
        if self.is_dangling or self.repository == "<none>":
            return f"<none>:<none> ({self.image_id[:12]})"
        return f"{self.repository}:{self.tag}"


class DockerManager:
    """
    Manages Docker daemon interaction, image listing, and cleanup.
    """

    @staticmethod
    def is_docker_running() -> Tuple[bool, str]:
        """
        Verifies if Docker CLI exists and Docker daemon is responsive.
        """
        if not shutil.which("docker"):
            return False, "Docker CLI is not installed or not in PATH."

        try:
            res = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                text=True,
                timeout=4,
            )
            if res.returncode == 0:
                return True, "Docker daemon is running."
            return False, f"Docker daemon not responding: {res.stderr.strip()[:100]}"
        except subprocess.TimeoutExpired:
            return False, "Docker daemon check timed out."
        except Exception as e:
            return False, f"Docker check failed: {str(e)}"

    @staticmethod
    def list_images() -> Tuple[List[DockerImage], str]:
        """
        Lists all Docker images, identifying whether they are in use by active/stopped containers.
        """
        running, msg = DockerManager.is_docker_running()
        if not running:
            return [], msg

        try:
            # 1. Get images currently used by containers
            used_images = set()
            ps_res = subprocess.run(
                ["docker", "ps", "-a", "--format", "{{.Image}}"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if ps_res.returncode == 0:
                for line in ps_res.stdout.splitlines():
                    img = line.strip()
                    if img:
                        used_images.add(img)

            # 2. Get list of all Docker images
            img_res = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}\t{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"],
                capture_output=True,
                text=True,
                timeout=6,
            )
            if img_res.returncode != 0:
                return [], f"Failed to list images: {img_res.stderr.strip()}"

            images: List[DockerImage] = []
            for line in img_res.stdout.splitlines():
                parts = line.split("\t")
                if len(parts) >= 5:
                    repo, tag, img_id, size_str, created = parts[:5]
                    is_dangling = repo == "<none>" or tag == "<none>"
                    # An image is in use if its ID or repo:tag matches any container
                    in_use = (img_id in used_images) or (f"{repo}:{tag}" in used_images) or (repo in used_images)

                    images.append(
                        DockerImage(
                            repository=repo,
                            tag=tag,
                            image_id=img_id,
                            size_str=size_str,
                            size_bytes=parse_size_to_bytes(size_str),
                            created=created,
                            in_use=in_use,
                            is_dangling=is_dangling,
                        )
                    )

            # Sort descending by size
            images.sort(key=lambda x: x.size_bytes, reverse=True)
            return images, ""
        except Exception as e:
            return [], f"Error querying Docker: {str(e)}"

    @staticmethod
    def remove_image(image_id: str, force: bool = False) -> Tuple[bool, str]:
        """
        Removes a specific Docker image by ID or name.
        """
        cmd = ["docker", "rmi"]
        if force:
            cmd.append("-f")
        cmd.append(image_id)

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=10)
            if res.returncode == 0:
                return True, f"Successfully removed image {image_id}"
            return False, res.stderr.strip() or res.stdout.strip()
        except Exception as e:
            return False, str(e)

    @staticmethod
    def prune_unused_images(all_unused: bool = True) -> Tuple[bool, str]:
        """
        Prunes Docker images.
        all_unused=True removes all unreferenced images (not just dangling ones).
        """
        cmd = ["docker", "image", "prune", "-f"]
        if all_unused:
            cmd.append("-a")

        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=25)
            if res.returncode == 0:
                # Extract reclaimed space line if available
                match = re.search(r"Total reclaimed space:\s*(.+)", res.stdout)
                reclaimed = match.group(1) if match else "images pruned"
                return True, f"Prune successful: Reclaimed {reclaimed}"
            return False, res.stderr.strip()
        except Exception as e:
            return False, str(e)
