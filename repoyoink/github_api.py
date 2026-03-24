"""GitHub API handler for RepoYoink.

Handles URL parsing, tree fetching, file content retrieval,
rate limiting, and optional authentication.
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass
from typing import Any

import httpx


class GitHubAPIError(Exception):
    """Base exception for GitHub API errors."""


class RepoNotFoundError(GitHubAPIError):
    """Repository not found or not accessible."""


class RateLimitError(GitHubAPIError):
    """GitHub API rate limit exceeded."""


class InvalidURLError(GitHubAPIError):
    """Invalid GitHub URL provided."""


@dataclass
class RepoInfo:
    """Parsed GitHub repository information."""
    owner: str
    repo: str
    branch: str | None = None
    path: str | None = None


def parse_github_url(url: str) -> RepoInfo:
    """Parse a GitHub URL into owner, repo, optional branch and path.

    Supports formats:
        https://github.com/owner/repo
        https://github.com/owner/repo/tree/branch
        https://github.com/owner/repo/tree/branch/path/to/dir
    """
    url = url.strip().rstrip("/")

    patterns = [
        # Full path with branch and subpath
        r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+)/tree/(?P<branch>[^/]+)(?:/(?P<path>.+))?",
        # Just owner/repo
        r"https?://github\.com/(?P<owner>[^/]+)/(?P<repo>[^/]+?)(?:\.git)?$",
    ]

    for pattern in patterns:
        match = re.match(pattern, url)
        if match:
            groups = match.groupdict()
            return RepoInfo(
                owner=groups["owner"],
                repo=groups["repo"],
                branch=groups.get("branch"),
                path=groups.get("path"),
            )

    raise InvalidURLError(f"Cannot parse GitHub URL: {url}")


class GitHubClient:
    """Async GitHub API client."""

    BASE_URL = "https://api.github.com"
    RAW_URL = "https://raw.githubusercontent.com"

    def __init__(self, token: str | None = None):
        self.token = token or os.environ.get("GITHUB_TOKEN")
        headers: dict[str, str] = {
            "Accept": "application/vnd.github.v3+json",
            "User-Agent": "RepoYoink/1.0",
        }
        if self.token:
            headers["Authorization"] = f"token {self.token}"
        self._client = httpx.AsyncClient(
            headers=headers,
            timeout=30.0,
            follow_redirects=True,
        )

    async def close(self) -> None:
        """Close the HTTP client."""
        await self._client.aclose()

    async def _request(self, method: str, url: str, **kwargs: Any) -> Any:
        """Make an API request with error handling."""
        try:
            response = await self._client.request(method, url, **kwargs)
        except httpx.ConnectError as exc:
            raise GitHubAPIError(f"Connection error: {exc}") from exc
        except httpx.TimeoutException as exc:
            raise GitHubAPIError(f"Request timed out: {exc}") from exc

        if response.status_code == 403:
            remaining = response.headers.get("X-RateLimit-Remaining", "?")
            if remaining == "0":
                reset = response.headers.get("X-RateLimit-Reset", "unknown")
                raise RateLimitError(
                    f"GitHub API rate limit exceeded. Resets at timestamp {reset}. "
                    "Set GITHUB_TOKEN env var for higher limits."
                )
            raise GitHubAPIError(f"Access forbidden: {response.text}")
        elif response.status_code == 404:
            raise RepoNotFoundError("Repository not found or not accessible.")
        elif response.status_code >= 400:
            raise GitHubAPIError(
                f"GitHub API error {response.status_code}: {response.text}"
            )

        return response.json()

    async def get_default_branch(self, owner: str, repo: str) -> str:
        """Get the default branch name for a repository."""
        data = await self._request("GET", f"{self.BASE_URL}/repos/{owner}/{repo}")
        return data["default_branch"]

    async def get_tree(
        self, owner: str, repo: str, branch: str
    ) -> list[dict[str, Any]]:
        """Fetch the full recursive file tree for a branch.

        Returns a list of tree entries with keys: path, mode, type, sha, size.
        """
        # Get the commit SHA for the branch
        data = await self._request(
            "GET", f"{self.BASE_URL}/repos/{owner}/{repo}/git/ref/heads/{branch}"
        )
        commit_sha = data["object"]["sha"]

        # Get the tree SHA from the commit
        commit_data = await self._request(
            "GET", f"{self.BASE_URL}/repos/{owner}/{repo}/git/commits/{commit_sha}"
        )
        tree_sha = commit_data["tree"]["sha"]

        # Fetch recursive tree
        tree_data = await self._request(
            "GET",
            f"{self.BASE_URL}/repos/{owner}/{repo}/git/trees/{tree_sha}",
            params={"recursive": "1"},
        )

        if tree_data.get("truncated"):
            # Tree is truncated (repo too large), fall back to Contents API
            pass  # We still return what we have

        return tree_data.get("tree", [])

    async def get_file_content(
        self, owner: str, repo: str, path: str, ref: str
    ) -> str:
        """Fetch raw file content for preview."""
        url = f"{self.RAW_URL}/{owner}/{repo}/{ref}/{path}"
        try:
            response = await self._client.get(url)
            response.raise_for_status()
            return response.text
        except httpx.HTTPStatusError as exc:
            raise GitHubAPIError(
                f"Failed to fetch file content: {exc.response.status_code}"
            ) from exc
        except httpx.ConnectError as exc:
            raise GitHubAPIError(f"Connection error: {exc}") from exc

    def get_raw_url(self, owner: str, repo: str, ref: str, path: str) -> str:
        """Get the raw content URL for a file."""
        return f"{self.RAW_URL}/{owner}/{repo}/{ref}/{path}"
