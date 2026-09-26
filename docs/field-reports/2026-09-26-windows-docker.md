# Windows Docker field report — 2026-09-26/27

This report records the first Windows 11 + Docker Desktop + WSL2 deployment of Asteria. It is a handoff for the Mac development machine. The GitHub `main` revision at the start was `691b70d`; several fixes described here were made locally afterward and must be reviewed and merged before a clean Windows redeployment can reproduce them.

## Final verified state

- Docker Desktop Linux engine ran under WSL2 with an approximately 12 GB WSL memory cap. Docker's data VHDX was moved to `E:\DK\DockerDesktopWSL\disk\docker_data.vhdx`.
- Compose services `api`, `worker`, `web`, PostgreSQL, Redis and Ollama were running. API/Web/PostgreSQL/Redis/Ollama health checks passed; Worker was running.
- A local short DeepSeek call, 1024-dimensional `bge-m3` embedding, Chroma round trip, RAG bridge load and authenticated web login passed. A CV literature review produced an 11-page Chinese PDF with 11 checked references. The long review exposed a table pagination problem.
- LAN access from a Mac on the same Wi-Fi was tested successfully. The bind address and firewall rule are local operational settings and are not committed as universal defaults.

## Failure chain and cause

| Stage | Observed symptom | Cause / resolution |
| --- | --- | --- |
| Docker installation | CLI absent; later daemon pipe 500/502 and “unable to start” | WSL2 feature had to be enabled and Windows restarted. Docker Desktop engine was then started; WSL memory/swap were set in the user's `.wslconfig`. This was host setup, not an Asteria code defect. |
| Base images | OAuth token request to `auth.docker.io` timed out | Network/proxy path to Docker Hub was intermittent. Retrying after Docker engine/network recovery allowed images to pull. |
| API container | Repeated clean exit or unhealthy startup | The built image once contained a zero-byte `scripts/start-research-service.py`. A nonempty entrypoint check and a deployment preflight were added so such an image fails at build time. |
| Python dependencies | `uvicorn.run` absent; later imports failed in `typing_extensions`, `requests`, `tenacity`, `tiktoken` and other packages | Several files in an earlier cached dependency layer were empty/truncated. Forced version pins alone did not fix the corruption and introduced conflicts. The backend image now reinstalls dependencies without pip cache and verifies package metadata/source sizes and imports. |
| App startup | Worker/API image could build but not safely activate | A verified-image activation procedure saved the previous image, checked for active jobs, restarted API and Worker, then ran DB/model/vector/RAG smoke checks. This existed as a host-local script; the repository update path below makes future activation reproducible. |
| LAN access | Mac initially could not reach Windows | Both devices had to join the same Wi-Fi; Windows bound the LAN address and a firewall rule allowed the intended subnet. Localhost-only Compose bindings remain the default. |

Do not reintroduce ad hoc `typing_extensions` or `uvicorn` version pins to treat empty wheel files. Confirm package integrity first. The Windows PowerShell 5 `RandomNumberGenerator.Fill` call also failed; the local first-run script uses `RandomNumberGenerator.Create().GetBytes()` instead.

## Packaging changes to merge

- `deploy/Dockerfile.backend`: cache-free pip install, package integrity checks, nonempty entrypoint check.
- `scripts/verify-installed-packages.py` and `scripts/deployment-preflight.py`: fail early on truncated packages or import failures.
- `scripts/start-research-service.py`: portable Uvicorn startup with explicit asyncio loop.
- `deploy/compose.lan.yaml`: optional LAN bindings; pair it with a restrictive host firewall rule.
- `asteria_researcher/agentic/autonomous.py`: separate AstaBench-discovered plan repair contradiction; see the benchmark handoff.

## Remaining limits

- A running service does not prove the full paper corpus migrated. The original Mac RAG data and historical accounts are not included in Git or Docker images.
- E2E experiment execution is still incomplete; the first AstaBench E2E sample failed after planning/coding delegation. The failure is in the application workflow, not Docker.
- The 11-page PDF comparison table can split its heading and body across pages.
- A Docker image rollback does not undo database schema changes. Back up data and inspect migrations before deploying a new revision.

## Handoff rule

Mac reviews this report and the bounded AstaBench packet in `docs/handoff/astabench/2026-09-27/`. Mac changes code in a PR; CI and review produce a specific merge commit or release tag. Windows deploys that exact revision with `deploy/update-windows.ps1`, preserving local `.env` and named volumes, and records health/smoke results. Raw logs, gated benchmark prompts, database dumps, and API keys remain on the host.
