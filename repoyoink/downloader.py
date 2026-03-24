"""Download manager for RepoYoink.

Handles concurrent downloading of selected files while preserving
directory structure and reporting progress.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Callable, Awaitable

import httpx

from .tree_model import TreeNode
from .github_api import GitHubClient


@dataclass
class DownloadResult:
    """Result of a file download."""
    path: str
    success: bool
    error: str | None = None
    size: int = 0


@dataclass
class DownloadProgress:
    """Progress update for downloads."""
    completed: int
    total: int
    current_file: str
    bytes_downloaded: int

    @property
    def percentage(self) -> float:
        if self.total == 0:
            return 100.0
        return (self.completed / self.total) * 100


ProgressCallback = Callable[[DownloadProgress], Awaitable[None]]


class DownloadManager:
    """Manages concurrent file downloads from GitHub."""

    def __init__(
        self,
        client: GitHubClient,
        owner: str,
        repo: str,
        ref: str,
        dest: str | Path = ".",
        max_concurrent: int = 10,
    ):
        self.client = client
        self.owner = owner
        self.repo = repo
        self.ref = ref
        self.dest = Path(dest)
        self.max_concurrent = max_concurrent
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._results: list[DownloadResult] = []
        self._completed = 0
        self._total = 0
        self._bytes_downloaded = 0
        self._cancelled = False

    def cancel(self) -> None:
        """Cancel ongoing downloads."""
        self._cancelled = True

    async def download_selected(
        self,
        root: TreeNode,
        progress_callback: ProgressCallback | None = None,
    ) -> list[DownloadResult]:
        """Download all selected files from the tree.

        Args:
            root: Root tree node with selection state.
            progress_callback: Async callback for progress updates.

        Returns:
            List of DownloadResult for each file attempted.
        """
        # Collect all selected file paths
        selected_files = list(root.get_selected_files())
        self._total = len(selected_files)
        self._completed = 0
        self._results = []
        self._bytes_downloaded = 0
        self._cancelled = False

        if not selected_files:
            return []

        # Create download tasks
        tasks = [
            self._download_file(node, progress_callback)
            for node in selected_files
        ]

        await asyncio.gather(*tasks, return_exceptions=True)
        return self._results

    async def _download_file(
        self,
        node: TreeNode,
        progress_callback: ProgressCallback | None,
    ) -> None:
        """Download a single file with semaphore-controlled concurrency."""
        if self._cancelled:
            return

        async with self._semaphore:
            if self._cancelled:
                return

            file_path = node.path
            dest_path = self.dest / file_path

            try:
                # Ensure parent directory exists
                dest_path.parent.mkdir(parents=True, exist_ok=True)

                # Get raw URL and download
                url = self.client.get_raw_url(
                    self.owner, self.repo, self.ref, file_path
                )

                async with self.client._client.stream("GET", url) as response:
                    response.raise_for_status()
                    total_size = 0

                    with open(dest_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=8192):
                            if self._cancelled:
                                return
                            f.write(chunk)
                            total_size += len(chunk)

                self._bytes_downloaded += total_size
                self._completed += 1

                result = DownloadResult(
                    path=file_path,
                    success=True,
                    size=total_size,
                )
                self._results.append(result)

                if progress_callback:
                    await progress_callback(
                        DownloadProgress(
                            completed=self._completed,
                            total=self._total,
                            current_file=file_path,
                            bytes_downloaded=self._bytes_downloaded,
                        )
                    )

            except Exception as exc:
                self._completed += 1
                result = DownloadResult(
                    path=file_path,
                    success=False,
                    error=str(exc),
                )
                self._results.append(result)

                if progress_callback:
                    await progress_callback(
                        DownloadProgress(
                            completed=self._completed,
                            total=self._total,
                            current_file=f"✗ {file_path}",
                            bytes_downloaded=self._bytes_downloaded,
                        )
                    )
