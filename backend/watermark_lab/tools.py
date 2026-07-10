"""Tool set for the watermark experiment agent (AI4Science).

The agent's action space mirrors a real robustness experiment:
list images -> embed watermark -> apply physical-channel distortion ->
extract -> report bit accuracy / PSNR. All heavy lifting runs in the
watermark-mcp torch venv via the subprocess bridge; the tools here are
model-agnostic (swap the model by re-pointing WATERMARK_MCP_ROOT).

Reuses the same ToolRegistry as the doc agent - one registry implementation,
two agents.
"""
from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from pathlib import Path

from backend.doc_agent.tool_registry import ToolRegistry
from .bridge import run_action, WATERMARK_ROOT

registry = ToolRegistry()

WORKSPACE_ROOT = Path(__file__).resolve().parents[2] / "outputs" / "watermark_lab"


@dataclass
class LabSession:
    session_id: str
    workspace: Path
    trace: list[dict] = field(default_factory=list)
    # embed results are remembered so extract can check accuracy without the
    # LLM having to shuttle 30-bit arrays through its own context
    embedded: dict[str, dict] = field(default_factory=dict)  # output path -> {index, source}


def new_session() -> LabSession:
    session_id = uuid.uuid4().hex[:12]
    workspace = WORKSPACE_ROOT / session_id
    workspace.mkdir(parents=True, exist_ok=True)
    return LabSession(session_id=session_id, workspace=workspace)


@registry.register(
    name="list_test_images",
    description="List available cover images in the experiment dataset.",
    parameters={
        "type": "object",
        "properties": {"limit": {"type": "integer", "description": "Max images to list (1-10).", "default": 5}},
    },
)
async def list_test_images(context: LabSession, limit: int = 5) -> dict:
    return await run_action("list-images", "--limit", str(max(1, min(int(limit), 10))))


@registry.register(
    name="embed_watermark",
    description="Embed a 30-bit watermark message into cover images using the "
                "screen-shooting robust model (PIMoG). Returns watermarked image "
                "paths and embedding imperceptibility (PSNR in dB).",
    parameters={
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": {"type": "string"},
                       "description": "Cover image paths (from list_test_images)."},
        },
        "required": ["images"],
    },
)
async def embed_watermark(images: list[str], context: LabSession) -> dict:
    result = await run_action("embed", "--images", *images,
                              "--out-dir", str(context.workspace))
    for item in result.get("results", []):
        if item.get("success"):
            context.embedded[item["output"]] = {
                "index": item["watermark_index"], "source": item["source"]}
            item.pop("bits", None)  # keep 30-bit arrays out of the LLM context
    return result


@registry.register(
    name="apply_distortion",
    description="Apply a physical-channel distortion to watermarked images. "
                "'screen_shooting' simulates the full screen-camera channel "
                "(perspective + light + moire + gaussian noise); 'identity' is "
                "the no-distortion control group.",
    parameters={
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": {"type": "string"},
                       "description": "Watermarked image paths."},
            "distortion": {"type": "string", "enum": ["screen_shooting", "identity"],
                           "default": "screen_shooting"},
        },
        "required": ["images"],
    },
)
async def apply_distortion(images: list[str], context: LabSession,
                           distortion: str = "screen_shooting") -> dict:
    result = await run_action("distort", "--images", *images,
                              "--out-dir", str(context.workspace),
                              "--distortion", distortion)
    # propagate watermark provenance from the source to the distorted copy
    for item in result.get("results", []):
        if item.get("success") and item["source"] in context.embedded:
            context.embedded[item["output"]] = context.embedded[item["source"]]
    return result


@registry.register(
    name="extract_watermark",
    description="Extract the 30-bit watermark from images and, when the image "
                "came from this session's embed/distort steps, report bit "
                "accuracy against the originally embedded message.",
    parameters={
        "type": "object",
        "properties": {
            "images": {"type": "array", "items": {"type": "string"},
                       "description": "Images to decode (watermarked or distorted)."},
        },
        "required": ["images"],
    },
)
async def extract_watermark(images: list[str], context: LabSession) -> dict:
    known = [context.embedded.get(p, {}).get("index") for p in images]
    args = ["extract", "--images", *images]
    if all(index is not None for index in known):
        args += ["--expected-indices", *[str(i) for i in known]]
    result = await run_action(*args)
    for item in result.get("results", []):
        item.pop("decoded_bits", None)  # bit arrays are noise for the LLM
    return result
