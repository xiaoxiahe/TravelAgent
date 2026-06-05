"""导入小红书数据到Chroma向量库（支持笔记内容和评论）"""
import json
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from travel_agent.rag.vectorstore import ChromaVectorStore
from travel_agent.rag.embedder import create_embedder


def extract_city_from_keyword(keyword: str) -> str:
    """从关键词中提取城市名"""
    if not keyword:
        return "未知"
    city = keyword.replace("好吃的餐厅", "").replace("美食推荐", "").strip()
    return city or "未知"


def extract_tags(tag_str: str) -> list:
    """解析标签字符串"""
    if not tag_str:
        return []
    return [t.strip() for t in tag_str.split(",") if t.strip()]


def build_comment_document(comment: dict) -> tuple[str, dict, str]:
    comment_id = comment.get("comment_id", "")
    content = comment.get("content", "")
    author = comment.get("nickname", "")
    ip_location = comment.get("ip_location", "未知")
    like_count = comment.get("like_count", "0")
    note_id = comment.get("note_id", "")

    content_parts = []
    if author:
        content_parts.append(f"用户【{author}】(IP属地:{ip_location})的评论:")
    if content:
        content_parts.append(content)
    full_content = "\n\n".join(content_parts)

    metadata = {
        "type": "comment",
        "note_id": note_id,
        "author": author,
        "ip_location": ip_location,
        "like_count": like_count,
    }
    return full_content, metadata, f"xhs_comment_{comment_id}"


def build_document(note: dict) -> tuple[str, dict, str]:
    note_id = note.get("note_id", "")
    title = note.get("title", "")
    desc = note.get("desc", "")
    city = extract_city_from_keyword(note.get("source_keyword", ""))
    tags = extract_tags(note.get("tag_list", ""))
    author = note.get("nickname", "")
    note_url = note.get("note_url", "")
    liked = note.get("liked_count", "0")
    collected = note.get("collected_count", "0")
    note_type = note.get("type", "normal")

    content_parts = []
    if title:
        content_parts.append(f"【{title}】")
    if desc:
        clean_desc = desc.replace("#", " ").strip()
        content_parts.append(clean_desc[:1000])
    content = "\n\n".join(content_parts)

    metadata = {
        "type": "restaurant",
        "city": city,
        "title": title,
        "tags": ",".join(tags),
        "author": author,
        "url": note_url,
        "liked_count": liked,
        "collected_count": collected,
        "note_type": note_type,
    }
    return content, metadata, f"xhs_{note_id}"


def ingest_restaurant_data(json_path: str, persist_dir: str = "./chroma_db", collection: str = "travel_knowledge"):
    print(f"Loading data from {json_path}...")
    if not os.path.exists(json_path):
        raise FileNotFoundError(f"File not found: {json_path}")

    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    print(f"Loaded {len(data)} items")

    # 判断数据类型
    if data and "comment_id" in data[0]:
        print("Detected: Comment data")
        build_fn = build_comment_document
    else:
        print("Detected: Note content data")
        build_fn = build_document

    # 从环境变量获取 DashScope API Key
    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("[ERROR] DASHSCOPE_API_KEY not found in environment. Please set it first.")
        return

    from travel_agent.rag.embedder import DashScopeEmbedder
    embedder = DashScopeEmbedder(api_key=api_key)

    store = ChromaVectorStore(
        persist_directory=persist_dir,
        collection_name=collection,
        embedder=embedder,
    )

    docs, metas, ids = [], [], []
    seen_ids = {}
    for item in data:
        content, metadata, doc_id = build_fn(item)
        if not content.strip():
            continue

        unique_id = doc_id
        if doc_id in seen_ids:
            seen_ids[doc_id] += 1
            unique_id = f"{doc_id}_{seen_ids[doc_id]}"
        else:
            seen_ids[doc_id] = 0

        docs.append(content)
        metas.append(metadata)
        ids.append(unique_id)

    if docs:
        print(f"Total documents to add: {len(docs)} (with {sum(v for v in seen_ids.values() if v > 0)} duplicate IDs handled)")
        store.add_documents(documents=docs, metadatas=metas, ids=ids)

    print(f"Done! Total documents in collection: {store.count()}")


def test_retrieval(query: str = "北京好吃的餐厅", top_k: int = 3):
    from travel_agent.rag.retriever import RestaurantRetriever

    retriever = RestaurantRetriever()
    results = retriever.retrieve_restaurants(location=query.replace("好吃的餐厅", "").strip() or "北京")
    print(f"Found {len(results)} results")
    for i, r in enumerate(results[:top_k]):
        print(f"[{i+1}] {r.source_name} | {r.metadata.get('city', 'N/A')} | {r.url}")


def test_search(query: str, top_k: int = 5, persist_dir: str = "./chroma_db", collection: str = "travel_knowledge"):
    """通用搜索测试"""
    print(f"\n=== Search Query: {query} ===\n")

    api_key = os.environ.get("DASHSCOPE_API_KEY")
    if not api_key:
        print("[ERROR] DASHSCOPE_API_KEY not found.")
        return

    from travel_agent.rag.embedder import DashScopeEmbedder
    embedder = DashScopeEmbedder(api_key=api_key)

    store = ChromaVectorStore(
        persist_directory=persist_dir,
        collection_name=collection,
        embedder=embedder,
    )

    results = store.search(query=query, top_k=top_k)
    print(f"Found {len(results)} results\n")

    for i, r in enumerate(results):
        print(f"--- Result {i+1} ---")
        print(f"Type: {r['metadata'].get('type', 'unknown')}")
        print(f"Score: {r.get('distance', 'N/A')}")
        print(f"Content: {r['content'][:200]}...")
        print(f"Metadata: {json.dumps(r['metadata'], ensure_ascii=False, indent=2)}")
        print()


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Import data to vector store and test search")
    parser.add_argument("--json", help="JSON file path to import")
    parser.add_argument("--dir", default="./chroma_db", help="Chroma persist directory")
    parser.add_argument("--collection", default="travel_knowledge", help="Collection name")
    parser.add_argument("--query", help="Search query to test")
    parser.add_argument("--top-k", type=int, default=5, help="Number of results to return")
    parser.add_argument("--test", action="store_true", help="Run built-in retrieval test after import")
    args = parser.parse_args()

    if args.json:
        ingest_restaurant_data(args.json, args.dir, args.collection)

    if args.query:
        test_search(query=args.query, top_k=args.top_k, persist_dir=args.dir, collection=args.collection)
    elif args.test:
        test_retrieval()
