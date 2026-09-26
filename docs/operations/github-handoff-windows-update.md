# GitHub handoff and Windows update path

This is the shared operating path for Mac development and the Windows lab host. It keeps evaluation evidence reviewable and deploys an exact Git revision instead of an unnamed local image.

## 1. Windows publishes an evaluation packet

After a local AstaBench run, keep the raw `.eval`, gated prompts, generated reports, API keys, database dumps and full Docker logs on the Windows E: drive. Run `scripts/export-astabench-handoff.py` against the saved run state, score and diagnostic events. The exporter deliberately copies only allowlisted metadata and agent/tool/status events. Review the generated packet, add a short Markdown interpretation, then commit it on a dated `handoff/...` branch and push it to GitHub.

The first packet is in [`docs/handoff/astabench/2026-09-27/`](../handoff/astabench/2026-09-27/README.md). It preserves the pre-fix and post-fix E2E runs separately. Each later packet should state the benchmark tag/commit, split, sample count, tool/knowledge settings, Asteria commit/image digest, score, failures, model usage, and whether the official sandbox/judge ran. Never compare a no-search baseline to a standard search-enabled leaderboard run as if conditions matched.

Mac fetches the handoff branch and reads the packet and [`Windows field report`](../field-reports/2026-09-26-windows-docker.md). A GitHub pull request is the review thread for fixes; each issue should link to the relevant run packet. Avoid copying gated task text or raw logs into a public issue or PR comment. GitHub's repository view is the timely status source; raw host logs can be shared by a separate private channel only when needed.

## 2. Mac delivers code

Mac implements fixes on a feature branch, runs relevant tests, and opens a PR against `main` with:

- the failure/run IDs and a link to the sanitized packet;
- the generic defect and exact code change;
- what was tested on Mac, and what still requires Windows validation;
- any database/volume migration or configuration change.

Merge only after review. Send Windows the full 40-character merge commit SHA (or an immutable release tag resolving to it). `main` should not be updated in place on Windows while an AstaBench run is active. Code, config templates and migration instructions belong in Git; host secrets and Docker named volumes do not.

## 3. Windows activates that exact commit

Use a **dedicated clean deployment checkout** with the existing ignored `deploy/.env` retained. The Docker data VHDX and named volumes are already on E: on the current host; the script never deletes volumes. From PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit> -CheckOnly
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit>
```

The script fetches `origin/main`, requires the target commit to be on it, refuses a dirty checkout or active research/indexing jobs, creates a PostgreSQL custom-format backup under `E:\AsteriaBackups`, saves both current image IDs as rollback tags, checks out the exact commit, validates Compose, builds API/Worker/Web, and replaces application containers. It requires API/Web health and the login endpoint to pass. If activation fails, it restores the previous image tags and commit and restarts those application containers. It does **not** automatically reverse database schema changes or replace a full backup of workspaces, reports and RAG volumes; changes to those require an explicit migration/backup plan in the PR.

The same Compose project name (`asteria-lab`) preserves existing named volumes. Keep `deploy/.env` and `ASTERIA_MODEL_SETTINGS_SECRET` unchanged so saved model keys remain decryptable. If the host uses LAN bindings, the merged commit must include `deploy/compose.lan.yaml` and the host firewall rule must remain restricted to the intended subnet. No `docker compose down -v` is used.

After activation, Windows runs the same smoke checks and then a small AstaBench validation subset. Export a new packet labelled with the activated commit and compare it to the previous baseline. A successful image health check does not by itself mean an E2E experiment or the Mac paper corpus has been verified.

## Current handoff status

The first Windows deployment fixes and AstaBench packets are on `handoff/windows-docker-astabench-20260927` until reviewed and merged. The active local API/Worker may include changes not in GitHub `main`; do not rebuild from `main` and call it the verified Windows image before merging the required files.
