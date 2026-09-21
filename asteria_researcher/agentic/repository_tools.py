"""Read-only, public GitHub inspection; fixed host, bounded bytes, pinned commit.

Never clones, executes repository code, follows redirects, or forwards credentials.
"""
import base64
import re
from pathlib import PurePosixPath
from urllib.parse import quote

import httpx


def repository_name(value):
    value = value.removeprefix("https://github.com/").rstrip("/").removesuffix(".git")
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", value) or ".." in value:
        raise ValueError("repository 必须是公开 GitHub owner/repo，不接受任意地址")
    return value


async def api(path):
    async with httpx.AsyncClient(timeout=20, follow_redirects=False, trust_env=False) as client:
        async with client.stream("GET", "https://api.github.com/repos/" + path,
                                 headers={"Accept": "application/vnd.github+json", "User-Agent": "Asteria-Research"}) as response:
            if response.status_code != 200:
                raise ValueError(f"GitHub 只读请求失败（HTTP {response.status_code}）")
            chunks, size = [], 0
            async for chunk in response.aiter_bytes():
                size += len(chunk)
                if size > 2 * 1024 * 1024:
                    raise ValueError("仓库响应超过大小限制，请缩小调查范围")
                chunks.append(chunk)
            import json
            return json.loads(b"".join(chunks))


async def pinned_commit(repo, ref="HEAD"):
    if not isinstance(ref, str) or not 1 <= len(ref) <= 160 or any(x in ref for x in ("..", "?", "#", "\\")):
        raise ValueError("无效仓库版本")
    result = await api(repo + "/commits/" + quote(ref, safe=""))
    sha = result.get("sha", "")
    if not re.fullmatch("[0-9a-f]{40}", sha):
        raise ValueError("无法确认仓库提交版本")
    return sha


async def inspect_repository(arguments):
    if set(arguments) - {"repository", "ref"}:
        raise ValueError("仓库调查参数不合法")
    repo = repository_name(arguments.get("repository", ""))
    sha = await pinned_commit(repo, arguments.get("ref", "HEAD"))
    result = await api(f"{repo}/git/trees/{sha}?recursive=1")
    files = [{"path": e["path"], "size": e.get("size"), "sha": e["sha"]}
             for e in result.get("tree", []) if e.get("type") == "blob" and e.get("mode") in {"100644", "100755"}]
    return {"repository": repo, "commit": sha, "files": files[:300],
            "truncated": bool(result.get("truncated")) or len(files) > 300,
            "source_url": f"https://github.com/{repo}/tree/{sha}"}


async def read_repository_file(arguments):
    if set(arguments) - {"repository", "ref", "path"}:
        raise ValueError("仓库读取参数不合法")
    repo = repository_name(arguments.get("repository", ""))
    path = arguments.get("path", "")
    if (not isinstance(path, str) or not path or len(path) > 400 or path.startswith("/") or "\\" in path
            or any(p in {"..", ".", ""} for p in path.split("/")) or PurePosixPath(path).is_absolute()):
        raise ValueError("文件路径必须为仓库内相对路径")
    sha = await pinned_commit(repo, arguments.get("ref", "HEAD"))
    data = await api(f"{repo}/contents/{quote(path, safe='/')}?ref={sha}")
    if not isinstance(data, dict) or data.get("type") != "file" or data.get("encoding") != "base64" or data.get("size", 0) > 131072:
        raise ValueError("只读取不超过128KiB的普通文本文件")
    raw = base64.b64decode(data["content"])
    if len(raw) > 131072 or b"\0" in raw:
        raise ValueError("文件为二进制或超出大小限制")
    return {"repository": repo, "commit": sha, "path": path, "content": raw.decode("utf-8"),
            "source_url": f"https://github.com/{repo}/blob/{sha}/{quote(path, safe='/')}"}


def repository_tools():
    return {
        "inspect_repository": ({"repository": "GitHub owner/repo", "ref": "branch/tag/commit; use returned commit thereafter"}, inspect_repository),
        "read_repository_file": ({"repository": "GitHub owner/repo", "ref": "prefer inspected commit SHA", "path": "relative file path"}, read_repository_file),
    }
