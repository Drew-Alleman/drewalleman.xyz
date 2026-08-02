#!/usr/bin/env python3
"""
Convert Obsidian-style image embeds to Jekyll-style Markdown image links.

    ![[Pasted image 20260726163400.png]]
        ->
    ![Showcase](/assets/images/Pasted image 20260726163400.png)

Also handles the Obsidian pipe syntax, using the text after the pipe as alt text:

    ![[diagram.png|Architecture]]
        ->
    ![Architecture](/assets/images/diagram.png)

By default it runs in "preview" mode: it shows you every proposed change and
asks for approval (per file) before writing anything. Nothing is modified
unless you type 'y'.
"""

import argparse
import re
import sys
from pathlib import Path

# Matches ![[ filename (optional |alt) ]]
EMBED_RE = re.compile(r"!\[\[\s*([^\]|]+?)\s*(?:\|\s*([^\]]*?)\s*)?\]\]")

DEFAULT_ALT = "Showcase"
ASSET_PREFIX = "/assets/images/"


def convert_line(text: str):
    """Return (new_text, num_replacements) for a string."""
    count = 0

    def repl(m):
        nonlocal count
        count += 1
        filename = m.group(1).strip()
        alt = (m.group(2) or "").strip() or DEFAULT_ALT
        return f"![{alt}]({ASSET_PREFIX}{filename})"

    return EMBED_RE.sub(repl, text), count


def preview_changes(path: Path, original: str, updated: str) -> int:
    """Print a line-by-line diff of only the changed lines. Returns change count."""
    changed = 0
    orig_lines = original.splitlines()
    new_lines = updated.splitlines()
    print(f"\n=== {path} ===")
    for i, (o, n) in enumerate(zip(orig_lines, new_lines), start=1):
        if o != n:
            changed += 1
            print(f"  line {i}:")
            print(f"    - {o}")
            print(f"    + {n}")
    return changed


def prompt_yes_no(question: str, assume_yes: bool) -> bool:
    if assume_yes:
        print(f"{question} [auto-yes]")
        return True
    try:
        answer = input(f"{question} [y/N]: ").strip().lower()
    except EOFError:
        return False
    return answer in ("y", "yes")


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("path", nargs="?", default=".",
                        help="File or directory to process (default: current directory)")
    parser.add_argument("--glob", default="*.md",
                        help="Glob pattern when a directory is given (default: *.md)")
    parser.add_argument("--recursive", "-r", action="store_true",
                        help="Recurse into subdirectories")
    parser.add_argument("--yes", "-y", action="store_true",
                        help="Skip prompts and apply all changes (use with care)")
    args = parser.parse_args()

    root = Path(args.path)
    if root.is_file():
        files = [root]
    elif root.is_dir():
        pattern = ("**/" + args.glob) if args.recursive else args.glob
        files = sorted(root.glob(pattern))
    else:
        print(f"Path not found: {root}", file=sys.stderr)
        sys.exit(1)

    if not files:
        print("No matching files found.")
        return

    total_files_changed = 0
    total_replacements = 0

    for path in files:
        try:
            original = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError) as e:
            print(f"Skipping {path}: {e}", file=sys.stderr)
            continue

        updated, count = convert_line(original)
        if count == 0:
            continue  # nothing to do in this file

        preview_changes(path, original, updated)
        print(f"  ({count} replacement{'s' if count != 1 else ''} in this file)")

        if prompt_yes_no(f"Apply changes to {path.name}?", args.yes):
            path.write_text(updated, encoding="utf-8")
            print(f"  ✓ written")
            total_files_changed += 1
            total_replacements += count
        else:
            print("  skipped")

    print(f"\nDone. {total_replacements} replacement(s) across "
          f"{total_files_changed} file(s).")


if __name__ == "__main__":
    main()