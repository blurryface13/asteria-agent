import asyncio
import hashlib
import importlib.util
from pathlib import Path

import httpx
import pytest


spec = importlib.util.spec_from_file_location("research_acceptance", Path(__file__).parents[1] / "scripts/accept-research-chain.py")
acceptance = importlib.util.module_from_spec(spec)
spec.loader.exec_module(acceptance)


@pytest.mark.parametrize("bad_hash", [False, True])
def test_acceptance_requires_downloadable_matching_deliverables(bad_hash):
    bodies = {"md": b"# Report", "latex_pdf": b"%PDF-1.7 fixture",
              "citation_review": b'{"status":"completed"}', "lead_decisions": b'[{"tool":"finish"}]'}
    artifacts = [{"kind": k, "path": "outputs/test/" + k, "size_bytes": len(v),
                  "sha256": "invalid" if bad_hash else hashlib.sha256(v).hexdigest()} for k, v in bodies.items()]

    def handle(request):
        assert request.headers["Authorization"] == "Bearer test-only"
        return httpx.Response(200, content=bodies[request.url.path.rsplit("/", 1)[1]])

    async def run():
        async with httpx.AsyncClient(base_url="http://test", transport=httpx.MockTransport(handle),
                                     headers={"Authorization": "Bearer test-only"}) as client:
            return await acceptance.verify_deliverables(client, {"artifacts": artifacts})

    if bad_hash:
        with pytest.raises(ValueError, match="differs"):
            asyncio.run(run())
    else:
        assert len(asyncio.run(run())) == 4
