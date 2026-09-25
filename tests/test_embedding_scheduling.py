"""A large research corpus must not monopolize the shared embedding slot."""
import asyncio

from asteria_researcher.context import hybrid_compression as hybrid


def test_small_retrieval_gets_a_slot_between_large_corpus_batches(monkeypatch):
    async def scenario():
        monkeypatch.setattr(hybrid, "_EMBED_BATCH", 2)
        monkeypatch.setattr(hybrid, "_EMBED_SEMAPHORE", asyncio.Semaphore(1))
        entered, release, small_queued = asyncio.Event(), asyncio.Event(), asyncio.Event()
        order, active, peak = [], 0, 0

        class Embeddings:
            async def aembed_documents(self, texts):
                nonlocal active, peak
                active += 1
                peak = max(peak, active)
                order.append(list(texts))
                try:
                    if texts[0] == "0":
                        entered.set()
                        await release.wait()
                    return [[int(text)] for text in texts]
                finally:
                    active -= 1

        compressor = hybrid.HybridContextCompressor([], Embeddings())
        large = asyncio.create_task(compressor._embed_texts(["0", "1", "2", "3", "4"]))
        await entered.wait()

        async def small_request():
            small_queued.set()
            return await compressor._embed_texts(["9"])

        small = asyncio.create_task(small_request())
        await small_queued.wait()
        release.set()
        large_vectors, small_vectors = await asyncio.gather(large, small)
        assert large_vectors == [[0], [1], [2], [3], [4]]
        assert small_vectors == [[9]]
        assert peak == 1 and all(len(batch) <= 2 for batch in order)
        assert order.index(["9"]) < order.index(["2", "3"])

    asyncio.run(scenario())


def test_cancelled_embedding_releases_provider_slot(monkeypatch):
    async def scenario():
        monkeypatch.setattr(hybrid, "_EMBED_SEMAPHORE", asyncio.Semaphore(1))
        entered = asyncio.Event()

        class Embeddings:
            async def aembed_documents(self, texts):
                if texts == ["blocked"]:
                    entered.set()
                    await asyncio.Event().wait()
                return [[1] for _ in texts]

        compressor = hybrid.HybridContextCompressor([], Embeddings())
        blocked = asyncio.create_task(compressor._embed_texts(["blocked"]))
        await entered.wait()
        blocked.cancel()
        await asyncio.gather(blocked, return_exceptions=True)
        assert await asyncio.wait_for(compressor._embed_texts(["next"]), 1) == [[1]]

    asyncio.run(scenario())
