"""rag_bm25 单元测试（BUG-01 修复的回归保护）。

运行：
    python -m pytest tests -q
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_bm25 import BM25, build_bm25_index, tokenize  # noqa: E402


def test_tokenize_chinese_keeps_meaningful_terms():
    tokens = tokenize("中文关键词检索为什么失效")
    assert "关键词" in tokens
    assert "检索" in tokens
    assert "失效" in tokens
    # 停用词应被过滤
    assert "为什么" not in tokens
    assert "的" not in tokens


def test_tokenize_english_lowercases_and_drops_stopwords():
    tokens = tokenize("Retrieval Augmented Generation for LLMs")
    assert "retrieval" in tokens
    assert "augmented" in tokens
    assert "llms" in tokens
    assert "for" not in tokens


def test_tokenize_mixed_text():
    tokens = tokenize("RAG的召回率 recall 怎么评估")
    assert "rag" in tokens
    assert "recall" in tokens
    assert "召回率" in tokens or "召回" in tokens


def test_tokenize_empty():
    assert tokenize("") == []
    assert tokenize("   ") == []


def test_bm25_chinese_ranks_matching_doc_first():
    documents = [
        {"content": "中文关键词检索为什么失效，因为分词没有生效"},
        {"content": "向量检索依赖嵌入模型"},
        {"content": "Streamlit 页面布局与按钮"},
    ]
    index = build_bm25_index(documents)
    scores = index.score(tokenize("关键词检索失效"))

    assert scores[0] > 0.0
    assert scores[0] > scores[1]
    assert scores[0] > scores[2]


def test_bm25_no_overlap_returns_zero():
    documents = [
        {"content": "中文关键词检索为什么失效"},
        {"content": "向量检索依赖嵌入模型"},
    ]
    index = build_bm25_index(documents)
    scores = index.score(tokenize("考勤系统"))
    assert all(score == 0.0 for score in scores)


def test_bm25_empty_query_returns_zero():
    documents = [{"content": "中文关键词检索"}, {"content": "向量检索"}]
    index = build_bm25_index(documents)
    assert index.score(tokenize("")) == [0.0, 0.0]


def test_bm25_empty_corpus():
    index = BM25([])
    assert index.score(["rag"]) == []


def test_bm25_term_frequency_helps_ranking():
    # 相同长度下，同一词出现两次的文档应比出现一次的高分。
    documents = [
        {"content": "检索 检索 方法"},
        {"content": "检索 方法 模型"},
        {"content": "完全无关的内容"},
    ]
    index = BM25([tokenize(doc["content"]) for doc in documents])
    scores = index.score(tokenize("检索"))
    assert scores[0] > scores[1] > scores[2]


def test_bm25_top_n_filters_zero_scores():
    documents = [
        {"content": "中文关键词检索为什么失效"},
        {"content": "向量检索依赖嵌入模型"},
        {"content": "完全无关的文本"},
    ]
    index = build_bm25_index(documents)
    ranked = index.top_n(tokenize("关键词"), n=3)
    assert len(ranked) == 1
    assert ranked[0][0] == 0
    assert ranked[0][1] > 0
