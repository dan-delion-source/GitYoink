# GitYoink 🎯

**Terminal-based selective GitHub repository downloader.**

Browse any GitHub repo interactively, pick only the files you need, and download them — all from your terminal.

![Python 3.10+](https://img.shields.io/badge/python-3.10+-blue)

---
## Video Demo
<details>

  [Watch Video](https://github.com/user-attachments/assets/1303561a-36fe-4482-8613-fc49f5e55c93)

</details>

---

## ✨ Features

- 🔗 **Paste any GitHub URL** — public repos work instantly, private repos with `GITHUB_TOKEN`
- 🌲 **Interactive tree browser** — expand/collapse directories, visual file icons
- ☑️ **Selective download** — check individual files or entire folders
- 🔍 **Search** — filter the tree by filename in real-time
- 👁️ **File preview** — view file content without downloading
- ⚡ **Concurrent downloads** — fast parallel fetching with progress tracking
- 📁 **Preserves structure** — downloaded files maintain their folder hierarchy
- 🖥️ **Cross-Platform** — Native support for Linux, macOS, and Windows.

---

## 📦 Installation

GitYoink comes with a robust installer that creates an isolated virtual environment and generates desktop shortcuts so you can launch it like a native app.

```bash
# Clone the repository
git clone https://github.com/dan-delion-source/GitYoink.git
cd GitYoink

# Run the interactive installer
python3 install.py
```

The installer will:
1. Create an isolated virtual environment.
2. Add a `gityoink` executable to your `~/.local/bin` (or AppData on Windows).
3. Generate a Desktop shortcut (a `.desktop` for Linux, `.command` for macOS, `.bat` for Windows) allowing you to pop open the TUI with a single double-click.

### Uninstalling
```bash
python3 install.py --uninstall
```

*(Alternatively, you can just run `pip install .` inside the folder to install it globally).*

---

## 🚀 Usage

```bash
# Launch the TUI
gityoink
```
Or simply double-click the GitYoink icon on your Desktop!

Then:
1. Paste a GitHub repo URL (e.g. `https://github.com/textualize/textual`)
2. Press **Enter** to fetch the file tree
3. Browse and select files
4. Press **Ctrl+D** to download selected files

### GitHub Token (Optional)

For private repos or to avoid rate limits, set your token:

```bash
export GITHUB_TOKEN=ghp_your_token_here
gityoink
```

---

## ⌨️ Keyboard Controls

| Key | Action |
|---|---|
| `↑ ↓` | Navigate tree items |
| `← →` | Collapse / Expand directories |
| `Tab` | Toggle selection on current item |
| `Ctrl+S` | Select all / Deselect all |
| `Ctrl+D` | Download selected files |
| `/` | Open search filter |
| `p` | Preview file content |
| `Esc` | Go back / Close panel |
| `q` | Quit |

---

## License

MIT
