"""爬虫调度服务"""
import asyncio
from typing import List, Dict, Any, Optional
import json
from pathlib import Path

from LittleCrawler.config import base_config
from LittleCrawler.src.platforms.xhs.core import XiaoHongShuCrawler


class CrawlerService:
    """爬虫调度服务"""

    def __init__(self):
        self.crawler = None
        self.data_dir = Path("./data/raw/xhs")
        self.data_dir.mkdir(parents=True, exist_ok=True)

    async def init_crawler(self):
        """初始化爬虫"""
        if self.crawler is None:
            self.crawler = XiaoHongShuCrawler()
            await self.crawler.init()

    async def search_notes(
        self,
        keywords: List[str],
        max_pages: int = 5,
        sort: str = "general"
    ) -> List[Dict[str, Any]]:
        """
        搜索笔记

        Args:
            keywords: 关键词列表
            max_pages: 最大页数
            sort: 排序方式

        Returns:
            笔记列表
        """
        await self.init_crawler()

        all_notes = []

        for keyword in keywords:
            print(f"正在搜索: {keyword}")

            try:
                notes = await self.crawler.get_note_by_keyword(
                    keyword=keyword,
                    page=1,
                    max_pages=max_pages,
                    sort=sort
                )
                all_notes.extend(notes)

                # 保存数据
                self._save_notes(keyword, notes)

            except Exception as e:
                print(f"搜索 {keyword} 失败: {e}")

        return all_notes

    async def get_note_details(self, note_ids: List[str]) -> List[Dict[str, Any]]:
        """获取笔记详情"""
        await self.init_crawler()

        details = []
        for note_id in note_ids:
            try:
                detail = await self.crawler.get_note_detail(note_id)
                if detail:
                    details.append(detail)
            except Exception as e:
                print(f"获取笔记 {note_id} 详情失败: {e}")

        return details

    async def search_restaurants(
        self,
        destination: str,
        max_pages: int = 3
    ) -> List[Dict[str, Any]]:
        """搜索餐厅相关笔记"""
        keywords = [
            f"{destination} 餐厅",
            f"{destination} 美食",
            f"{destination} 必吃",
            f"{destination} 小吃",
            f"{destination} 网红餐厅",
        ]
        return await self.search_notes(keywords, max_pages=max_pages)

    async def search_attractions(
        self,
        destination: str,
        max_pages: int = 3
    ) -> List[Dict[str, Any]]:
        """搜索景点相关笔记"""
        keywords = [
            f"{destination} 景点",
            f"{destination} 必去",
            f"{destination} 打卡",
            f"{destination} 攻略",
            f"{destination} 观光",
        ]
        return await self.search_notes(keywords, max_pages=max_pages)

    def _save_notes(self, keyword: str, notes: List[Dict[str, Any]]):
        """保存笔记到文件"""
        if not notes:
            return

        filename = self.data_dir / f"{keyword}_{len(notes)}.json"
        with open(filename, "w", encoding="utf-8") as f:
            json.dump(notes, f, ensure_ascii=False, indent=2)

        print(f"已保存 {len(notes)} 条笔记到 {filename}")

    def load_saved_notes(self, keyword: str = None) -> List[Dict[str, Any]]:
        """加载已保存的笔记"""
        notes = []

        if keyword:
            pattern = f"*{keyword}*.json"
        else:
            pattern = "*.json"

        for json_file in self.data_dir.glob(pattern):
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


# 全局实例
_crawler_service: Optional[CrawlerService] = None


def get_crawler_service() -> CrawlerService:
    """获取爬虫服务实例"""
    global _crawler_service
    if _crawler_service is None:
        _crawler_service = CrawlerService()
    return _crawler_service


async def crawl_destination(destination: str, max_pages: int = 3) -> Dict[str, List]:
    """
    爬取目的地的相关数据

    Returns:
        {
            "attractions": [...],
            "restaurants": [...],
        }
    """
    service = get_crawler_service()

    # 并行爬取景点和餐厅
    attractions, restaurants = await asyncio.gather(
        service.search_attractions(destination, max_pages),
        service.search_restaurants(destination, max_pages)
    )

    return {
        "attractions": attractions,
        "restaurants": restaurants,
    }
