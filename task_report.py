"""Describe what a --task run changed in the workspace. Standard library only."""
import hashlib
import os


HASH_CAP = 64 * 1024 * 1024  # ponytail: bigger files fall back to (size, mtime); fine for agent-written text


def snapshot(workspace_dir):
    """Map each file's relative path to a fingerprint: (size, sha256). Touch-only edits don't change it."""
    files = {}
    for root, _, names in os.walk(workspace_dir):
        for name in names:
            path = os.path.join(root, name)
            try:
                stat = os.stat(path)
                if stat.st_size <= HASH_CAP:
                    with open(path, "rb") as f:
                        fp = (stat.st_size, hashlib.sha256(f.read()).hexdigest())
                else:
                    fp = (stat.st_size, stat.st_mtime_ns)
            except OSError:
                continue  # vanished or unreadable mid-walk
            files[os.path.relpath(path, workspace_dir)] = fp
    return files


def summarize(before, after):
    """Return (created, changed) relative paths, sorted."""
    created = sorted(f for f in after if f not in before)
    changed = sorted(f for f in after if f in before and after[f] != before[f])
    return created, changed


def deleted(before, after):
    """Relative paths present before and gone after, sorted."""
    return sorted(f for f in before if f not in after)


def render(workspace_dir, files, created, changed, removed=()):
    """Lines to print after a task. Say 'completed' only when a file was created or changed."""
    wrote = bool(created or changed or removed)
    head = (f"✅ Task completed. Created {len(created)}, changed {len(changed)}." if wrote
            else "⚠️ The agent finished, but it created or changed no files.")
    lines = ["=" * 76, head, f"Workspace files ({len(files)}):"]
    if removed:
        lines.append(f"Deleted {len(removed)}: " + ", ".join(removed))
    lines += [f"   \U0001F4C1 {os.path.join(workspace_dir, f)}" for f in files]
    if not wrote:
        lines += ["Small local models sometimes answer without writing anything.",
                  "If you expected a file, run the same command again, or name the file in your task."]
    lines.append("=" * 76)
    return lines
