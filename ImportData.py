import os
import json
from typing import List, Dict, Any
from VectorDB import VectorDB
from langchain_community.embeddings import HuggingFaceBgeEmbeddings
from langchain_core.documents import Document
from dotenv import load_dotenv

load_dotenv()

DATA_PATH = "data/xiaohongshu.json"
CATEGORY = "travel"


def load_json_file(file_path: str) -> List[Dict[str, Any]]:
    if not os.path.exists(file_path):
        print(f"文件不存在: {file_path}")
        return []
    with open(file_path, "r", encoding="utf-8") as f:
        return json.load(f)


def _parse_liked(liked_str: str) -> int:
    try:
        if "万" in liked_str:
            return float(liked_str.replace("万", "")) * 10000
        return float(liked_str)
    except Exception:
        return 0


def note_to_document(note: Dict[str, Any]) -> Document:
    page_content = note.get("desc", "") or note.get("title", "")
    metadata = {
        "note_id": note.get("note_id", ""),
        "title": note.get("title", ""),
        "source": note.get("ip_location", ""),
        "liked_count": _parse_liked(str(note.get("liked_count", 0))),
        "type": note.get("type", ""),
    }
    return Document(page_content=page_content, metadata=metadata)


async def import_from_files(
    content_files: List[str],
    comment_files: List[str],
    collection_name: str = "travel",
):
    print(f"开始导入数据到 {collection_name}")
    embedding = HuggingFaceBgeEmbeddings(
        model_name=os.getenv("EMBEDDING_MODEL"),
        model_kwargs={"device": "cpu"},
        encode_kwargs={"normalize_embeddings": True},
    )
    vector_db = VectorDB(collection_name=collection_name, embedding_function=embedding)

    all_content_docs = []
    for file in content_files:
        all_content_docs.extend(load_json_file(file))

    all_comment_docs = []
    for file in comment_files:
        if file:
            all_comment_docs.extend(load_json_file(file))

    documents: List[Document] = []
    ids: List[str] = []
    for note in all_content_docs:
        doc = note_to_document(note)
        note_id = note.get("note_id", "")
        if not note_id:
            continue
        documents.append(doc)
        ids.append(note_id)

    if documents:
        vector_db.add_documents(documents, ids)
        print(f"导入内容数据完成: {len(documents)} 条")
    else:
        print(f"没有可导入的内容数据")
