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

## 3. First handoff from the already-running Windows deployment

PR #11 contains the Windows-tested code fixes. Its field report and sanitized AstaBench packet are evidence, not a complete copy of the host: the working `deploy/.env`, model keys, Docker volumes, WSL/Docker Desktop configuration, firewall rules, and raw evaluation output remain on Windows. Keep the currently working containers and their image IDs until the first update has passed smoke tests. Do not rebuild the older `main` and assume it reproduces this installation.

**After PR #11 is merged**, prepare a dedicated clean deployment checkout at the full merge SHA. Keep the same Compose project name (`asteria-lab`); copy only the existing ignored `deploy/.env` into that checkout, without committing or printing it. Do not replace the database or volumes. Because that new checkout's Git revision may not match the image already running from PR #11/local Windows fixes, the *first* handoff is explicit:

```powershell
$tokens = $null; $errors = $null
[System.Management.Automation.Language.Parser]::ParseFile((Resolve-Path '.\deploy\update-windows.ps1'), [ref]$tokens, [ref]$errors) | Out-Null
if ($errors.Count) { $errors | ForEach-Object { Write-Error $_.ToString() }; throw 'Update script syntax check failed' }
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit> -AdoptExisting -CheckOnly
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit> -AdoptExisting
```

Use `-AdoptExisting` only after checking that the current API and Worker are the known-good Windows installation and confirming a writable backup drive. It allows an initial runtime-revision mismatch; it does not prove that the old running image was built from the new checkout. Retain the old image IDs and database backup until acceptance. Do **not** use this switch for normal future updates: a mismatch then signals an out-of-band rebuild, a wrong checkout, or mixed containers and needs investigation.

## 4. Subsequent Mac-to-Windows updates

Use a **dedicated clean deployment checkout** with the existing ignored `deploy/.env` retained. The Docker data VHDX and named volumes are already on E: on the current host; the script never deletes volumes. From PowerShell on Windows:

```powershell
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit> -CheckOnly
powershell -ExecutionPolicy Bypass -File .\deploy\update-windows.ps1 -Revision <40-character-merge-commit>
```

Pushing a Mac commit does **not** update Windows by itself. Merge the reviewed PR, take the full SHA from `main`, run `-CheckOnly`, then run the update command. The script fetches `origin/main`, requires that SHA to be on it, and compares the running API/Worker image revisions with the deployment checkout before proceeding. It refuses a dirty checkout, relevant schema-file changes, or active research/coordinator/indexing jobs. It creates a PostgreSQL custom-format backup under `E:\AsteriaBackups`, saves the current API/Web image IDs as rollback tags, checks out the exact commit, validates Compose, builds API/Worker/Web and checks package integrity in the built backend image even if Docker reused a cached layer.

Before activation it stops new Web/API submissions and checks active work **again**, so a job started during the build does not cause the Worker to be killed. With no active work it replaces API, Worker and Web. Acceptance requires API/Web health, a running Worker, the login endpoint, and API/Worker image revisions matching the requested SHA. If activation fails, it restores the previous image tags and commit and checks the restored services; rollback failure is reported separately. This is an image/code rollback, **not** a database rollback. Changes to schemas, workspaces, reports, RAG data, model keys, or host configuration need a separate reviewed plan and backup.

The same Compose project name (`asteria-lab`) preserves existing named volumes. Keep `deploy/.env` and `ASTERIA_MODEL_SETTINGS_SECRET` unchanged so saved model keys remain decryptable. If the host uses LAN bindings, the merged commit must include `deploy/compose.lan.yaml` and the host firewall rule must remain restricted to the intended subnet. No `docker compose down -v` is used.

After activation, Windows runs an authenticated short request, an embedding/RAG lookup, and one small report task before the AstaBench validation subset. Record the activated commit, container image IDs, feature outcome, and known limitations in a new packet. Compare only runs with the same AstaBench split, search/tool access, judge and sandbox conditions; the first packet's closed-book LitQA2 and partial E2E result are not a full benchmark score. A successful image health check does not prove an E2E experiment, GPU use, or the Mac paper corpus has been verified.

## Current handoff status

PR #11 merged the first Windows deployment fixes and sanitized AstaBench packets into `main`. The user confirmed that the running code fixes are represented in the PR, while some raw evaluation results remain only on Windows. The host image SHA has not been independently verified on Mac, so the one-time adoption above remains an explicit Windows validation step.
