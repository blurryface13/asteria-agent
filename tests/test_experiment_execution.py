"""Coding dispatch and isolated experiment execution contracts."""
import asyncio
import importlib.util
import json
import os
from pathlib import Path
import shutil
import sys
from types import SimpleNamespace

import pytest

from asteria_researcher.agentic.collaboration import Assignment, allocation_report, repair_implementation_ownership
from asteria_researcher.agentic.coding import run_coding
from asteria_researcher.agentic.experiment_tools import DockerExperimentWorkspace, RemoteExperimentWorkspace


def assignment(name, role, ids):
    return Assignment(name=name, role=role, objective=name, goal_ids=ids,
                      focus="独立调查", expected_output="可核查结果")


def test_misrouted_implementation_goal_moves_to_existing_coder():
    tasks = [assignment("paper", "researcher", ["g1", "c1"]),
             assignment("code", "coding", ["c2"])]
    fixed, repairs = repair_implementation_ownership(tasks, [
        {"id": "g1", "description": "文献依据"},
        {"id": "c1", "description": "运行实验"},
        {"id": "c2", "description": "修改脚本"}], True)
    assert fixed[0].goal_ids == ["g1"]
    assert fixed[1].goal_ids == ["c2", "c1"] or fixed[1].goal_ids == ["c1", "c2"]
    assert repairs[0]["goal_ids"] == ["c1"]
    assert allocation_report(fixed, ["g1", "c1", "c2"])["planned_coverage"] == 1
    assert tasks[0].goal_ids == ["g1", "c1"]  # original model trace unchanged


def test_misrouted_implementation_goal_creates_coder_when_room():
    tasks = [assignment("paper", "researcher", ["g1", "c1"])]
    fixed, _ = repair_implementation_ownership(tasks, [
        {"id": "g1", "description": "文献依据"},
        {"id": "c1", "description": "运行实验"}], True)
    assert [(t.role, t.goal_ids) for t in fixed] == [
        ("researcher", ["g1"]), ("coding", ["c1"])]


def test_scratch_paths_cannot_escape_or_follow_symlink(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/docker")
    workspace = DockerExperimentWorkspace(tmp_path / "scratch")
    assert workspace.write({"path": "src/demo.py", "content": "print(1)\n"})["scope"] == "experiment_scratch_only"
    assert workspace.read({"path": "src/demo.py"})["content"] == "print(1)\n"
    for name in ("../outside", "/etc/passwd", "a//b"):
        with pytest.raises(ValueError):
            workspace.write({"path": name, "content": "bad"})
    (workspace.root / "link").symlink_to(tmp_path, target_is_directory=True)
    with pytest.raises(ValueError):
        workspace.write({"path": "link/escape", "content": "bad"})


def test_remote_broker_address_is_exact():
    RemoteExperimentWorkspace("http://experiment-broker:8090", "token")
    for url in ("http://experiment-broker:8090.evil.test", "http://experiment-broker:8090@evil.test",
                "http://experiment-broker:8090/other", "https://experiment-broker:8090"):
        with pytest.raises(ValueError):
            RemoteExperimentWorkspace(url, "token")


def test_sandbox_invocation_has_isolation_and_artifact_proof(tmp_path, monkeypatch):
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/docker")
    workspace = DockerExperimentWorkspace(tmp_path / "scratch")
    invocations = []

    async def fake_subprocess(*args, **kwargs):
        invocations.append(args)
        (workspace.root / "result.txt").write_text("42")
        class Stream:
            reads = 0
            async def read(self, _):
                self.reads += 1
                return b"ok\n" if self.reads == 1 else b""
        async def wait():
            return 0
        return SimpleNamespace(stdout=Stream(), returncode=0, wait=wait)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_subprocess)
    result = asyncio.run(workspace.run({"command": "python demo.py", "timeout_seconds": 10}))
    args = invocations[0]
    for flag in ("--network", "none", "--read-only", "--cap-drop", "ALL",
                 "--security-opt", "no-new-privileges", "--pull", "never"):
        assert flag in args
    assert result["status"] == "completed"
    assert result["generated_artifacts"][0]["path"] == "result.txt"


def test_broker_requires_token_and_uses_private_session(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from asteria_researcher.agentic import experiment_tools
    monkeypatch.setitem(sys.modules, "experiment_tools", experiment_tools)
    monkeypatch.setenv("ASTERIA_EXPERIMENT_BROKER_TOKEN", "test-token")
    monkeypatch.setenv("ASTERIA_EXPERIMENT_VOLUME", "test-volume")
    monkeypatch.setenv("ASTERIA_EXPERIMENT_ROOT", str(tmp_path))
    monkeypatch.setattr(os, "chown", lambda *_: None)
    monkeypatch.setattr(os, "fchown", lambda *_: None)
    monkeypatch.setattr(shutil, "which", lambda _: "/usr/local/bin/docker")
    script = Path(__file__).parents[1] / "scripts" / "experiment-broker.py"
    spec = importlib.util.spec_from_file_location("test_experiment_broker", script)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    client = TestClient(module.app)
    assert client.post("/sessions").status_code == 401
    headers = {"Authorization": "Bearer test-token"}
    created = client.post("/sessions", headers=headers)
    assert created.status_code == 200
    session = created.json()["session_id"]
    assert client.post(f"/sessions/{session}/write", json={"path": "a.py", "content": "print(1)"}).status_code == 401
    assert client.post(f"/sessions/{session}/write", headers=headers,
                       json={"path": "a.py", "content": "print(1)"}).status_code == 200
    assert client.post(f"/sessions/{session}/read", headers=headers,
                       json={"path": "a.py"}).json()["content"] == "print(1)"
    module.sessions.clear()  # simulate broker process restart with persistent volume
    assert client.post(f"/sessions/{session}/read", headers=headers,
                       json={"path": "a.py"}).json()["content"] == "print(1)"


def test_execution_goal_cannot_finish_from_prose_or_failed_run():
    async def exercise():
        actions = [
            {"tool": "write_experiment_file", "arguments": {"path": "demo.py", "content": "print(1)"}},
            {"tool": "run_experiment_command", "arguments": {"command": "python demo.py"}},
            {"tool": "finish", "summary": "实验已完成", "outcome": "completed"},
        ]
        calls = iter(actions)
        async def model(_system, _context):
            return json.dumps({"purpose": "test", **next(calls)})
        async def emit(*args, **kwargs):
            pass
        async def write(_):
            return {"status": "completed", "scope": "experiment_scratch_only"}
        async def failed_run(_):
            return {"status": "failed", "execution_performed": True, "exit_code": 1}
        task = assignment("run", "coding", ["c1"])
        return await run_coding(task, model, {
            "write_experiment_file": ({}, write),
            "run_experiment_command": ({}, failed_run)},
            None, emit, max_turns=3,
            context={"goals": [{"id": "c1", "kind": "experiment_execution"}]})
    result = asyncio.run(exercise())
    assert result["status"] == "incomplete"
    assert result["execution_performed"] is False


def test_coding_loop_completes_only_with_successful_artifact():
    async def exercise():
        actions = iter([
            {"tool": "write_experiment_file", "arguments": {"path": "demo.py", "content": "print(42)"}},
            {"tool": "run_experiment_command", "arguments": {"command": "python demo.py"}},
            {"tool": "finish", "summary": "隔离实验区运行成功；原工作区未修改", "outcome": "completed"},
        ])
        async def model(_system, _context):
            return json.dumps({"purpose": "verify", **next(actions)})
        async def emit(*args, **kwargs):
            pass
        async def write(_):
            return {"status": "completed", "scope": "experiment_scratch_only", "path": "demo.py"}
        async def run(_):
            return {"status": "completed", "execution_performed": True, "exit_code": 0,
                    "generated_artifacts": [{"path": "result.txt", "sha256": "abc"}]}
        return await run_coding(assignment("implement and run", "coding", ["c1", "c2"]), model,
                                {"write_experiment_file": ({}, write), "run_experiment_command": ({}, run)},
                                None, emit, max_turns=3,
                                context={"goals": [{"id": "c1", "kind": "code_change"},
                                                    {"id": "c2", "kind": "experiment_execution"}]})
    result = asyncio.run(exercise())
    assert result["status"] == "completed"
    assert result["execution_performed"] is True
    assert result["generated_artifacts"][0]["path"] == "result.txt"


@pytest.mark.skipif(not shutil.which("docker"), reason="Docker CLI unavailable")
def test_real_docker_experiment_is_networkless_and_persists_output(tmp_path):
    import subprocess
    image = next((candidate for candidate in ("python:3.11-slim", "node:22-alpine")
                  if subprocess.run(["docker", "image", "inspect", candidate],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0), None)
    if image is None:
        pytest.skip("No suitable image pre-pulled; tests never pull automatically")

    async def exercise():
        workspace = DockerExperimentWorkspace(tmp_path / "experiment", image=image)
        workspace.write({"path": "input.txt", "content": "42\n"})
        return await workspace.run({"command": "cp input.txt result.txt && cat result.txt", "timeout_seconds": 15})
    result = asyncio.run(exercise())
    assert result["status"] == "completed" and result["exit_code"] == 0
    assert Path(tmp_path / "experiment" / "result.txt").read_text() == "42\n"
    assert any(a["path"] == "result.txt" for a in result["artifacts"])


@pytest.mark.skipif(not shutil.which("docker"), reason="Docker CLI unavailable")
def test_real_docker_diagnostic_echo_cannot_hide_failure(tmp_path):
    import subprocess
    image = next((candidate for candidate in ("python:3.11-slim", "node:22-alpine")
                  if subprocess.run(["docker", "image", "inspect", candidate],
                                    stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0), None)
    if image is None:
        pytest.skip("No suitable image pre-pulled")
    async def exercise():
        workspace = DockerExperimentWorkspace(tmp_path / "failed", image=image)
        return await workspace.run({"command": "exit 17; echo EXIT=$?", "timeout_seconds": 10})
    result = asyncio.run(exercise())
    assert result["status"] == "failed"
    assert result["exit_code"] == 17
