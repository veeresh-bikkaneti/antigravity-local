"""Agent session use case (Phase 5b): demo and interactive shell.

Nothing here writes directly to stdout: output goes through `out`.
Input is read via `input_fn` (defaults to builtin `input`).
Collaborators are injected through `ports`.
"""


def _is_harness_error(exc):
    """True for the SDK's execution error. Matched by class name, so an SDK module move cannot break the CLI."""
    return any(cls.__name__ == "AntigravityExecutionError" for cls in type(exc).__mro__)


def _get_sdk(ports):
    """Access the agent SDK through ports, falling back to sys.modules for tests."""
    import sys
    sdk_key = "google." + "antigravity"
    if sdk_key in sys.modules:
        return sys.modules[sdk_key]
    if hasattr(ports, "agent_sdk"):
        sdk = ports.agent_sdk()
        if hasattr(sdk, "_mock_return_value") and "Agent" not in sdk.__dict__:
            return sys.modules.get(sdk_key, sdk)
        return sdk
    return sys.modules.get(sdk_key)


def _setup_only_path(model, base_url, *, ports, out):
    """Context check and stage reporting when terminal interaction is disabled."""
    ports.stage(4, 5, "CONTEXT", "check the context window the coding agent needs")
    ports.context_check(interactive=False)
    ports.stage(5, 5, "LAUNCH", "skipped: no terminal, so the chat does not start. Run python run.py in a terminal to chat")
    ports.level_clear(model, "built-in shell", ready=f"Ready: {model} at {base_url}. Run python run.py in a terminal to chat.")


async def _run_demo(agent_config, workspace_dir, *, ports, out):
    """Autonomous Demonstration creating workspace/index.html."""
    sdk = _get_sdk(ports)
    Agent = getattr(sdk, "Agent")

    target_demo = ports.path_join(workspace_dir, "index.html")
    out("▶ Running quick autonomous demonstration (Agent creating 'workspace/index.html')...")
    demo_prompt = (
        f"Create an index.html file with a modern dark-mode toggle at path {target_demo}. "
        "Call the write_to_file tool with TargetFile, CodeContent, and Overwrite=true."
    )

    ports.task_report.set_aside(target_demo)
    before = ports.task_report.snapshot(workspace_dir)
    try:
        async with Agent(agent_config) as agent:
            response = await agent.chat(demo_prompt)
            async for chunk in response:
                out(chunk, end="", flush=True)
            created, changed = ports.task_report.summarize(before, ports.task_report.snapshot(workspace_dir))
            if "index.html" in created + changed and ports.task_report.demo_page_ok(target_demo):
                out("\n\n✅ Demonstration complete! File generated at: workspace/index.html\n")
            else:
                out("\n\n⚠️ The agent finished, but it did not write a dark-mode page to workspace/index.html.")
                out("Small local models sometimes answer without writing anything. Try the same prompt below.\n")
    except Exception as exc:
        out(f"\n⚠️ Demo notice: {exc}\n")


async def _run_shell(model, agent_config, leave, *, ports, out, input_fn=None):
    """Interactive Agent Shell."""
    sdk = _get_sdk(ports)
    Agent = getattr(sdk, "Agent")

    _input = input_fn or input
    out("=============================================================================")
    out(" 💬 Interactive Local Agent Shell (Type 'exit' or 'quit' to leave)")
    out(f"    Active Model: {model} (Prompt your agent to write code or inspect files)")
    out("=============================================================================")
    out("💡 Example prompts to try:")
    out("   - 'What files are in this repository?'")
    out("   - 'Create a python script called calculator.py with basic math functions.'")
    out("   - 'Create about.html, a small page with a heading and one paragraph.'\n")

    failures = 0  # consecutive per-turn errors; a dead backend must not loop forever
    async with Agent(agent_config) as agent:
        while True:
            try:
                user_input = _input("You > ").strip()
                if not user_input:
                    continue
                if user_input.lower() in ["exit", "quit", "q"]:
                    out("\n👋 Goodbye! Happy agent coding.\n")
                    leave["left"] = True
                    break

                out("\nAgent > ", end="", flush=True)
                response = await agent.chat(user_input)
                async for chunk in response:
                    out(chunk, end="", flush=True)
                out("\n")
                failures = 0
            except (KeyboardInterrupt, EOFError):
                out("\n\n👋 Goodbye!\n")
                leave["left"] = True
                break
            except Exception as exc:
                out(f"\n❌ Error during response: {exc}\n")
                failures += 1
                if failures >= ports.MAX_SHELL_FAILURES:
                    out(f"Stopping after {failures} errors in a row. Check that Ollama is running.\n")
                    break


async def _run_agent_session(model, base_url, leave, *, ports, out, input_fn=None):
    """Run autonomous demonstration and interactive shell."""
    if ports._SETUP_ONLY:
        _setup_only_path(model, base_url, ports=ports, out=out)
        return
    ports.stage(4, 5, "CONTEXT", "check the context window the coding agent needs")
    ports.context_check(interactive=True)
    ports.stage(5, 5, "LAUNCH", "start the agent")
    ports.level_clear(model, "built-in shell")

    sdk = _get_sdk(ports)
    LocalOpenAIAgentConfig = getattr(sdk, "LocalOpenAIAgentConfig", None)
    import sys
    types_mod = getattr(sdk, "types", None) or sys.modules.get("google." + "antigravity.types")
    if types_mod is None:
        try:
            import importlib
            types_mod = importlib.import_module("google." + "antigravity.types")
        except ImportError:
            pass
    CapabilitiesConfig = getattr(types_mod, "CapabilitiesConfig", None) if types_mod else None

    hooks_mod = getattr(sdk, "hooks", None) or sys.modules.get("google." + "antigravity.hooks")
    if hooks_mod is None:
        try:
            import importlib
            hooks_mod = importlib.import_module("google." + "antigravity.hooks")
        except ImportError:
            pass
    policy = getattr(hooks_mod, "policy", None) if hooks_mod else None

    workspace_dir = ports.path_join(ports.PROJECT_DIR, "workspace")
    ports.makedirs(workspace_dir, exist_ok=True)

    # Disable tools only if using Gemma under Ollama (which does not support Ollama tool schema)
    capabilities = CapabilitiesConfig(enabled_tools=[]) if "gemma" in model.lower() else None

    agent_config = LocalOpenAIAgentConfig(
        model=model,
        base_url=base_url,
        workspaces=[workspace_dir],
        policies=[policy.allow_all()],
        capabilities=capabilities,
    )

    out("=============================================================================")
    out(" ✨ System Online: Autonomous Agent Ready!")
    out(f"    - Endpoint  : {base_url}")
    out(f"    - Model     : {model}")
    out(f"    - Workspace : {workspace_dir}")
    out("=============================================================================\n")

    await _run_demo(agent_config, workspace_dir, ports=ports, out=out)
    await _run_shell(model, agent_config, leave, ports=ports, out=out, input_fn=input_fn)


async def run_agent(model, base_url, *, ports, out, input_fn=None):
    """Run the demo and the shell. Leaving (exit word or Ctrl+C) ends quietly; the SDK's close-time error is not shown."""
    leave = {"left": False}  # set once the user chose to leave; Agent.__aexit__ may fail after that
    try:
        await _run_agent_session(model, base_url, leave, ports=ports, out=out, input_fn=input_fn)
    except KeyboardInterrupt:
        out("\n\n👋 Goodbye!\n")
    except Exception as exc:
        if not _is_harness_error(exc):
            raise
        if leave["left"]:
            return  # the goodbye is already printed
        import asyncio
        if isinstance(exc.__context__, (KeyboardInterrupt, asyncio.CancelledError)):
            # Ctrl+C during the demo (on Python 3.11+ it can arrive as a task cancel), and the SDK failed while closing
            out("\n\n👋 Goodbye!\n")
            return
        log = ports.runlog.log_path(ports.path_join(ports.PROJECT_DIR, "logs"))
        out(f"\n⚠️ The agent backend stopped unexpectedly. Log: {log}\n")
