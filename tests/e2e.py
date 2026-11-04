#!/usr/bin/env python3
"""Real end-to-end check of both delivery paths. Stdlib only.

  python tests/e2e.py local    # run.py --serve in a fresh clone-like env (own venv), free port
  python tests/e2e.py docker   # build image, run two containers on random host ports

Same HTTP assertions for both, so "works locally" and "works in the image" mean the same thing.
"""
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
IMAGE = f"antigravity-local:e2e-{os.getpid()}"  # unique per run, removed in docker()'s finally


def get(url):
    try:
        with urllib.request.urlopen(url, timeout=10) as r:
            return r.status, r.read()
    except urllib.error.HTTPError as e:
        body = e.read(); e.close()
        return e.code, body


def check(base):
    code, body = get(base + "/healthz")
    assert code == 200 and json.loads(body)["status"] == "ok", (code, body)
    docs = json.loads(body)["documents"]
    assert docs > 5, f"index looks empty: {docs} docs"
    code, body = get(base + "/api/search?q=hardware+offloading+16GB+VRAM&limit=3")
    res = json.loads(body)["results"]
    assert code == 200 and res, "search returned nothing"
    assert any("hardware" in r["path"].lower() or "hardware" in r["content"].lower() for r in res), res[:1]
    assert get(base + "/api/search?q=")[0] == 400
    assert get(base + "/diagrams/system-topology.html")[0] == 200
    code, body = get(base + "/diagrams/..%2f..%2fREADME.md")
    assert code in (400, 404) and b"Antigravity Agent" not in body
    assert get(base + "/")[0] == 200
    print(f"   [ok] healthz ({docs} docs), search, diagram, bad-input and traversal checks pass")


def wait_url(proc, pattern, timeout):
    end = time.time() + timeout
    while time.time() < end:
        line = proc.stdout.readline()
        if not line:
            if proc.poll() is not None:
                raise RuntimeError("server exited early")
            continue
        print("   |", line.rstrip())
        m = re.search(pattern, line)
        if m:
            return m.group(1)
    raise TimeoutError("server never announced its URL")


def stop(p):
    """Stop a server we started, children included.

    Windows terminate() kills only the top process, which orphans the venv python that run.py
    spawns (and keeps its port and temp dir alive). taskkill /T kills the whole tree.
    """
    if sys.platform == "win32":
        subprocess.run(["taskkill", "/T", "/F", "/PID", str(p.pid)], capture_output=True)
    else:
        p.terminate()
    try:
        p.wait(10)
    except Exception:
        p.kill()


def local():
    work = Path(tempfile.mkdtemp(prefix="ag-e2e-"))
    dest = work / "repo"
    # Copy the working tree (no venv/db) so first-run bootstrap is exercised for real.
    shutil.copytree(ROOT, dest, ignore=shutil.ignore_patterns(
        "venv", ".venv", ".git", ".memory", ".agents", ".claude*", "node_modules", "__pycache__", ".ai-context"))
    print(f"[local] bootstrapping fresh copy at {dest}")
    procs, bases = [], []
    try:
        for i in range(2):  # two at once must land on two different free ports
            p = subprocess.Popen([sys.executable, "run.py", "--serve"], cwd=dest, text=True,
                                 stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
            procs.append(p)
            bases.append(wait_url(p, r"(http://127\.0\.0\.1:\d+)", 600 if i == 0 else 120))
        assert bases[0] != bases[1], bases
        for b in bases:
            print(f"[local] checking {b}"); check(b)
    finally:
        for p in procs:
            stop(p)
        for attempt in range(5):  # Windows may need a moment to release files
            try:
                shutil.rmtree(work)
                break
            except OSError:
                if attempt == 4:
                    raise
                time.sleep(1)


def docker():
    run = lambda *a, **k: subprocess.run(a, check=True, capture_output=True, text=True, **k).stdout.strip()
    print("[docker] building image")
    subprocess.run(["docker", "build", "-q", "-t", IMAGE, str(ROOT)], check=True)
    ids = []
    try:
        for _ in range(2):  # random host ports, loopback only
            ids.append(run("docker", "run", "-d", "--rm", "-p", "127.0.0.1::8000", IMAGE))
        ports = [re.search(r":(\d+)\s*$", run("docker", "port", c, "8000").splitlines()[0]).group(1) for c in ids]
        assert ports[0] != ports[1], ports
        def wait_healthy(c, base):
            print(f"[docker] waiting for {base}")
            for _ in range(60):
                try:
                    status = run("docker", "inspect", "-f", "{{.State.Health.Status}}", c)
                except subprocess.CalledProcessError:
                    raise RuntimeError("container exited before it became healthy (--rm already removed it)")
                if status == "healthy":
                    return
                time.sleep(2)
            raise TimeoutError("container never became healthy: " + subprocess.run(
                ["docker", "logs", c], capture_output=True, text=True).stdout[-800:])

        for c, port in zip(ids, ports):
            base = f"http://127.0.0.1:{port}"
            wait_healthy(c, base)
            check(base)
        # Permission variants: an arbitrary user id (as some platforms force) and a read-only root filesystem.
        for label, extra in (("arbitrary user id", ["--user", "12345:12345"]),
                             ("read-only filesystem", ["--read-only", "--tmpfs", "/app/.memory"])):
            c = run("docker", "run", "-d", "--rm", "-p", "127.0.0.1::8000", *extra, IMAGE)
            ids.append(c)
            base = "http://127.0.0.1:" + re.search(r":(\d+)\s*$", run("docker", "port", c, "8000").splitlines()[0]).group(1)
            wait_healthy(c, base)
            check(base)
            print(f"   [ok] runs with {label}")
        user = run("docker", "exec", ids[0], "id", "-un")
        assert user == "app", f"container runs as {user}, expected non-root"
        print("   [ok] runs as non-root user 'app'; HEALTHCHECK reports healthy")
    finally:
        for c in ids:
            subprocess.run(["docker", "stop", "-t", "2", c], capture_output=True)  # --rm deletes the container
        subprocess.run(["docker", "rmi", "-f", IMAGE], capture_output=True)  # leave no image behind


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) > 1 else ""
    {"local": local, "docker": docker}.get(mode, lambda: sys.exit(__doc__))()
    print(f"E2E {mode}: PASS")
