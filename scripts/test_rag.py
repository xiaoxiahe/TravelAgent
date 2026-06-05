"""简单的 RAG 手动测试脚本。"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from travel_agent.rag.retriever import MultiQueryRetriever
from travel_agent.rag.vectorstore import ChromaVectorStore


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="测试项目 RAG 检索结果")
    parser.add_argument("query", help="检索查询，例如：日本景点")
    parser.add_argument(
        "--collection",
        default="travel",
        choices=["travel", "restaurant"],
        help="要测试的 Chroma collection",
    )
    parser.add_argument("--top-k", type=int, default=5, help="返回结果数量")
    parser.add_argument(
        "--filter-type",
        default="",
        help="可选 metadata.type 过滤，例如 attraction / note / comment",
    )
    parser.add_argument(
        "--show-content-chars",
        type=int,
        default=180,
        help="每条结果显示的内容长度",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()

    filters = {"type": args.filter_type} if args.filter_type else None
    store = ChromaVectorStore(collection_name=args.collection)
    retriever = MultiQueryRetriever(vector_store=store, top_k=args.top_k)

    print(f"[RAG TEST] collection={args.collection}")
    print(f"[RAG TEST] top_k={args.top_k}")
    print(f"[RAG TEST] query={args.query}")
    print(f"[RAG TEST] filter={json.dumps(filters, ensure_ascii=False) if filters else 'None'}")

    try:
        count = store.count()
        print(f"[RAG TEST] collection_count={count}")
    except Exception as exc:
        print(f"[RAG TEST] failed to count collection: {type(exc).__name__}: {exc}")

    results = retriever.retrieve(args.query, filters=filters)
    print(f"[RAG TEST] results={len(results)}")

    for index, item in enumerate(results, start=1):
        content = (item.content or "").replace("\n", " ").strip()
        preview = content[: args.show_content_chars]
        metadata = item.metadata or {}
        print(f"\n=== Result {index} ===")
        print(f"score={item.score}")
        print(f"source_type={item.source_type}")
        print(f"source_name={item.source_name}")
        print(f"id={item.id}")
        print(f"metadata={json.dumps(metadata, ensure_ascii=False)}")
        print(f"content={preview}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
