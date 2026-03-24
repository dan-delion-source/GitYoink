"""Custom widgets for RepoYoink TUI."""

from __future__ import annotations

from textual.widgets import Tree as TextualTree, Static, Input
from textual.widgets.tree import TreeNode as TextualTreeNode

from .tree_model import TreeNode, SelectionState, NodeType


# Icons for the tree
ICONS = {
    "dir_open": "📂",
    "dir_closed": "📁",
    "file": "📄",
    "selected": "☑",       # ☑
    "unselected": "☐",     # ☐
    "partial": "▣",        # ▣ partial selection
}

# File extension → icon mapping for visual flair
FILE_ICONS: dict[str, str] = {
    ".py": "🐍",
    ".js": "🟨",
    ".ts": "🔷",
    ".jsx": "⚛️",
    ".tsx": "⚛️",
    ".json": "📋",
    ".md": "📝",
    ".txt": "📃",
    ".yml": "⚙️",
    ".yaml": "⚙️",
    ".toml": "⚙️",
    ".cfg": "⚙️",
    ".ini": "⚙️",
    ".html": "🌐",
    ".css": "🎨",
    ".scss": "🎨",
    ".rs": "🦀",
    ".go": "🐹",
    ".java": "☕",
    ".rb": "💎",
    ".sh": "🔧",
    ".bash": "🔧",
    ".zsh": "🔧",
    ".dockerfile": "🐳",
    ".docker": "🐳",
    ".png": "🖼️",
    ".jpg": "🖼️",
    ".jpeg": "🖼️",
    ".gif": "🖼️",
    ".svg": "🖼️",
    ".ico": "🖼️",
    ".lock": "🔒",
    ".env": "🔐",
    ".gitignore": "🚫",
    ".license": "📜",
}


def get_file_icon(name: str) -> str:
    """Get an appropriate icon for a filename."""
    name_lower = name.lower()
    # Check full name first (e.g., Dockerfile, .gitignore)
    if name_lower in FILE_ICONS:
        return FILE_ICONS[name_lower]
    if name_lower == "dockerfile":
        return "🐳"
    if name_lower == "makefile":
        return "🔧"
    if name_lower.startswith("license"):
        return "📜"
    if name_lower.startswith("readme"):
        return "📝"

    # Check extension
    for ext, icon in FILE_ICONS.items():
        if name_lower.endswith(ext):
            return icon
    return "📄"


def format_node_label(node: TreeNode, expanded: bool = False) -> str:
    """Format a tree node label with checkbox and icon."""
    # Selection checkbox
    if node.selection == SelectionState.SELECTED:
        checkbox = ICONS["selected"]
    elif node.selection == SelectionState.PARTIAL:
        checkbox = ICONS["partial"]
    else:
        checkbox = ICONS["unselected"]

    # Node icon
    if node.is_dir:
        icon = ICONS["dir_open"] if expanded else ICONS["dir_closed"]
    else:
        icon = get_file_icon(node.name)

    # Size suffix for files
    size_str = ""
    if node.is_file and node.size > 0:
        size_str = f" ({_format_size(node.size)})"

    return f"{checkbox} {icon} {node.name}{size_str}"


def _format_size(size_bytes: int) -> str:
    """Format file size for display."""
    if size_bytes < 1024:
        return f"{size_bytes}B"
    elif size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.1f}KB"
    elif size_bytes < 1024 * 1024 * 1024:
        return f"{size_bytes / (1024 * 1024):.1f}MB"
    return f"{size_bytes / (1024 * 1024 * 1024):.1f}GB"


class RepoTree(TextualTree):
    """Custom tree widget for browsing repository files with selection."""

    def __init__(self, label: str = "Repository", **kwargs):
        super().__init__(label, **kwargs)
        self._tree_data: TreeNode | None = None
        self._node_map: dict[str, TreeNode] = {}
        self._textual_node_map: dict[str, TextualTreeNode] = {}

    def load_tree(self, root: TreeNode) -> None:
        """Load a TreeNode hierarchy into the Textual tree widget."""
        self._tree_data = root
        self._node_map.clear()
        self._textual_node_map.clear()

        self.clear()
        self.root.set_label(f"📦 {self.root.label}")
        self.root.data = root

        self._add_children(self.root, root)
        self.root.expand()

    def _add_children(
        self, textual_parent: TextualTreeNode, data_parent: TreeNode
    ) -> None:
        """Recursively add children to the textual tree."""
        for child in data_parent.children:
            label = format_node_label(child)
            self._node_map[child.path] = child

            if child.is_dir:
                t_node = textual_parent.add(label, data=child)
                self._textual_node_map[child.path] = t_node
                self._add_children(t_node, child)
            else:
                t_node = textual_parent.add_leaf(label, data=child)
                self._textual_node_map[child.path] = t_node

    def toggle_node_selection(self, textual_node: TextualTreeNode) -> None:
        """Toggle selection on a node and update the display."""
        data_node: TreeNode | None = textual_node.data
        if data_node is None:
            return

        data_node.toggle_selection()

        # Update parent selection states up the chain
        self._update_parent_chain(textual_node)

        # Refresh labels for this node and all descendants
        self._refresh_label(textual_node)
        if data_node.is_dir:
            self._refresh_children_labels(textual_node)

    def _update_parent_chain(self, textual_node: TextualTreeNode) -> None:
        """Walk up the tree and update parent selection states."""
        current = textual_node.parent
        while current is not None:
            data: TreeNode | None = current.data
            if data and isinstance(data, TreeNode):
                data.update_parent_selection()
                self._refresh_label(current)
            current = current.parent

    def _refresh_label(self, textual_node: TextualTreeNode) -> None:
        """Refresh the label of a single textual tree node."""
        data: TreeNode | None = textual_node.data
        if data and isinstance(data, TreeNode):
            expanded = textual_node.is_expanded if hasattr(textual_node, "is_expanded") else False
            label = format_node_label(data, expanded)
            textual_node.set_label(label)

    def _refresh_children_labels(self, textual_node: TextualTreeNode) -> None:
        """Recursively refresh labels for all descendants."""
        for child in textual_node.children:
            self._refresh_label(child)
            self._refresh_children_labels(child)

    def refresh_all_labels(self) -> None:
        """Refresh all node labels in the tree."""
        self._refresh_node_recursive(self.root)

    def _refresh_node_recursive(self, textual_node: TextualTreeNode) -> None:
        """Recursively refresh labels."""
        self._refresh_label(textual_node)
        for child in textual_node.children:
            self._refresh_node_recursive(child)

    def select_all(self) -> None:
        """Select all nodes."""
        if self._tree_data:
            from .tree_model import select_all
            select_all(self._tree_data)
            self.refresh_all_labels()

    def deselect_all(self) -> None:
        """Deselect all nodes."""
        if self._tree_data:
            from .tree_model import deselect_all
            deselect_all(self._tree_data)
            self.refresh_all_labels()

    @property
    def tree_data(self) -> TreeNode | None:
        return self._tree_data
