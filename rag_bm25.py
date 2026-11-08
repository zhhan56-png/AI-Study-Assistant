"""中文友好的 BM25 关键词检索（BUG-01 修复）。

原实现 ``keyword_search()`` 用 ``query.lower().split()`` 按空格切词，
中文问题（如"中文关键词检索为什么失效"）会被当成一个 token，
与任何文档都匹配不上，得分恒为 0 —— 混合检索因此退化为纯向量检索。
详见 docs/DEBUG-REPORT.md 的 BUG-01。

本模块提供：
- ``tokenize()``：中文用 jieba，英文/数字按词切，并过滤停用词；
- ``BM25``：标准 Okapi BM25（k1=1.5, b=0.75）；
- ``build_bm25_index()``：从 documents（[{"content": ...}, ...]）建索引。

设计说明（面试可讲）：
- 中文没有天然空格，必须分词；jieba 精确模式在通用语料上足够；
- BM25 由三部分组成：IDF（稀有词权重高）、词频饱和（k1 控制）、
  文档长度归一（b 控制）；这三个性质正是不足之处——词重叠率没有的；
- 停用词只保留最小集合，避免把"什么是"之类切碎后误伤召回。
"""

from __future__ import annotations

import math
import re
from collections import Counter
from typing import Dict, List, Sequence

import jieba

__all__ = ["tokenize", "BM25", "build_bm25_index"]

# 最小停用词表：中文功能词 + 英文高频虚词。
_STOPWORDS = set(
    """
    的 了 是 在 我 你 他 她 它 我们 你们 他们 这 那 那么 这个 那个 这些 那些
    有 和 与 及 等 把 被 让 给 对 从 到 为 以 于 而 也 就 都 还 又 很 最 更
    一个 一些 什么 怎么 为什么 如何 哪些 哪个 哪里 是否 可以 可能 应该
    吗 呢 吧 啊 哦 嗯 呀 其 之 者 所 因此 所以 但是 如果 因为 然后 以及
    """.split()
)
_STOPWORDS.update(
    "a an the of in on at to for and or is are was were be been being it "
    "this that these those with by as from".split()
)

_CJK_RE = re.compile(r"[\u4e00-\u9fff]+")
_ASCII_RE = re.compile(r"[a-zA-Z0-9_]+")


def tokenize(text: str, remove_stopwords: bool = True) -> List[str]:
    """把文本切成小写 token 列表（中文交给 jieba，英文/数字按词切）。

    Args:
        text: 原始文本。
        remove_stopwords: 是否过滤停用词，测试里可关掉。

    Returns:
        token 列表；空文本返回 []。
    """
    if not text:
        return []

    tokens: List[str] = []
    # 英文/数字：直接按连续字符切，避免混在中文里被 jieba 吞掉。
    tokens.extend(word.lower() for word in _ASCII_RE.findall(text))
    # 中文：只把纯中文片段交给 jieba，避免大小写/数字干扰分词。
    for segment in _CJK_RE.findall(text):
        for word in jieba.lcut(segment):
            word = word.strip()
            if word:
                tokens.append(word)

    if remove_stopwords:
        tokens = [token for token in tokens if token not in _STOPWORDS]
    return tokens


class BM25:
    """Okapi BM25 索引。

    Args:
        corpus_tokens: 每篇文档的 token 列表。
        k1: 词频饱和参数，常用 1.2 ~ 2.0。
        b: 文档长度归一参数，0 ~ 1，常用 0.75。
    """

    def __init__(
        self,
        corpus_tokens: Sequence[Sequence[str]],
        k1: float = 1.5,
        b: float = 0.75,
    ) -> None:
        self.corpus_tokens = [list(doc) for doc in corpus_tokens]
        self.k1 = k1
        self.b = b
        self.n_docs = len(self.corpus_tokens)
        self.doc_len = [len(doc) for doc in self.corpus_tokens]
        self.avgdl = (sum(self.doc_len) / self.n_docs) if self.n_docs else 0.0

        self.term_freqs = [Counter(doc) for doc in self.corpus_tokens]
        doc_freq: Counter = Counter()
        for tf in self.term_freqs:
            doc_freq.update(tf.keys())
        self.doc_freq = doc_freq
        # 加 1 平滑的 IDF，避免高频词出现负权重（语料很小时也不会为负）。
        self.idf = {
            term: math.log(1.0 + (self.n_docs - df + 0.5) / (df + 0.5))
            for term, df in doc_freq.items()
        }

    def score(self, query_tokens: Sequence[str]) -> List[float]:
        """返回查询对每篇文档的 BM25 分数（与 self.corpus_tokens 顺序一致）。"""
        scores = [0.0] * self.n_docs
        if not self.n_docs:
            return scores

        for term in query_tokens:
            idf = self.idf.get(term)
            if idf is None:
                continue
            for i, tf in enumerate(self.term_freqs):
                freq = tf.get(term, 0)
                if not freq:
                    continue
                dl = self.doc_len[i] or 1
                denom = freq + self.k1 * (
                    1.0 - self.b + self.b * dl / (self.avgdl or 1.0)
                )
                scores[i] += idf * freq * (self.k1 + 1.0) / denom
        return scores

    def top_n(self, query_tokens: Sequence[str], n: int = 5) -> List[tuple]:
        """返回分数最高的 n 篇文档 [(doc_index, score)]，过滤 0 分。"""
        ranked = sorted(
            enumerate(self.score(query_tokens)),
            key=lambda item: item[1],
            reverse=True,
        )
        return [(idx, score) for idx, score in ranked[:n] if score > 0]


def build_bm25_index(documents: Sequence[Dict]) -> BM25:
    """从 documents（[{"content": ...}, ...]）构建 BM25 索引。"""
    corpus = [tokenize(str(doc.get("content", ""))) for doc in documents]
    return BM25(corpus)
