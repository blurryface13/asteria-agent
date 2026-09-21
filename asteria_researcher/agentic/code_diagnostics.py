"""Read-backed static checks and diffs. Never import or execute target code."""
import ast
import asyncio
import difflib
import hashlib

from pydantic import BaseModel, ConfigDict, Field


class SyntaxCheck(BaseModel):
    model_config = ConfigDict(extra="forbid")
    observation_id: str = Field(min_length=1, max_length=80)


class DiffCheck(SyntaxCheck):
    proposed_content: str = Field(max_length=131072)


def source_observation(results, identifier):
    item = next((r for r in results if r["id"] == identifier), None)
    if not item or item["tool"] not in {"read_workspace_file", "read_repository_file"}:
        raise ValueError("必须引用本轮实际读取的代码 observation_id")
    values = item["result"] if isinstance(item["result"], list) else [item["result"]]
    value = next((v for v in values if isinstance(v, dict) and isinstance(v.get("content"), str)), None)
    if value is None or value.get("exists") is False:
        raise ValueError("代码观察没有实际文件内容")
    return value


def syntax_result(content, name):
    if not name.endswith(".py") or len(content.encode()) > 131072:
        raise ValueError("语法检查仅支持不超过128KiB的Python文本")
    digest = hashlib.sha256(content.encode()).hexdigest()
    try:
        # No compile-to-bytecode, imports, plugins, subprocess or execution.
        ast.parse(content, filename=name)
        return {"valid_syntax": True, "content_sha256": digest, "issues": [], "execution_performed": False,
                "scope": "Python语法，不验证算法正确性、依赖或实验结果"}
    except SyntaxError as exc:
        return {"valid_syntax": False, "content_sha256": digest,
                "issues": [{"line": exc.lineno, "column": exc.offset, "message": exc.msg}],
                "execution_performed": False, "scope": "Python语法"}
    except (ValueError, RecursionError):
        raise ValueError("文本无法安全解析，请缩小文件")


def build_diagnostic_tools(results):
    async def syntax(arguments):
        args = SyntaxCheck.model_validate(arguments)
        source = source_observation(results, args.observation_id)
        return {"observation_id": args.observation_id,
                **await asyncio.to_thread(syntax_result, source["content"], source.get("name", source.get("path", "")))}

    async def diff(arguments):
        args = DiffCheck.model_validate(arguments)
        source = source_observation(results, args.observation_id)
        return await asyncio.to_thread(diff_result, args, source)

    def diff_result(args, source):
        name = source.get("name", source.get("path", "source"))
        lines = list(difflib.unified_diff(source["content"].splitlines(keepends=True),
                     args.proposed_content.splitlines(keepends=True), fromfile=name, tofile=name + " (proposed)"))
        result = {"observation_id": args.observation_id, "diff": "".join(lines)[:20000],
                  "truncated": sum(map(len, lines)) > 20000, "applied": False,
                  "original_sha256": hashlib.sha256(source["content"].encode()).hexdigest(),
                  "proposed_sha256": hashlib.sha256(args.proposed_content.encode()).hexdigest(),
                  "execution_performed": False}
        if name.endswith(".py"):
            result["proposed_syntax"] = syntax_result(args.proposed_content, name)
        return result
    return {"check_python_syntax": (SyntaxCheck.model_json_schema(), syntax),
            "preview_code_diff": (DiffCheck.model_json_schema(), diff)}
