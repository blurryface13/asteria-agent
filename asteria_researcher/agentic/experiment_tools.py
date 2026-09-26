"""Opt-in Docker experiment scratchpad for the Coding Agent.

Never mounts the user's workspace, Docker socket, cloud credentials or host home
inside the untrusted container. This is a local executor, not a cloud service.
"""
from __future__ import annotations

import asyncio
import hashlib
import os
from pathlib import Path
import re
import shutil
import stat
from uuid import uuid4
from urllib.parse import urlsplit
from contextlib import contextmanager

import httpx


MAX_FILE = 256 * 1024
MAX_OUTPUT = 16000
MAX_CAPTURE = 2 * 1024 * 1024
IMAGE = "python:3.11-slim"


def _relative_path(value: str) -> Path:
    if (not isinstance(value, str) or not 1 <= len(value) <= 240 or
            not re.fullmatch(r"[A-Za-z0-9_./-]+", value) or
            value.startswith("/") or any(part in {"", ".", ".."} for part in value.split("/"))):
        raise ValueError("实验文件必须是安全的相对路径")
    return Path(value)


class DockerExperimentWorkspace:
    def __init__(self, root: Path, image: str = IMAGE, *, volume: str | None = None):
        if not shutil.which("docker"):
            raise RuntimeError("Docker CLI is unavailable; experiment execution is disabled")
        if not re.fullmatch(r"[A-Za-z0-9_.:/@-]+", image):
            raise ValueError("Invalid experiment image")
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.image = image
        if volume is not None and not re.fullmatch(r"[A-Za-z0-9_.-]+", volume):
            raise ValueError("Invalid experiment volume")
        self.volume = volume

    @contextmanager
    def _parent_fd(self, name: str, *, create: bool = False):
        """Traverse within scratch without following container-created symlinks."""
        parts = _relative_path(name).parts
        fd = os.open(self.root, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
        try:
            for part in parts[:-1]:
                if create:
                    try:
                        os.mkdir(part, 0o700, dir_fd=fd)
                    except FileExistsError:
                        pass
                try:
                    child = os.open(part, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW, dir_fd=fd)
                except OSError as error:
                    raise ValueError("实验路径不能经过符号链接或非目录节点") from error
                if create and self.volume:
                    os.fchown(child, 65534, 65534)
                os.close(fd)
                fd = child
            yield fd, parts[-1]
        finally:
            os.close(fd)

    def write(self, arguments: dict) -> dict:
        if set(arguments) != {"path", "content"}:
            raise ValueError("write_experiment_file requires path and content")
        content = arguments["content"]
        if not isinstance(content, str) or len(content.encode()) > MAX_FILE:
            raise ValueError("实验文件内容超过 256 KiB")
        with self._parent_fd(arguments["path"], create=True) as (parent, filename):
            fd = os.open(filename, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW,
                         0o600, dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError("实验目标必须是普通文件")
                if self.volume:
                    os.fchown(fd, 65534, 65534)
                with os.fdopen(fd, "w", encoding="utf-8", closefd=False) as file:
                    file.write(content)
            finally:
                os.close(fd)
        return {"status": "completed", "path": arguments["path"], "scope": "experiment_scratch_only",
                "sha256": hashlib.sha256(content.encode()).hexdigest()}

    def read(self, arguments: dict) -> dict:
        if set(arguments) != {"path"}:
            raise ValueError("read_experiment_file requires path")
        with self._parent_fd(arguments["path"]) as (parent, filename):
            fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
            try:
                if not stat.S_ISREG(os.fstat(fd).st_mode):
                    raise ValueError("实验目标必须是普通文件")
                if os.fstat(fd).st_size > MAX_FILE:
                    raise ValueError("实验文件超过读取上限")
                with os.fdopen(fd, "r", encoding="utf-8", closefd=False) as file:
                    content = file.read(MAX_FILE + 1)
            finally:
                os.close(fd)
        return {"status": "completed", "path": arguments["path"], "content": content}

    def files(self) -> list[dict]:
        found = []
        for path in sorted(self.root.rglob("*")):
            if path.is_symlink() or not path.is_file():
                continue
            name = path.relative_to(self.root).as_posix()
            try:
                with self._parent_fd(name) as (parent, filename):
                    fd = os.open(filename, os.O_RDONLY | os.O_NOFOLLOW, dir_fd=parent)
                    try:
                        size = os.fstat(fd).st_size
                        if not stat.S_ISREG(os.fstat(fd).st_mode):
                            continue
                        digest = hashlib.sha256(os.read(fd, MAX_FILE + 1)).hexdigest() if size <= MAX_FILE else None
                    finally:
                        os.close(fd)
            except (OSError, ValueError):
                continue  # A container may be concurrently changing its scratch files.
            found.append({"path": name, "size": size, "sha256": digest})
            if len(found) >= 80:
                break
        return found

    async def run(self, arguments: dict) -> dict:
        if set(arguments) - {"command", "timeout_seconds"}:
            raise ValueError("Unknown experiment execution parameter")
        command = arguments.get("command")
        timeout = arguments.get("timeout_seconds", 30)
        if not isinstance(command, str) or not 1 <= len(command) <= 1200 or "\0" in command:
            raise ValueError("Invalid experiment command")
        if type(timeout) is not int or not 1 <= timeout <= 120:
            raise ValueError("Experiment timeout must be 1–120 seconds")
        before = {item["path"]: (item["size"], item["sha256"]) for item in self.files()}
        name = "asteria-experiment-" + uuid4().hex
        flags = ["docker", "run", "--rm", "--pull", "never", "--name", name,
                 "--network", "none", "--read-only", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--pids-limit", "128",
                 "--memory", "1g", "--cpus", "1", "--ulimit", "fsize=67108864:67108864",
                 "--tmpfs", "/tmp:rw,nosuid,size=64m",
                 "--mount", (f"type=volume,src={self.volume},volume-subpath={self.root.name},dst=/work"
                             if self.volume else f"type=bind,src={self.root},dst=/work"),
                 "--workdir", "/work",
                 "--env", "HOME=/tmp", "--env", "PYTHONDONTWRITEBYTECODE=1"]
        if hasattr(os, "getuid"):
            uid, gid = (65534, 65534) if self.volume else (os.getuid(), os.getgid())
            flags += ["--user", f"{uid}:{gid}"]
        # Exit immediately on an unhandled failing command. Without -e, a
        # diagnostic suffix such as `python broken.py; echo EXIT=$?` makes the
        # overall shell return 0 and falsely labels a failed experiment green.
        flags += [self.image, "sh", "-ec", command]
        process = await asyncio.create_subprocess_exec(*flags, stdout=asyncio.subprocess.PIPE,
                                                        stderr=asyncio.subprocess.STDOUT)
        async def capture():
            chunks, size = [], 0
            while chunk := await process.stdout.read(8192):
                size += len(chunk)
                if size > MAX_CAPTURE:
                    raise ValueError("实验输出超过 2 MiB，已终止隔离容器")
                chunks.append(chunk)
            await process.wait()
            return b"".join(chunks)
        try:
            output = await asyncio.wait_for(capture(), timeout + 10)
        except (asyncio.TimeoutError, asyncio.CancelledError, ValueError):
            if process.returncode is None:
                process.kill()
            await process.wait()
            cleanup = await asyncio.create_subprocess_exec("docker", "rm", "-f", name,
                                                           stdout=asyncio.subprocess.DEVNULL,
                                                           stderr=asyncio.subprocess.DEVNULL)
            await cleanup.wait()
            raise
        if process.returncode == 125:
            raise RuntimeError("Docker sandbox failed to start; check the pinned image and Docker engine")
        artifacts = self.files()
        generated = [item for item in artifacts if before.get(item["path"]) != (item["size"], item["sha256"])]
        return {"status": "completed" if process.returncode == 0 else "failed",
                "execution_performed": True, "exit_code": process.returncode,
                "output": output.decode(errors="replace")[-MAX_OUTPUT:],
                "artifacts": artifacts, "generated_artifacts": generated,
                "workspace": str(self.root),
                "isolation": "docker_no_network_readonly_root_no_host_credentials"}


class RemoteExperimentWorkspace:
    """A Worker only sees this capability API; Docker privileges stay in broker."""

    def __init__(self, url: str, token: str):
        endpoint = urlsplit(url)
        if (endpoint.scheme != "http" or endpoint.hostname != "experiment-broker" or
                endpoint.port != 8090 or endpoint.path not in {"", "/"} or
                endpoint.query or endpoint.fragment or endpoint.username or endpoint.password or not token):
            raise ValueError("Experiment broker must use the internal Compose endpoint and a token")
        self.url, self.token, self.session = url.rstrip("/"), token, None

    async def _call(self, operation: str, arguments: dict):
        async with httpx.AsyncClient(timeout=150, trust_env=False) as client:
            headers = {"Authorization": "Bearer " + self.token}
            if self.session is None:
                response = await client.post(self.url + "/sessions", headers=headers)
                response.raise_for_status()
                self.session = response.json()["session_id"]
            response = await client.post(self.url + f"/sessions/{self.session}/{operation}",
                                         headers=headers, json=arguments)
            response.raise_for_status()
            return response.json()

    async def write(self, args):
        return await self._call("write", args)

    async def read(self, args):
        return await self._call("read", args)

    async def files(self, args):
        return await self._call("files", args)

    async def run(self, args):
        return await self._call("run", args)


def build_experiment_tools(root: Path) -> dict:
    mode = os.getenv("ASTERIA_EXPERIMENT_EXECUTOR")
    if mode == "broker":
        url = os.getenv("ASTERIA_EXPERIMENT_BROKER_URL", "")
        token = os.getenv("ASTERIA_EXPERIMENT_BROKER_TOKEN", "")
        if not url or not token:
            return {}
        workspace = RemoteExperimentWorkspace(url, token)
    elif mode == "local_docker" and shutil.which("docker"):
        workspace = DockerExperimentWorkspace(root, os.getenv("ASTERIA_EXPERIMENT_IMAGE", IMAGE))
    else:
        return {}

    async def write(args):
        result = workspace.write(args)
        return await result if asyncio.iscoroutine(result) else result

    async def read(args):
        result = workspace.read(args)
        return await result if asyncio.iscoroutine(result) else result

    async def files(args):
        if args:
            raise ValueError("list_experiment_files takes no arguments")
        result = workspace.files({}) if isinstance(workspace, RemoteExperimentWorkspace) else workspace.files()
        result = await result if asyncio.iscoroutine(result) else result
        return result if isinstance(result, dict) else {"status": "completed", "files": result}

    return {
        "write_experiment_file": ({"path": "relative experiment path", "content": "UTF-8 text"}, write),
        "read_experiment_file": ({"path": "relative experiment path"}, read),
        "list_experiment_files": ({}, files),
        "run_experiment_command": ({"command": "shell command inside isolated container",
                                     "timeout_seconds": "1–120; default 30"}, workspace.run),
    }
