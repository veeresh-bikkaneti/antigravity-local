"""Environment bootstrap use case (Phase 6e): check venv and bootstrap if needed.

agl.app must NOT import agl.platform or subprocess!
All system collaborators (process, stage, paths) are injected through `ports`.
"""
import os
import sys
import shutil


def is_in_venv():
    return sys.prefix != sys.base_prefix


def bootstrap_venv(*, ports, out=print):
    """Create virtual environment and install requirements if not inside one."""
    ports.stage(1, 5, "ENVIRONMENT", "check the Python environment, then find Ollama")
    healthy = True
    project_dir = getattr(ports, "PROJECT_DIR", os.getcwd())
    venv_dir = getattr(ports, "VENV_DIR", os.path.join(project_dir, "venv"))
    venv_python = getattr(
        ports,
        "VENV_PYTHON",
        os.path.join(venv_dir, "Scripts" if ports.IS_WIN else "bin", "python.exe" if ports.IS_WIN else "python"),
    )

    if not os.path.exists(venv_dir) or not os.path.exists(venv_python):
        healthy = False
        out(f"       Creating virtual environment at: {venv_dir}")
        ports.process.check_call([sys.executable, "-m", "venv", venv_dir])

    # Copy .env.example to .env if missing
    env_file = os.path.join(project_dir, ".env")
    env_example = os.path.join(project_dir, ".env.example")
    if not os.path.exists(env_file) and os.path.exists(env_example):
        healthy = False
        out("       Generating default .env from .env.example...")
        shutil.copyfile(env_example, env_file)

    # Check if google-antigravity is installed in venv
    try:
        ports.process.check_call(
            [venv_python, "-c", "import google.antigravity"],
            stdout=ports.process.DEVNULL,
            stderr=ports.process.DEVNULL,
        )
        out(
            "       Python environment ready (google-antigravity installed)"
            if healthy
            else "       Dependencies verified: 'google-antigravity' is ready."
        )
    except ports.process.CalledProcessError:
        healthy = False
        out("       Installing dependencies from requirements.txt (first run only)...")
        req_file = os.path.join(project_dir, "requirements.txt")
        ports.process.check_call([venv_python, "-m", "pip", "install", "--upgrade", "pip", "--quiet"])
        ports.process.check_call([venv_python, "-m", "pip", "install", "-r", req_file, "--quiet"])
        out("       Dependencies successfully installed.")

    # Relaunch script using the venv python
    if not healthy:
        out("       Switching execution to managed environment...")
    sys.stdout.flush()
    sys.stderr.flush()
    script_path = getattr(ports, "script_path", None) or os.path.join(project_dir, "run.py")
    header_flag = getattr(ports, "HEADER_FLAG", "ANTIGRAVITY_HEADER_PRINTED")
    os.environ[header_flag] = "1"
    if ports.IS_WIN:
        try:
            sys.exit(ports.process.call([venv_python, script_path] + sys.argv[1:]))
        except KeyboardInterrupt:
            sys.exit(0)
    else:
        os.execv(venv_python, [venv_python, script_path] + sys.argv[1:])
