"""Container system plugin for interacting with a persistent Docker container."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

from plugins.base import PluginSpec, ToolSpec
import tools

CONTAINER_NAME = os.environ.get("PLUGIN_CONTAINER_NAME", "copilot-workspace-container")
IMAGE = os.environ.get("PLUGIN_CONTAINER_IMAGE", "python:3.12-slim")
CONTAINER_WORKSPACE = "/workspace"

# Bind-mount source for the sandbox container. It must be a path the *host* Docker
# daemon understands. When the backend itself runs in a container (the sibling-
# container setup via the mounted docker socket), `tools.WORKSPACE` is the
# backend-internal mount path (`/workspace`), NOT a host path — so HOST_WORKSPACE_DIR
# must carry the real host path of the workspace. Run locally, `tools.WORKSPACE` is
# already the host path, so the fallback is correct.
HOST_WORKSPACE = os.environ.get("HOST_WORKSPACE_DIR") or str(tools.WORKSPACE)

# Sandbox resource/isolation limits (hardening). All overridable via env. These
# apply at container *creation*; an already-running container keeps the limits it
# was created with, so change one of these and recreate the container to re-apply.
_MEMORY = os.environ.get("PLUGIN_CONTAINER_MEMORY", "2g")
_CPUS = os.environ.get("PLUGIN_CONTAINER_CPUS", "2")
_PIDS_LIMIT = os.environ.get("PLUGIN_CONTAINER_PIDS_LIMIT", "512")
# Default keeps networking on so the agent can `pip install`; set to "none" to
# fully isolate the sandbox from the network.
_NETWORK = os.environ.get("PLUGIN_CONTAINER_NETWORK", "bridge")

INSTRUCTIONS = f"""Container plugin:
- Execute commands and manage files in a persistent Docker container ({CONTAINER_NAME}).
- The container bind-mounts the app workspace at `{CONTAINER_WORKSPACE}` — files you
  create there (plots, outputs) are visible to the workspace display tools.
- The sandbox has resource limits ({_MEMORY} memory, {_CPUS} CPUs) and runs with
  dropped capabilities; network access may be restricted.
- Use `run_command` to execute shell commands.
- Use `read_container_file` and `write_container_file` for file operations inside the container.
- All paths are relative to `{CONTAINER_WORKSPACE}` unless absolute.
"""


def _container_workspace_path(path: str) -> str:
    candidate = Path(path)
    if candidate.is_absolute():
        try:
            remapped = tools.remap_into_workspace(candidate)
        except ValueError:
            return str(candidate)
        rel = remapped.relative_to(tools.WORKSPACE)
        return str(Path(CONTAINER_WORKSPACE) / rel)
    return str(Path(CONTAINER_WORKSPACE) / path.lstrip("/"))

def _ensure_container():
    """Ensure the container is running."""
    try:
        # Check if container exists
        result = subprocess.run(
            ["docker", "inspect", CONTAINER_NAME],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            # Create and start container
            subprocess.run([
                "docker", "run", "-d",
                "--name", CONTAINER_NAME,
                "-v", f"{HOST_WORKSPACE}:{CONTAINER_WORKSPACE}",
                "-w", CONTAINER_WORKSPACE,
                "--memory", _MEMORY,
                "--cpus", _CPUS,
                "--pids-limit", _PIDS_LIMIT,
                "--network", _NETWORK,
                "--security-opt", "no-new-privileges",
                "--cap-drop", "ALL",
                IMAGE,
                "tail", "-f", "/dev/null"
            ], check=True)
        else:
            # Check if it's running
            status = subprocess.run(
                ["docker", "inspect", "-f", "{{.State.Running}}", CONTAINER_NAME],
                capture_output=True,
                text=True,
                check=True
            ).stdout.strip()
            if status != "true":
                subprocess.run(["docker", "start", CONTAINER_NAME], check=True)
    except Exception as e:
        return {"error": f"Failed to ensure container state: {e}"}
    return None

def run_command(command: str, timeout: int = 30) -> dict[str, Any]:
    """Run a shell command inside the container."""
    err = _ensure_container()
    if err: return err
    
    try:
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "sh", "-c", command],
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False
        )
        return {
            "stdout": result.stdout,
            "stderr": result.stderr,
            "exit_code": result.returncode
        }
    except subprocess.TimeoutExpired:
        return {"error": f"Command timed out after {timeout} seconds"}
    except Exception as e:
        return {"error": f"Failed to run command: {e}"}

def read_container_file(path: str) -> dict[str, Any]:
    """Read a file from the container."""
    err = _ensure_container()
    if err: return err
    
    try:
        target = _container_workspace_path(path)
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "cat", target],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            return {"error": f"Failed to read file: {result.stderr}"}
        return {"content": result.stdout, "path": target}
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

def write_container_file(path: str, content: str) -> dict[str, Any]:
    """Write a file to the container."""
    err = _ensure_container()
    if err: return err
    
    try:
        target = _container_workspace_path(path)
        # Use a temporary file to pipe content to docker cp or use sh -c 'cat > path'
        # Sh -c 'cat > path' is simpler for text
        process = subprocess.Popen(
            [
                "docker",
                "exec",
                "-i",
                CONTAINER_NAME,
                "sh",
                "-c",
                f"mkdir -p {sh_quote(str(Path(target).parent))} && cat > {sh_quote(target)}",
            ],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=content)
        if process.returncode != 0:
            return {"error": f"Failed to write file: {stderr}"}
        return {"path": target, "status": "success"}
    except Exception as e:
        return {"error": f"Failed to write file: {e}"}


def sh_quote(value: str) -> str:
    return "'" + value.replace("'", "'\"'\"'") + "'"

def get_plugin() -> PluginSpec:
    return PluginSpec(
        id="core.container",
        name="Container System",
        type="core",
        description="Run shell commands and read/write files inside the container.",
        instructions=INSTRUCTIONS,
        tools=[
            ToolSpec("run_command", run_command),
            ToolSpec("read_container_file", read_container_file),
            ToolSpec("write_container_file", write_container_file),
        ],
    )
