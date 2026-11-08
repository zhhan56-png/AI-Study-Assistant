"""BUG-01 修复前后对比探针。

用途：用同一份示例语料，对比
- 原实现（query.lower().split() + 词重叠率）
- 新实现（jieba 分词 + BM25）
在中文查询下的关键词检索得分，作为 docs/DEBUG-REPORT.md 的复现证据。

运行：
    python scripts/probe_keyword_search.py
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from rag_bm25 import build_bm25_index, tokenize  # noqa: E402


DOCUMENTS = [
    {
        "content": "中文关键词检索为什么失效？因为代码用空格切词，"
        "中文问题会被当成一个 token，关键词得分为零，混合检索退化为纯向量检索。"
    },
    {
        "content": "向量检索依赖嵌入模型，把文本编码成向量后计算余弦相似度。"
        "Embedding 模型的质量直接决定召回效果。"
    },
    {
        "content": "Streamlit 是一个快速构建数据应用的 Python 框架，"
        "本项目用它做聊天界面和侧边栏设置。"
    },
]

QUERIES = [
    "中文关键词检索为什么失效",
    "关键词检索",
    "RAG 的召回率怎么评估",
    "Streamlit 界面",
    "考勤系统",
]


def old_keyword_search(query, documents):
    """原实现（app.py 修复前）：按空格切词 + 词重叠率。"""
    query_words = set(query.lower().split())
    scores = {}
    for i, doc in enumerate(documents):
        doc_words = set(doc["content"].lower().split())
        score = (
            len(query_words.intersection(doc_words)) / len(query_words)
            if query_words
            else 0.0
        )
        scores[str(i)] = score
    return scores


def new_keyword_search(query, documents, index):
    """新实现：jieba 分词 + BM25。"""
    scores = index.score(tokenize(query))
    return {str(i): score for i, score in enumerate(scores)}


def print_row(label, scores):
    formatted = ", ".join(f"doc{k}={v:.4f}" for k, v in scores.items())
    print(f"  {label:<12}{formatted}")


def main():
    index = build_bm25_index(DOCUMENTS)

    print("=" * 78)
    print("BUG-01 关键词检索前后对比（同一语料、同一查询）")
    print("=" * 78)
    for query in QUERIES:
        print(f"\n查询：{query!r}")
        print(f"  jieba 分词：{tokenize(query)}")
        print_row("旧(split)", old_keyword_search(query, DOCUMENTS))
        print_row("新(BM25)", new_keyword_search(query, DOCUMENTS, index))

    print("\n" + "=" * 78)
    print("结论：旧实现下中文查询几乎全为 0，关键词检索形同虚设；")
    print("      BM25 能正确命中包含相关术语的文档，并给出可比较的分数。")
    print("=" * 78)


if __name__ == "__main__":
    main()
