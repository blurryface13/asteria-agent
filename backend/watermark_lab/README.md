# Watermark Experiment Agent (AI4Science)

A ReAct agent that orchestrates **real digital-watermarking robustness
experiments** — not simulations. Every tool call executes actual model
inference (embedding / physical-channel distortion / decoding) on the PIMoG
screen-shooting robust watermarking model.

## Why this exists

It closes the loop between the owner's CV research (physical-channel robust
watermarking) and the agent system: the agent plans and runs the same
experiment pipeline a researcher would — embed → distort → extract → metrics —
and writes the experiment report from observed numbers only.

## Architecture

```
asteria-agent (this repo, no torch)                 watermark-mcp (own torch venv)
┌───────────────────────────────────┐   subprocess  ┌───────────────────────────┐
│ ReAct loop (react_agent.py)       │  ──────────▶  │ mcp/experiment_cli.py     │
│ ToolRegistry (shared w/ doc_agent)│   JSON out    │  embed / distort /        │
│ tools: list_test_images,          │  ◀──────────  │  extract / list-images    │
│  embed_watermark, apply_distortion│               │ PIMoG Encoder/Decoder +   │
│  extract_watermark                │               │ ScreenShooting noise layer│
└───────────────────────────────────┘               └───────────────────────────┘
```

- **Model-agnostic contract**: the CLI's four actions are the interface;
  swapping in a different watermark model (e.g. the owner's own thesis models,
  DWSF) only means re-implementing `_load_model/_encode/_decode` in the CLI.
- **Env isolation**: torch stays in watermark-mcp's venv; asteria talks JSON
  over subprocess. Point `WATERMARK_MCP_ROOT` elsewhere to switch model repos.
- **Session provenance**: embed results (which 30-bit message went into which
  image) are tracked server-side, so extract can compute bit accuracy without
  the LLM shuttling bit arrays through its context.

## Measured results (real runs, 2026-07-10)

Agent instruction: *"评估 PIMoG 在屏摄失真下的鲁棒性,含无失真对照组"* — the agent
autonomously planned list → embed → distort(identity + screen_shooting) →
extract, including designing the control group.

| 指标 | 值 |
|---|---|
| Agent 端到端耗时 | **17.0s**(第二次运行;首次 ~40s,含模型冷加载) |
| ReAct 步数 / 工具调用 | 5 / 5 |
| 嵌入不可感知性 | PSNR **39.3-39.4 dB**(与 PIMoG 论文一致) |
| 屏摄失真下提取准确率 | **30/30 bits(100%)**(透视+光照+摩尔纹+高斯) |
| 无失真对照组 | 100% |

## API

`POST /api/watermark-lab/run` `{"instruction": "..."}` (JWT) → ReAct trace +
run metrics + Markdown experiment report.

## Compat fixes made in watermark-mcp

- kornia ≥ 0.7 moved `get_perspective_transform` etc. into
  `kornia.geometry.transform` — aliased at CLI import.
- numpy ≥ 2.0 no longer auto-converts 1-element arrays to scalars —
  `Moire_Distortion` centers wrapped in `float()`.
