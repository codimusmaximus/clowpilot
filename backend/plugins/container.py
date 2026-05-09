"""Container system plugin for interacting with a persistent Docker container."""

from __future__ import annotations

import os
import subprocess
from typing import Any

from plugins.base import PluginSpec, ToolSpec

CONTAINER_NAME = os.environ.get("PLUGIN_CONTAINER_NAME", "copilot-workspace-container")
WORKSPACE_VOLUME = os.environ.get("PLUGIN_CONTAINER_VOLUME", "copilot-workspace-data")
IMAGE = os.environ.get("PLUGIN_CONTAINER_IMAGE", "python:3.12-slim")

INSTRUCTIONS = f"""Container plugin:
- Execute commands and manage files in a persistent Docker container ({CONTAINER_NAME}).
- The container has a persistent volume mounted at `/workspace`.
- Use `run_command` to execute shell commands.
- Use `read_container_file` and `write_container_file` for file operations inside the container.
- All paths are relative to `/workspace` unless absolute.
"""

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
                "-v", f"{WORKSPACE_VOLUME}:/workspace",
                "-w", "/workspace",
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
        result = subprocess.run(
            ["docker", "exec", CONTAINER_NAME, "cat", path],
            capture_output=True,
            text=True,
            check=False
        )
        if result.returncode != 0:
            return {"error": f"Failed to read file: {result.stderr}"}
        return {"content": result.stdout, "path": path}
    except Exception as e:
        return {"error": f"Failed to read file: {e}"}

def write_container_file(path: str, content: str) -> dict[str, Any]:
    """Write a file to the container."""
    err = _ensure_container()
    if err: return err
    
    try:
        # Use a temporary file to pipe content to docker cp or use sh -c 'cat > path'
        # Sh -c 'cat > path' is simpler for text
        process = subprocess.Popen(
            ["docker", "exec", "-i", CONTAINER_NAME, "sh", "-c", f"cat > {path}"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        stdout, stderr = process.communicate(input=content)
        if process.returncode != 0:
            return {"error": f"Failed to write file: {stderr}"}
        return {"path": path, "status": "success"}
    except Exception as e:
        return {"error": f"Failed to write file: {e}"}

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
