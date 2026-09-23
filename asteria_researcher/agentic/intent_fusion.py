"""EchoMind-inspired intent fusion, adapted to Asteria's deliverable contracts.

Unlike the reference: strict LRU+TTL, full context hashes, explicit vector mode,
and no keyword-only fallback that silently starts an expensive/tool-enabled task.
"""
import asyncio
from collections import OrderedDict
from copy import deepcopy
import hashlib
import json
import math
import re
import time
from weakref import WeakKeyDictionary


TEMPLATES = {
    "general_chat": ["你好", "解释上一条回答，不需要查资料", "把刚才的结论翻译成英文"],
    "knowledge_chat": ["根据我们知识库里的论文解释这个定义", "查阅上传的实验记录回答这个问题"],
    "literature_review": ["对比扩散模型水印方法，生成有论文依据的综述报告", "调研这些论文的方法和实验，并分析代码实现"],
    "experiment_design": ["设计消融实验方案，明确数据集、基线和评价指标", "制定复现实验计划"],
    "general_research": ["搜索公开资料，整理行业研究报告", "调研不同开源数据库的优势和局限"],
    "workspace_coding": ["读取attention.py，分析实现并提出修改", "查找工作区文件并修改README", "分析这个GitHub仓库的bug"],
    "learning_guidance": ["为我制定机器学习入门的学习计划", "根据我的基础推荐练习"],
    "submission_consulting": ["核对本年度会议投稿截止日期和材料要求", "查询这个期刊的投稿范围"],
    "financial_research": ["解释市盈率和现金流，不需要研究报告", "分析公司的公开财务数据和风险"],
    "company_research": ["核实公司的主体和公开业务信息", "对这家企业进行公开资料背调"],
}
PATTERNS = {
    "literature_review": [r"文献综述|论文调研|related.work|literature.review", r"(?:对比|综述|调研).{0,40}(?:论文|文献|科研方法)"],
    "experiment_design": [r"(?:设计|制定|规划).{0,15}(?:实验|复现).{0,10}(?:方案|计划|协议)|消融实验方案"],
    "workspace_coding": [r"(?:读取|查找|修改|删除|检查|修复).{0,35}(?:文件|代码|readme|\.(?:py|js|ts|md)\b)", r"github|debug|bug|调试"],
    "knowledge_chat": [r"知识库|上传的.{0,8}(?:论文|记录|资料)"],
    "learning_guidance": [r"学习计划|学习路径|入门.{0,10}练习"],
    "submission_consulting": [r"投稿|征稿|截稿|call.for.papers"],
    "financial_research": [r"市盈率|现金流|财务|投资|资产负债"],
    "company_research": [r"企业背调|公司背调|公司主体|企业公开|尽职调查"],
    "general_research": [r"行业研究报告|公开资料调研|调研报告"],
    "general_chat": [r"^(?:你好|您好|hello|hi)[！!。\s]*$", r"(?:翻译|解释|改写).{0,20}(?:刚才|上一条|报告中的)"],
}
VERSION = hashlib.sha256(json.dumps(['orchestrator-main-support-v1', TEMPLATES, PATTERNS], sort_keys=True, ensure_ascii=False).encode()).hexdigest()
WEIGHTS = {"llm": .7, "embedding": .2, "pattern": .1}


def cosine(a, b):
    if len(a) != len(b) or not a or not all(math.isfinite(float(x)) for x in [*a, *b]):
        raise ValueError("Invalid embedding shape or values")
    norm = math.sqrt(sum(x*x for x in a) * sum(x*x for x in b))
    return sum(x*y for x, y in zip(a, b)) / norm if norm else 0.


def local_features(text, dimensions=512):
    """Lexical fallback, deliberately NOT advertised as a semantic embedding."""
    normalized = re.sub(r"\s+", " ", text.casefold()).strip()[:6000]
    vector = [0.] * dimensions
    tokens = {normalized[i:i+n] for n in (1, 2, 3) for i in range(max(0, len(normalized)-n+1))}
    for token in tokens:
        digest = hashlib.sha256(token.encode()).digest()
        vector[int.from_bytes(digest[:4], "big") % dimensions] += 1 if digest[4] % 2 else -1
    return vector


def pattern_vote(message, available):
    scores = {c: min(1., .65 + .2*(hits-1)) for c, patterns in PATTERNS.items() if c in available
              if (hits := sum(bool(re.search(p, message, re.I)) for p in patterns))}
    if not scores:
        return {"capability": None, "score": 0.}
    winner = max(scores, key=scores.get)
    # Report ties instead of letting dictionary order decide a compound task.
    if sum(v == scores[winner] for v in scores.values()) > 1:
        return {"capability": None, "score": 0., "ambiguous": sorted(scores)}
    return {"capability": winner, "score": scores[winner]}


class IntentFusion:
    def __init__(self, capacity=256, ttl=300, clock=time.monotonic):
        self.capacity, self.ttl, self.clock = capacity, ttl, clock
        self.cache, self.templates = OrderedDict(), OrderedDict()
        self.hits, self.misses = 0, 0
        self.template_locks = WeakKeyDictionary()

    def cache_get(self, key):
        item = self.cache.get(key)
        if item is None:
            return None
        saved_at, value = item
        if self.clock() - saved_at >= self.ttl:
            del self.cache[key]
            return None
        self.cache.move_to_end(key)
        self.hits += 1
        return deepcopy(value)

    def cache_put(self, key, value):
        self.cache[key] = self.clock(), deepcopy(value)
        self.cache.move_to_end(key)
        while len(self.cache) > self.capacity:
            self.cache.popitem(last=False)

    async def vector_vote(self, message, available, embed, identity):
        pairs = [(c, text) for c, texts in TEMPLATES.items() if c in available for text in texts]
        key = (identity, tuple(available), VERSION)
        mode, failure = "semantic_embedding", None
        try:
            if embed is None:
                raise ValueError("No embedding adapter")
            vectors = self.templates.get(key)
            if vectors is None:
                # Coalesce cold template encoding, not user requests. Locks belong
                # to the running loop so sequential test/event loops stay valid.
                locks = self.template_locks.setdefault(asyncio.get_running_loop(), {})
                lock = locks.setdefault(key, asyncio.Lock())
                async with lock:
                    vectors = self.templates.get(key)
                    if vectors is None:
                        vectors = await asyncio.wait_for(embed([text for _, text in pairs]), 12)
                        if len(vectors) != len(pairs):
                            raise ValueError("Embedding count mismatch")
                        for vector in vectors:
                            cosine(vector, vector)
                        # Only static templates are cached; never user query vectors.
                        self.templates[key] = vectors
                        self.templates.move_to_end(key)
                        while len(self.templates) > 4:
                            self.templates.popitem(last=False)
            query_vectors = await asyncio.wait_for(embed([message[:6000]]), 8)
            if len(query_vectors) != 1:
                raise ValueError("Query embedding count mismatch")
            query = query_vectors[0]
            scores = [(c, max(0., cosine(query, v))) for (c, _), v in zip(pairs, vectors)]
        except Exception as exc:
            # CancelledError is not swallowed; auth/provider failures stay distinguishable.
            failure, mode = type(exc).__name__, "local_ngram"
            query = local_features(message)
            scores = [(c, max(0., cosine(query, local_features(text)))) for c, text in pairs]
        winner, similarity = max(scores, key=lambda item: item[1])
        return {"capability": winner if similarity >= .35 else None,
                "score": similarity if similarity >= .35 else 0., "mode": mode, "failure": failure}

    async def recognize(self, payload, semantic, *, available, embed=None, identity=None, cache_scope=None):
        start = self.clock()
        available = sorted(available)
        # Full input hashes: no prefix truncation collisions, and no cross-account reuse.
        key = hashlib.sha256(json.dumps({"payload": payload, "scope": cache_scope,
            "model": identity, "available": available, "version": VERSION, "weights": WEIGHTS},
            sort_keys=True, ensure_ascii=False).encode()).hexdigest() if cache_scope and identity else None
        if key:
            found = self.cache_get(key)
            if found is not None:
                found["routing_trace"].update(cache_hit=True, latency_ms=round((self.clock()-start)*1000, 2))
                return found
        self.misses += 1
        llm_job = asyncio.create_task(semantic())
        emb_job = asyncio.create_task(self.vector_vote(payload["message"], available, embed, identity))
        try:
            llm, emb = await asyncio.gather(llm_job, emb_job)
        except BaseException:
            for job in (llm_job, emb_job):
                job.cancel()
            await asyncio.gather(llm_job, emb_job, return_exceptions=True)
            raise  # Never convert a paid-model failure into successful keyword routing.
        pat = pattern_vote(payload["message"], available)
        votes = {"llm": {"capability": llm["capability"], "score": llm["confidence"]}, "embedding": emb, "pattern": pat}
        weights = dict(WEIGHTS)
        # Lexical fallback is weaker, not a second semantic model.
        if emb["mode"] != "semantic_embedding":
            weights.update(llm=.85, embedding=.05)
        scores = {}
        for source, vote in votes.items():
            if vote["capability"] in available:
                scores[vote["capability"]] = scores.get(vote["capability"], 0.) + weights[source]*vote["score"]
        ranked = sorted(scores, key=scores.get, reverse=True)
        winner = ranked[0]
        score = scores[winner]
        margin = score - (scores[ranked[1]] if len(ranked) > 1 else 0.)
        conflict = winner != llm["capability"]
        clarify = llm.get("needs_clarification", False) or score < .5 or margin < .12 or conflict
        result = {**llm, "capability": winner, "needs_clarification": clarify,
                  "routing_trace": {"version": VERSION[:12], "source_votes": votes, "weights": weights,
                    "scores": scores, "winning_score": score, "margin": margin,
                    "cache_hit": False, "latency_ms": round((self.clock()-start)*1000, 2),
                    "note": "融合分数为启发式分值，不是校准后的准确率或任务成功率"}}
        if clarify:
            result["clarification_question"] = llm.get("clarification_question") or "你希望我直接解答、调研并生成报告，还是检查或修改代码？请明确这次的交付内容。"
        else:
            result["clarification_question"] = ""
        # Do not cache degraded-vector/clarification results: recovery should be observable.
        if key and not clarify and (emb["mode"] == "semantic_embedding" or embed is None):
            self.cache_put(key, result)
        return result


FUSION = IntentFusion()
