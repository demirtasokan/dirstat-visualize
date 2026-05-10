# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Running the tool

```bash
# Install dependency
pip install rich

# Basic usage (direct subdirectories only)
python dirstat.py [directory]

# Recursive mode (scans subdirectories depth-first)
python dirstat.py -r [directory]
```

## Architecture

The entire tool is a single-file CLI in `dirstat.py`. The data pipeline is one-directional:

1. **`collect_tree()`** — walks the filesystem and builds a node list. Each node is a tuple: `(Path, file_count, mtime|None, top_exts, children)`. This tuple is the sole data structure passed through the rest of the program.
2. **`find_max()`** — traverses the node tree to find the maximum file count across all nodes, used to normalize bar widths proportionally.
3. **`render_tree()`** — recursively renders nodes using `rich.text.Text`, coloring bars with `freshness_style()` and labeling age with `age_label()`.

Key helpers:
- `freshness_style(mtime)` — Rich color string derived from age thresholds `_24H`, `_30D`, `_1Y`
- `age_label(mtime)` — Turkish human-readable string (e.g. `"3g once"`, `"2ay once"`)
- `latest_mtime(path, recursive)` — max mtime among all files in a directory
- `top_extensions(path, recursive)` — top-`TOP_N` extensions with percentage share

Module-level constants (`BAR_CHAR`, `MAX_BAR_WIDTH`, `TOP_N`, `NOW`) control all visual output.

## Language note

All UI strings, comments, and labels are intentionally written in Turkish. Keep this consistent when adding any output text.
