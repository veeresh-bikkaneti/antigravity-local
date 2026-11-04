"""Describe what a --task run changed in the workspace. Standard library only."""
import os


def snapshot(workspace_dir):
    """Map each file's relative path to (mtime_ns, size)."""
    files = {}
    for root, _, names in os.walk(workspace_dir):
        for name in names:
            path = os.path.join(root, name)
            stat = os.stat(path)
            files[os.path.relpath(path, workspace_dir)] = (stat.st_mtime_ns, stat.st_size)
    return files


def summarize(before, after):
    """Return (created, changed) relative paths, sorted."""
    created = sorted(f for f in after if f not in before)
    changed = sorted(f for f in after if f in before and after[f] != before[f])
    return created, changed


def render(workspace_dir, files, created, changed):
    """Lines to print after a task. Say 'completed' only when a file was created or changed."""
    wrote = bool(created or changed)
    head = (f"✅ Task completed. Created {len(created)}, changed {len(changed)}." if wrote
            else "⚠️ The agent finished, but it created or changed no files.")
    lines = ["=" * 76, head, f"Workspace files ({len(files)}):"]
    lines += [f"   \U0001F4C1 {os.path.join(workspace_dir, f)}" for f in files]
    if not wrote:
        lines += ["Small local models sometimes answer without writing anything.",
                  "If you expected a file, run the same command again, or name the file in your task."]
    lines.append("=" * 76)
    return lines
