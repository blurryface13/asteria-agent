# Windows AstaBench diagnosis for Mac-side development (2026-09-27)

This note accompanies [PR #11](https://github.com/blurryface13/asteria-agent/pull/11). The public `*.samples.jsonl` files contain one row for each Inspect sample, with only an opaque sample ID, outcome class, Asteria status, routing capability/confidence, failure class, elapsed time and token counts. They contain no prompt, target answer, response, rationale or credential. The corresponding original `.eval` archives remain in a separate private handoff because the AstaBench dataset is gated and prohibits redistribution.

## Exact experimental conditions

- AstaBench v0.5.4, commit `36c9bc14a83b95851a4f5c4baaccdde6d1c0cafb`; official LitQA2 task and scorer, custom Asteria solver.
- Model configured in Asteria: `deepseek-chat`. Inspect's `mockllm/model` is a harness placeholder. The Asteria API created one conversation per question.
- LitQA2: Asta search tools off (`with_search_tools=False`), local knowledge base off. This measures closed-book Q&A routed by Asteria, not the standard search-enabled configuration and not a leaderboard score.
- The 75-item test baseline was recorded against backend image `sha256:d175f75a52c46b5e27639950e15477223ace50d3430f3e60c171e13d30a72fc1`. Later E2E runs used a different local backend, so do not combine these into one system score.

## Run inventory and results

| Run | N | Correct | Wrong confident | Unsure | Run failed | Interpretation |
| --- | ---: | ---: | ---: | ---: | ---: | --- |
| Pilot | 1 | 1 | 0 | 0 | 0 | Connectivity smoke only |
| Early validation attempt | 3 | 1 | 0 | 0 | 0 (2 unscored) | Interrupted/partial; not the validation result |
| Validation | 10 | 4 | 0 | 3 | 3 | 4/10 total accuracy |
| Test baseline | 75 | 15 | 21 | 30 | 9 | 15/75 total accuracy (20%); 15/36 among confident answers |

The nine test failures and three validation failures were `SemanticIntent.model_validate_json` errors in Asteria's intent routing. The API container did not crash. Every completed test item was routed to `general_chat`; the research lead, paper search and local RAG were not exercised. The test run recorded 173,490 input and 6,046 output DeepSeek tokens, about 4 minutes 31 seconds wall time. These numbers do not include a verified provider bill.

## Single E2E validation item

AstaBench E2E Discovery validation item `idea-60-simplified` was submitted unchanged to Asteria's `experiment_design` durable-run API. Online research was enabled; the local knowledge base was off. The official 48 GB sandbox was not available within this Windows host's 12 GB WSL cap, making this an exploratory adapter run.

| Run | Result | Evidence | Next failure |
| --- | --- | --- | --- |
| Before generic plan-repair fix | Official scorer early-zero: 0; no Claude call | 19.2 s; 2 model calls; 9,031 input / 3,826 output tokens; no artifact | Plan contract rejected the `user_quote` twice because it was not a literal excerpt of the task. |
| After generic plan-repair fix | Official scorer early-zero: 0; no Claude call | 212 s; 19 model calls; 241,178 input / 43,754 output tokens; 5 agent actions; 0 completed subagents; 0 papers read; 0 downloaded bytes; no artifact | Planning passed. Coding/research delegation was repeatedly rejected; a completion attempt lacked evidence and was refused. |

The second zero is a failure to produce a deliverable on one task. It is not a measured grade of a completed experiment or research report. The official rubric judge requests `claude-sonnet-4-6` only if a result exists; these early-zero branches never invoked it.

## Optimization priorities and falsifiable retests

1. **Make intent routing resilient.** Investigate the raw model output/`SemanticIntent` schema mismatch locally; validate fields, retry malformed structured output and surface a safe fallback with a reason code. Rerun the same 75 test IDs under the same closed-book settings. Primary acceptance measure: routing failures drop from 9/75 to 0/75. Accuracy may improve, but the log does not prove how many of the nine would answer correctly.
2. **Separate answer calibration from routing.** Of 66 completed test samples, 30 selected unsure; among 36 confident answers, 21 were wrong. Compare exact-answer extraction and confidence behavior on the unchanged 75-item set. Report total accuracy, confident coverage and accuracy among confident answers together; do not optimize one while hiding the others.
3. **Add a separately labeled retrieval run.** A scientific paper question that the router calls `general_chat` cannot test research search. Enable the intended Asta tools or a clearly specified corpus in a new run, keeping a fixed split and logging actual search calls, evidence use and cost. Do not compare its score as if it had the same tool conditions as this closed-book baseline.
4. **Repair the E2E delegation and artifact path.** The plan fix resolved the first blocking stage. Trace why proposed research/coding subagents fail quality checks, then require a successful delegation, evidence retrieval, runnable code/experiment and final artifact on this one item. Count completed subagents, papers, executed steps and delivered files. Only then invoke the full official rubric judge and examine the resulting score.
5. **Establish reproducible versioned runs.** Label every future packet with Asteria commit and image digest, benchmark tag, split and sample IDs, tools/corpus, model settings, scorer path and whether the official sandbox ran. Keep pre-fix and post-fix records separate and do not treat this exploratory E2E run as a leaderboard submission.

## Files to inspect

- `litqa2-run-index.json`: mapping from each original Inspect `.eval` archive to its public per-sample metadata file.
- `*.samples.jsonl`: per-sample outcome, route, time, token use and failure class; no question/answer text.
- PR #11 `docs/handoff/astabench/2026-09-27/`: earlier high-level summary and E2E stage/tool/status events.
- Private raw archive: `E:\AstaBench\github-handoff-full` on Windows, containing the four original `.eval` files, E2E states, scores and diagnostic records with `MANIFEST.json` hashes. Access path for Mac must be restricted to a user with legitimate dataset access.
