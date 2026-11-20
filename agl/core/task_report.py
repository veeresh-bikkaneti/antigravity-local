"""The pure half of "describe what a --task run changed in the workspace".

The parts that touch the disk (snapshot, set_aside, demo_page_ok) stayed at the root
task_report.py until Phase 4. Standard library only.
"""
import posixpath


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
    head = (f"✅ Task completed. Created {len(created)}, changed {len(changed)}." + (f" Deleted {len(removed)}." if removed else "") if wrote
            else "⚠️ The agent finished, but it created or changed no files.")
    lines = ["=" * 76, head, f"Workspace files ({len(files)}):"]
    if removed:
        lines.append(f"Deleted {len(removed)}: " + ", ".join(removed))
    lines += [f"   \U0001F4C1 {posixpath.join(workspace_dir, f)}" for f in files]
    if not wrote:
        lines += ["Small local models sometimes answer without writing anything.",
                  "If you expected a file, run the same command again, or name the file in your task."]
    lines.append("=" * 76)
    return lines
