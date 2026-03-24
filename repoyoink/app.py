"""RepoYoink – Main TUI Application.

A terminal-based interactive GitHub repository browser and selective downloader.
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

from textual import on, work
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Container, Horizontal, Vertical
from textual.screen import Screen
from textual.widgets import (
    Footer,
    Header,
    Input,
    Label,
    LoadingIndicator,
    ProgressBar,
    Static,
    Tree,
)
from textual.widgets.tree import TreeNode as TextualTreeNode

from .downloader import DownloadManager, DownloadProgress
from .github_api import (
    GitHubAPIError,
    GitHubClient,
    InvalidURLError,
    RateLimitError,
    RepoNotFoundError,
    parse_github_url,
)
from .tree_model import (
    SelectionState,
    TreeNode,
    build_tree,
    deselect_all,
    select_all,
)
from .widgets import RepoTree, format_node_label


# ──────────────────────────────────────────────
#  URL Input Screen
# ──────────────────────────────────────────────


class URLScreen(Screen):
    """Screen for entering a GitHub repository URL."""

    BINDINGS = [
        Binding("escape", "quit", "Quit", show=True),
    ]

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                "╦═╗ ╔═╗ ╔═╗ ╔═╗  ╦ ╦ ╔═╗ ╦ ╔╗╔ ╦╔═\n"
                "╠╦╝ ║╣  ╠═╝ ║ ║  ╚╦╝ ║ ║ ║ ║║║ ╠╩╗\n"
                "╩╚═ ╚═╝ ╩   ╚═╝   ╩  ╚═╝ ╩ ╝╚╝ ╩ ╩",
                id="logo-text",
            ),
            Static(
                "Selective GitHub Repository Downloader",
                id="url-subtitle",
            ),
            Input(
                placeholder="Paste GitHub repo URL (e.g. https://github.com/user/repo)",
                id="url-input",
            ),
            Static("", id="url-error"),
            Static("", id="url-status"),
            Static(
                "Press [bold]Enter[/bold] to fetch • [bold]Esc[/bold] to quit",
                id="url-help",
            ),
            id="url-container",
        )

    def on_mount(self) -> None:
        self.query_one("#url-input", Input).focus()

    @on(Input.Submitted, "#url-input")
    def on_url_submitted(self, event: Input.Submitted) -> None:
        url = event.value.strip()
        if not url:
            self._show_error("Please enter a GitHub URL")
            return

        self._show_status("Fetching repository...")
        self.app.post_message(FetchRepo(url))

    def _show_error(self, msg: str) -> None:
        err = self.query_one("#url-error", Static)
        err.update(f"[bold red]✗[/] {msg}")
        err.display = True
        status = self.query_one("#url-status", Static)
        status.display = False

    def _show_status(self, msg: str) -> None:
        status = self.query_one("#url-status", Static)
        status.update(f"[bold cyan]⟳[/] {msg}")
        status.display = True
        err = self.query_one("#url-error", Static)
        err.display = False

    def show_error(self, msg: str) -> None:
        self._show_error(msg)


# ──────────────────────────────────────────────
#  Explorer Screen
# ──────────────────────────────────────────────


class ExplorerScreen(Screen):
    """Screen for browsing and selecting repository files."""

    BINDINGS = [
        Binding("tab", "toggle_select", "Select", show=True),
        Binding("ctrl+s", "select_all", "Select All", show=True),
        Binding("ctrl+d", "download", "Download", show=True),
        Binding("slash", "search", "Search", show=True),
        Binding("p", "preview", "Preview", show=True),
        Binding("escape", "back", "Back", show=True),
        Binding("q", "quit", "Quit", show=True),
    ]

    def __init__(
        self,
        owner: str,
        repo: str,
        branch: str,
        tree_data: TreeNode,
        client: GitHubClient,
    ):
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.tree_data = tree_data
        self.client = client
        self._all_selected = False
        self._search_visible = False
        self._preview_visible = False

    def compose(self) -> ComposeResult:
        yield Container(
            Horizontal(
                Static(
                    f"[bold]📦 {self.owner}/{self.repo}[/] [dim]({self.branch})[/]",
                    id="header-title",
                ),
                Static("", id="header-stats"),
                id="explorer-header",
            ),
            Horizontal(
                Container(
                    RepoTree(f"{self.owner}/{self.repo}", id="repo-tree"),
                    id="tree-panel",
                ),
                Container(
                    Static("", id="preview-title"),
                    Static("", id="preview-content"),
                    id="preview-panel",
                ),
                id="explorer-body",
            ),
            Input(
                placeholder="🔍 Type to search... (Esc to close)",
                id="search-bar",
            ),
            Static(
                "[bold]Tab[/] Select • [bold]Ctrl+S[/] Select All • "
                "[bold]Ctrl+D[/] Download • [bold]/[/] Search • "
                "[bold]p[/] Preview • [bold]Esc[/] Back",
                id="footer-bar",
            ),
            id="explorer-screen",
        )

    def on_mount(self) -> None:
        tree_widget = self.query_one("#repo-tree", RepoTree)
        tree_widget.load_tree(self.tree_data)
        tree_widget.focus()
        self._update_stats()

    def _update_stats(self) -> None:
        selected = self.tree_data.count_selected()
        total = self.tree_data.count_total_files()
        stats = self.query_one("#header-stats", Static)
        stats.update(f"[bold]{selected}[/]/{total} files selected")

    # ── Selection ──

    def action_toggle_select(self) -> None:
        tree = self.query_one("#repo-tree", RepoTree)
        cursor_node = tree.cursor_node
        if cursor_node is not None:
            tree.toggle_node_selection(cursor_node)
            self._update_stats()

    def action_select_all(self) -> None:
        tree = self.query_one("#repo-tree", RepoTree)
        if self._all_selected:
            tree.deselect_all()
            self._all_selected = False
        else:
            tree.select_all()
            self._all_selected = True
        self._update_stats()

    # ── Search ──

    def action_search(self) -> None:
        search_bar = self.query_one("#search-bar", Input)
        if self._search_visible:
            search_bar.display = False
            self._search_visible = False
            self.query_one("#repo-tree", RepoTree).focus()
        else:
            search_bar.display = True
            search_bar.value = ""
            search_bar.focus()
            self._search_visible = True

    @on(Input.Changed, "#search-bar")
    def on_search_changed(self, event: Input.Changed) -> None:
        """Filter tree based on search query."""
        query = event.value.strip()
        tree = self.query_one("#repo-tree", RepoTree)

        if not query:
            # Show all nodes
            self._show_all_nodes(tree.root)
            return

        # Filter nodes
        self._filter_nodes(tree.root, query.lower())

    def _filter_nodes(self, node: TextualTreeNode, query: str) -> bool:
        """Recursively show/hide nodes based on search query. Returns True if visible."""
        data: TreeNode | None = node.data
        if data is None:
            # Root node - process children
            any_visible = False
            for child in node.children:
                if self._filter_nodes(child, query):
                    any_visible = True
            return any_visible

        name_matches = query in data.name.lower()

        if data.is_dir:
            any_child_visible = False
            for child in node.children:
                if self._filter_nodes(child, query):
                    any_child_visible = True

            visible = name_matches or any_child_visible
            node.allow_expand = visible
            if visible and any_child_visible:
                node.expand()
            return visible
        else:
            return name_matches

    def _show_all_nodes(self, node: TextualTreeNode) -> None:
        """Show all nodes (reset filter)."""
        data: TreeNode | None = node.data
        if data and data.is_dir:
            node.allow_expand = True
        for child in node.children:
            self._show_all_nodes(child)

    @on(Input.Submitted, "#search-bar")
    def on_search_submitted(self, event: Input.Submitted) -> None:
        """Close search and focus tree on Enter."""
        self.action_search()

    # ── Preview ──

    def action_preview(self) -> None:
        if self._preview_visible:
            self.query_one("#preview-panel").display = False
            self._preview_visible = False
            return

        tree = self.query_one("#repo-tree", RepoTree)
        cursor_node = tree.cursor_node
        if cursor_node is None:
            return

        data: TreeNode | None = cursor_node.data
        if data is None or data.is_dir:
            return

        self._preview_visible = True
        self.query_one("#preview-panel").display = True
        self.query_one("#preview-title", Static).update(
            f" 📄 {data.name}"
        )
        self.query_one("#preview-content", Static).update(
            "[dim]Loading...[/]"
        )
        self._load_preview(data.path)

    @work(exclusive=True)
    async def _load_preview(self, path: str) -> None:
        """Load file content for preview."""
        try:
            content = await self.client.get_file_content(
                self.owner, self.repo, path, self.branch
            )
            # Truncate very long files
            lines = content.split("\n")
            if len(lines) > 200:
                content = "\n".join(lines[:200]) + f"\n\n... ({len(lines) - 200} more lines)"

            self.query_one("#preview-content", Static).update(content)
        except Exception as exc:
            self.query_one("#preview-content", Static).update(
                f"[bold red]Error:[/] {exc}"
            )

    # ── Tree Events ──

    @on(Tree.NodeExpanded)
    def on_node_expanded(self, event: Tree.NodeExpanded) -> None:
        data: TreeNode | None = event.node.data
        if data and isinstance(data, TreeNode):
            label = format_node_label(data, expanded=True)
            event.node.set_label(label)

    @on(Tree.NodeCollapsed)
    def on_node_collapsed(self, event: Tree.NodeCollapsed) -> None:
        data: TreeNode | None = event.node.data
        if data and isinstance(data, TreeNode):
            label = format_node_label(data, expanded=False)
            event.node.set_label(label)

    # ── Download ──

    def action_download(self) -> None:
        selected = self.tree_data.count_selected()
        if selected == 0:
            self.notify("No files selected!", severity="warning")
            return
        self.app.post_message(StartDownload())

    # ── Navigation ──

    def action_back(self) -> None:
        if self._search_visible:
            self.action_search()
            return
        if self._preview_visible:
            self.query_one("#preview-panel").display = False
            self._preview_visible = False
            return
        self.app.pop_screen()

    def action_quit(self) -> None:
        self.app.exit()


# ──────────────────────────────────────────────
#  Download Screen
# ──────────────────────────────────────────────


class DownloadScreen(Screen):
    """Screen showing download progress."""

    BINDINGS = [
        Binding("escape", "back", "Back", show=True),
    ]

    def __init__(
        self,
        owner: str,
        repo: str,
        branch: str,
        tree_data: TreeNode,
        client: GitHubClient,
    ):
        super().__init__()
        self.owner = owner
        self.repo = repo
        self.branch = branch
        self.tree_data = tree_data
        self.client = client
        self._manager: DownloadManager | None = None

    def compose(self) -> ComposeResult:
        yield Container(
            Static("⬇ Downloading Files", id="download-title"),
            ProgressBar(total=100, id="download-progress", show_percentage=False, show_eta=False),
            Static("", id="download-percentage"),
            Static("Preparing...", id="download-status"),
            Static("", id="download-file"),
            Static("", id="download-done"),
            id="download-container",
        )

    def on_mount(self) -> None:
        self._start_download()

    @work(exclusive=True)
    async def _start_download(self) -> None:
        """Run the download process."""
        dest = Path.cwd() / f"{self.owner}_{self.repo}"

        self._manager = DownloadManager(
            client=self.client,
            owner=self.owner,
            repo=self.repo,
            ref=self.branch,
            dest=dest,
        )

        total = self.tree_data.count_selected()
        progress_bar = self.query_one("#download-progress", ProgressBar)
        progress_bar.update(total=total, progress=0)

        async def on_progress(p: DownloadProgress) -> None:
            progress_bar.update(progress=p.completed)
            # Calculate percentage
            percentage = (p.completed / p.total) * 100 if p.total > 0 else 0
            self.query_one("#download-percentage", Static).update(
                f"[bold]{percentage:.0f}%[/] [dim]({p.completed}/{p.total})[/]"
            )
            self.query_one("#download-status", Static).update(
                "Downloading..."
            )
            self.query_one("#download-file", Static).update(
                f"[dim]{p.current_file}[/]"
            )

        results = await self._manager.download_selected(
            self.tree_data, progress_callback=on_progress
        )

        succeeded = sum(1 for r in results if r.success)
        failed = sum(1 for r in results if not r.success)
        total_bytes = sum(r.size for r in results if r.success)

        done_msg = f"[bold green]✓ Complete![/] {succeeded} files downloaded"
        if failed:
            done_msg += f" [bold red]({failed} failed)[/]"
        done_msg += f"\n  📁 Saved to: [bold]{dest}[/]"
        done_msg += f"\n  📊 Total size: {_format_bytes(total_bytes)}"

        self.query_one("#download-done", Static).update(done_msg)
        self.query_one("#download-done").display = True
        self.query_one("#download-status", Static).update("Download complete!")
        self.query_one("#download-file", Static).update(
            "[dim]Press Esc to go back[/]"
        )

    def action_back(self) -> None:
        if self._manager:
            self._manager.cancel()
        self.app.pop_screen()


# ──────────────────────────────────────────────
#  Custom Messages
# ──────────────────────────────────────────────

from textual.message import Message


class FetchRepo(Message):
    """Message to trigger repo fetching."""
    def __init__(self, url: str):
        super().__init__()
        self.url = url


class StartDownload(Message):
    """Message to trigger download."""
    pass


# ──────────────────────────────────────────────
#  Main Application
# ──────────────────────────────────────────────


class RepoYoinkApp(App):
    """RepoYoink – Terminal-based selective GitHub downloader."""

    TITLE = "RepoYoink"
    SUB_TITLE = "Selective GitHub Downloader"
    CSS_PATH = "app.tcss"

    BINDINGS = [
        Binding("q", "quit", "Quit", show=True, priority=True),
    ]

    def __init__(self):
        super().__init__()
        self.client = GitHubClient()
        self._owner: str = ""
        self._repo: str = ""
        self._branch: str = ""
        self._tree_data: TreeNode | None = None

    def on_mount(self) -> None:
        self.push_screen(URLScreen())

    @on(FetchRepo)
    def on_fetch_repo(self, event: FetchRepo) -> None:
        self._fetch_repository(event.url)

    @work(exclusive=True)
    async def _fetch_repository(self, url: str) -> None:
        """Fetch repository tree from GitHub."""
        url_screen = self.screen
        if not isinstance(url_screen, URLScreen):
            return

        try:
            repo_info = parse_github_url(url)
        except InvalidURLError as exc:
            url_screen.show_error(str(exc))
            return

        self._owner = repo_info.owner
        self._repo = repo_info.repo

        try:
            # Get branch
            if repo_info.branch:
                self._branch = repo_info.branch
            else:
                self._branch = await self.client.get_default_branch(
                    self._owner, self._repo
                )

            # Fetch tree
            api_tree = await self.client.get_tree(
                self._owner, self._repo, self._branch
            )

            # Build tree model
            self._tree_data = build_tree(api_tree, repo_info.path)

        except RepoNotFoundError:
            url_screen.show_error(
                "Repository not found. Check the URL or set GITHUB_TOKEN for private repos."
            )
            return
        except RateLimitError as exc:
            url_screen.show_error(str(exc))
            return
        except GitHubAPIError as exc:
            url_screen.show_error(f"API Error: {exc}")
            return
        except Exception as exc:
            url_screen.show_error(f"Unexpected error: {exc}")
            return

        # Switch to explorer screen
        self.push_screen(
            ExplorerScreen(
                owner=self._owner,
                repo=self._repo,
                branch=self._branch,
                tree_data=self._tree_data,
                client=self.client,
            )
        )

    @on(StartDownload)
    def on_start_download(self, event: StartDownload) -> None:
        if self._tree_data:
            self.push_screen(
                DownloadScreen(
                    owner=self._owner,
                    repo=self._repo,
                    branch=self._branch,
                    tree_data=self._tree_data,
                    client=self.client,
                )
            )

    async def on_unmount(self) -> None:
        await self.client.close()


def _format_bytes(size: int) -> str:
    """Format bytes into human readable string."""
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024:
            return f"{size:.1f} {unit}" if unit != "B" else f"{size} {unit}"
        size /= 1024
    return f"{size:.1f} TB"


def main() -> None:
    """Entry point for the repoyoink command."""
    app = RepoYoinkApp()
    app.run()


if __name__ == "__main__":
    main()
