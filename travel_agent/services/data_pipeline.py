"""数据管道 - 从爬虫数据到向量数据库"""
import json
import os
from typing import List, Dict, Any, Optional
from pathlib import Path

from travel_agent.models.attraction import Attraction
from travel_agent.models.restaurant import Restaurant
from travel_agent.models.hotel import Hotel
from travel_agent.rag.vectorstore import ChromaVectorStore, init_vector_store


class DataPipeline:
    """数据处理管道"""

    def __init__(
        self,
        data_dir: str = "./data",
        chroma_dir: str = "./chroma_db"
    ):
        self.data_dir = Path(data_dir)
        self.chroma_dir = Path(chroma_dir)

    def load_xhs_notes(self, source_dir: Optional[str] = None) -> List[Dict[str, Any]]:
        """加载小红书笔记数据"""
        source = Path(source_dir) if source_dir else self.data_dir / "raw" / "xhs"

        if not source.exists():
            print(f"数据目录不存在: {source}")
            return []

        notes = []

        # 查找所有JSON文件
        for json_file in source.glob("*.json"):
            try:
                with open(json_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if isinstance(data, list):
                        notes.extend(data)
                    else:
                        notes.append(data)
            except Exception as e:
                print(f"加载文件失败 {json_file}: {e}")

        return notes

    def extract_attractions(self, notes: List[Dict[str, Any]]) -> List[Attraction]:
        """从笔记中提取景点信息"""
        attractions = []
        seen_ids = set()

        for note in notes:
            # 提取景点信息
            content = note.get("desc", "") + " " + note.get("title", "")

            # 简单关键词匹配识别景点
            keywords = ["景点", "打卡", "必去", "观光", "游玩", "神社", "寺庙", "公园", "塔", "城"]
            if any(kw in content for kw in keywords) or note.get("type") == "normal":
                # 创建景点对象
                attraction = Attraction(
                    id=note.get("note_id", f"xhs_{len(attractions)}"),
                    name=note.get("title", "未知景点"),
                    location=note.get("last_location", ""),
                    city=self._extract_city(note.get("last_location", "")),
                    category="景点",
                    tags=note.get("tag_list", []),
                    description=note.get("desc", ""),
                    rating=float(note.get("liked_count", 0)) / 1000 if note.get("liked_count") else 0,
                    review_count=int(note.get("comment_count", 0)) if note.get("comment_count") else 0,
                    source_url=f"https://www.xiaohongshu.com/explore/{note.get('note_id', '')}",
                    source_note_id=note.get("note_id", "")
                )

                if attraction.id not in seen_ids:
                    attractions.append(attraction)
                    seen_ids.add(attraction.id)

        return attractions

    def extract_restaurants(self, notes: List[Dict[str, Any]]) -> List[Restaurant]:
        """从笔记中提取餐厅信息"""
        restaurants = []
        seen_ids = set()

        for note in notes:
            content = note.get("desc", "") + " " + note.get("title", "")

            # 识别餐厅关键词
            food_keywords = ["餐厅", "美食", "好吃", "拉面", "寿司", "烤肉", "火锅", "料理", "咖啡", "甜品"]
            if any(kw in content for kw in food_keywords):
                restaurant = Restaurant(
                    id=note.get("note_id", f"xhs_rest_{len(restaurants)}"),
                    name=note.get("title", "未知餐厅"),
                    location=note.get("last_location", ""),
                    city=self._extract_city(note.get("last_location", "")),
                    cuisine_type=self._guess_cuisine_type(content),
                    rating=float(note.get("liked_count", 0)) / 1000 if note.get("liked_count") else 0,
                    review_count=int(note.get("comment_count", 0)) if note.get("comment_count") else 0,
                    positive_reviews=[note.get("desc", "")[:100]],
                    source_url=f"https://www.xiaohongshu.com/explore/{note.get('note_id', '')}",
                    source_note_id=note.get("note_id", "")
                )

                if restaurant.id not in seen_ids:
                    restaurants.append(restaurant)
                    seen_ids.add(restaurant.id)

        return restaurants

    def _extract_city(self, location: str) -> str:
        """提取城市名"""
        # 简单实现，实际应该用更智能的方法
        cities = ["东京", "大阪", "京都", "北海道", "冲绳", "横滨", "名古屋", "神户", "福冈"]
        for city in cities:
            if city in location:
                return city
        return location if location else "未知"

    def _guess_cuisine_type(self, content: str) -> str:
        """猜测菜系"""
        cuisine_map = {
            "拉面": "日式拉面",
            "寿司": "寿司",
            "烤肉": "烧肉",
            "刺身": "刺身",
            "天妇罗": "天妇罗",
            "咖喱": "咖喱",
            "咖啡": "咖啡厅",
            "甜品": "甜品",
        }
        for kw, cuisine in cuisine_map.items():
            if kw in content:
                return cuisine
        return "其他"

    def process_and_index(
        self,
        source_dir: Optional[str] = None,
        collection_name: str = "travel_knowledge"
    ) -> Dict[str, int]:
        """处理数据并索引到向量数据库"""
        # 加载数据
        notes = self.load_xhs_notes(source_dir)
        print(f"加载了 {len(notes)} 条笔记")

        # 提取实体
        attractions = self.extract_attractions(notes)
        restaurants = self.extract_restaurants(notes)
        print(f"提取了 {len(attractions)} 个景点，{len(restaurants)} 个餐厅")

        # 初始化向量数据库
        vector_store = init_vector_store(
            persist_directory=str(self.chroma_dir),
            collection_name=collection_name
        )

        # 添加到向量库
        doc_count = 0

        # 添加景点
        for attraction in attractions:
            vector_store.add_documents(
                documents=[attraction.to_search_text()],
                metadatas=[{
                    "type": "attraction",
                    "name": attraction.name,
                    "location": attraction.location,
                    "city": attraction.city,
                    "category": attraction.category,
                    "rating": attraction.rating,
                    "source_url": attraction.source_url,
                    "id": attraction.id,
                }],
                ids=[attraction.id]
            )
            doc_count += 1

        # 添加餐厅
        for restaurant in restaurants:
            vector_store.add_documents(
                documents=[restaurant.to_search_text()],
                metadatas=[{
                    "type": "restaurant",
                    "name": restaurant.name,
                    "location": restaurant.location,
                    "city": restaurant.city,
                    "cuisine_type": restaurant.cuisine_type,
                    "rating": restaurant.rating,
                    "price_range": restaurant.price_range,
                    "source_url": restaurant.source_url,
                    "id": restaurant.id,
                }],
                ids=[restaurant.id]
            )
            doc_count += 1

        print(f"已索引 {doc_count} 个文档到 {collection_name}")

        return {
            "notes_loaded": len(notes),
            "attractions": len(attractions),
            "restaurants": len(restaurants),
            "total_indexed": doc_count,
        }


def run_pipeline(
    data_dir: str = "./data",
    chroma_dir: str = "./chroma_db",
    collection_name: str = "travel_knowledge"
):
    """运行数据管道"""
    pipeline = DataPipeline(data_dir=data_dir, chroma_dir=chroma_dir)
    return pipeline.process_and_index(collection_name=collection_name)


if __name__ == "__main__":
    result = run_pipeline()
    print("处理完成:", result)
