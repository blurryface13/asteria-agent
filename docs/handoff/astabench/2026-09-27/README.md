# AstaBench Windows handoff — 2026-09-27

These are **allowlisted summaries**, intended for review on the Mac after fetching this Git branch. Raw Inspect `.eval` files, official gated prompts, Asteria reports, credentials and model responses remain on the Windows host. The exporter `scripts/export-astabench-handoff.py` emits only run identity, numeric usage/score, artifact kinds/sizes, and agent/tool/status events.

## LitQA2 baseline

Official AstaBench v0.5.4 (`36c9bc14a83b95851a4f5c4baaccdde6d1c0cafb`) validation: 4/10 correct. Test: 15/75 correct (20%); 36/75 certain answers, of which 15/36 were correct. Nine test requests failed in Asteria intent validation. Every successful answer used `general_chat`; no Asta search tools or local knowledge base were enabled. This is a closed-book baseline and is **not** a standard leaderboard comparison. See `litqa2-summary.json`.

## One E2E validation sample

Official sample `idea-60-simplified` was sent unchanged to Asteria's `experiment_design` durable-run API. The official 48 GB sandbox was not used because the Windows WSL cap was 12 GB, so this is an exploratory adapter run.

1. Before the plan-repair fix, Asteria's invalid `user_quote` failed the literal-task contract twice, before any experiment. Official scorer early-zero branch: 0; no Claude call.
2. After a generic plan-repair instruction fix, the same sample passed planning with a neutral scope confirmation. It then repeatedly failed coding delegation, read no papers, executed no experiment, and delivered no code/report. Official scorer early-zero branch: 0; no Claude call.

The score says “no deliverable” for this single E2E item, not “all Asteria research quality is zero.” Review `e2e-*.json` and the sanitized `*.events.jsonl` progression. The substantive gap is a runnable, controlled experiment/coding path plus valid delegation and artifact delivery; tuning the rubric judge cannot repair an absent answer.

## Scorer API status

The official E2E rubric code requests `claude-sonnet-4-6` for grading **when a result exists**. An APIDock token was saved encrypted on Windows, but a compatibility probe against the supplied homepage URL received HTTP 401 for both x-api-key and bearer authentication. The actual API Base URL/token entitlement must be checked in the APIDock console. No key is in this repository. The failed E2E item did not call or need the judge.

## Future handoff sequence

After each local benchmark run, preserve its raw record on the Windows E: drive, export an allowlisted packet, review it for privacy, and commit that packet on a handoff branch. Include: benchmark version/split/sample count; exact Asteria commit or image digest; adapter and tool/knowledge settings; score plus coverage/failure counts; reason codes; deployment health; and a link to the code fix PR. Keep pre-fix and post-fix results separate. Mac can fetch the branch and compare packets; Windows deploys a reviewed merge commit or release tag, then reruns the same sample set into a new packet.

## Detailed per-sample handoff

For Mac-side diagnosis, read [`optimization-analysis.md`](optimization-analysis.md) first, then [`litqa2-run-index.json`](litqa2-run-index.json) and the four `*.samples.jsonl` files. Each row identifies an Inspect sample by opaque ID and records outcome class, routing capability/confidence, failure class, elapsed seconds and DeepSeek token use. This exposes all 75 test outcomes and the validation/pilot outcomes without reproducing gated questions, targets or model answers. The full `.eval` archives and E2E diagnostics are retained separately for private transfer to an authorized dataset user.
