"""File tree model for RepoYoink.

Converts flat GitHub API tree responses into a nested tree structure
with selection state management.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Iterator


class NodeType(Enum):
    """Type of tree node."""
    FILE = "blob"
    DIRECTORY = "tree"


class SelectionState(Enum):
    """Selection state for tree nodes."""
    UNSELECTED = 0
    PARTIAL = 1
    SELECTED = 2


@dataclass
class TreeNode:
    """A node in the repository file tree."""
    name: str
    path: str
    node_type: NodeType
    children: list[TreeNode] = field(default_factory=list)
    selection: SelectionState = SelectionState.UNSELECTED
    size: int = 0
    sha: str = ""

    @property
    def is_dir(self) -> bool:
        return self.node_type == NodeType.DIRECTORY

    @property
    def is_file(self) -> bool:
        return self.node_type == NodeType.FILE

    @property
    def is_selected(self) -> bool:
        return self.selection == SelectionState.SELECTED

    @property
    def is_partial(self) -> bool:
        return self.selection == SelectionState.PARTIAL

    def toggle_selection(self) -> None:
        """Toggle selection state. If selected/partial → unselect, if unselected → select."""
        if self.selection in (SelectionState.SELECTED, SelectionState.PARTIAL):
            self._set_selection_recursive(SelectionState.UNSELECTED)
        else:
            self._set_selection_recursive(SelectionState.SELECTED)

    def _set_selection_recursive(self, state: SelectionState) -> None:
        """Set selection state recursively for this node and all children."""
        self.selection = state
        for child in self.children:
            child._set_selection_recursive(state)

    def update_parent_selection(self) -> None:
        """Update this node's selection state based on children.
        Should be called bottom-up after toggling a child.
        """
        if not self.children:
            return

        all_selected = all(
            c.selection == SelectionState.SELECTED for c in self.children
        )
        any_selected = any(
            c.selection in (SelectionState.SELECTED, SelectionState.PARTIAL)
            for c in self.children
        )

        if all_selected:
            self.selection = SelectionState.SELECTED
        elif any_selected:
            self.selection = SelectionState.PARTIAL
        else:
            self.selection = SelectionState.UNSELECTED

    def get_selected_files(self) -> Iterator[TreeNode]:
        """Yield all selected file nodes recursively."""
        if self.is_file and self.is_selected:
            yield self
        for child in self.children:
            yield from child.get_selected_files()

    def count_selected(self) -> int:
        """Count the number of selected files recursively."""
        return sum(1 for _ in self.get_selected_files())

    def count_total_files(self) -> int:
        """Count total file nodes recursively."""
        if self.is_file:
            return 1
        return sum(c.count_total_files() for c in self.children)

    def sort_children(self) -> None:
        """Sort children: directories first, then files, both alphabetically."""
        self.children.sort(key=lambda n: (n.is_file, n.name.lower()))
        for child in self.children:
            child.sort_children()

    def filter_matches(self, query: str) -> bool:
        """Check if this node or any descendant matches the search query."""
        query_lower = query.lower()
        if query_lower in self.name.lower():
            return True
        return any(child.filter_matches(query) for child in self.children)


def build_tree(api_tree: list[dict], base_path: str | None = None) -> TreeNode:
    """Build a nested TreeNode structure from a flat GitHub API tree response.

    Args:
        api_tree: List of entries from GitHub's git/trees API.
        base_path: Optional base path to filter the tree to a subdirectory.

    Returns:
        Root TreeNode containing the full hierarchy.
    """
    root = TreeNode(name="/", path="", node_type=NodeType.DIRECTORY)

    # Build a map of path → node for quick lookup
    node_map: dict[str, TreeNode] = {"": root}

    # Sort entries so parent directories come before their children
    sorted_entries = sorted(api_tree, key=lambda e: e["path"])

    for entry in sorted_entries:
        path: str = entry["path"]
        entry_type = entry.get("type", "blob")

        # If we have a base_path, only include entries under it
        if base_path:
            if not path.startswith(base_path + "/") and path != base_path:
                continue
            # Adjust display path relative to base
            display_path = path[len(base_path) + 1:] if path != base_path else ""
            if not display_path:
                continue
        else:
            display_path = path

        parts = display_path.split("/")
        name = parts[-1]

        # Ensure all parent directories exist
        current_path = ""
        parent_node = root
        for i, part in enumerate(parts[:-1]):
            current_path = "/".join(parts[: i + 1])
            full_path = f"{base_path}/{current_path}" if base_path else current_path
            if current_path not in node_map:
                dir_node = TreeNode(
                    name=part,
                    path=full_path,
                    node_type=NodeType.DIRECTORY,
                )
                node_map[current_path] = dir_node
                parent_node.children.append(dir_node)
            parent_node = node_map[current_path]

        # Create the node itself
        node_type = NodeType.DIRECTORY if entry_type == "tree" else NodeType.FILE
        node = TreeNode(
            name=name,
            path=path,
            node_type=node_type,
            size=entry.get("size", 0) or 0,
            sha=entry.get("sha", ""),
        )

        # Avoid duplicating directory nodes already created as parents
        if display_path in node_map:
            existing = node_map[display_path]
            existing.size = node.size
            existing.sha = node.sha
            continue

        node_map[display_path] = node
        parent_node.children.append(node)

    root.sort_children()
    return root


def select_all(root: TreeNode) -> None:
    """Select all nodes in the tree."""
    root._set_selection_recursive(SelectionState.SELECTED)


def deselect_all(root: TreeNode) -> None:
    """Deselect all nodes in the tree."""
    root._set_selection_recursive(SelectionState.UNSELECTED)


def format_size(size_bytes: int) -> str:
    """Format file size in human-readable format."""
    if size_bytes == 0:
        return ""
    for unit in ("B", "KB", "MB", "GB"):
        if size_bytes < 1024:
            return f"{size_bytes:.0f}{unit}" if unit == "B" else f"{size_bytes:.1f}{unit}"
        size_bytes /= 1024
    return f"{size_bytes:.1f}TB"
