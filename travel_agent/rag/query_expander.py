"""查询扩展模块"""
from typing import List, Dict, Any
import re


class QueryExpander:
    """查询扩展器 - 扩展检索关键词"""

    # 同义词映射
    SYNONYMS = {
        "景点": ["观光", "旅游", "游玩", "打卡", "必去"],
        "餐厅": ["美食", "吃饭", "餐饮", "料理", "食堂"],
        "购物": ["商场", "免税", "买买买", "购物"],
        "酒店": ["住宿", "旅馆", "民宿", "客栈"],
        "交通": ["出行", "交通", "怎么去", "路线"],
    }

    # 日本相关扩展词
    JAPAN_EXTENSIONS = {
        "东京": ["Tokyo", "东京都", "关东"],
        "大阪": ["Osaka", "关西"],
        "京都": ["Kyoto"],
        "北海道": ["Hokkaido"],
        "冲绳": ["Okinawa"],
    }

    # 旅行类型相关词
    TRAVEL_TYPE_KEYWORDS = {
        "蜜月旅行": ["浪漫", "情侣", "私密", "海景"],
        "家庭出游": ["亲子", "儿童", "适合全家", "安全"],
        "独自旅行": ["一个人", "自由行", "背包客"],
        "朋友团建": ["热闹", "聚餐", "酒吧", "娱乐"],
        "商务旅行": ["商务", "高端", "便利"],
        "亲子游": ["儿童", "亲子", "乐园"],
    }

    def __init__(self):
        self.destination_keywords = {}  # 目的地特定关键词

    def expand(self, query: str, context: Dict[str, Any] = None) -> List[str]:
        """扩展查询，返回多个检索词"""
        queries = [query]

        # 添加目的地扩展
        destination = context.get("destination", "") if context else ""
        if destination in self.JAPAN_EXTENSIONS:
            queries.extend(self.JAPAN_EXTENSIONS[destination])

        # 添加旅行类型相关词
        travel_type = context.get("travel_type", "") if context else ""
        if travel_type in self.TRAVEL_TYPE_KEYWORDS:
            for kw in self.TRAVEL_TYPE_KEYWORDS[travel_type]:
                queries.append(f"{query} {kw}")

        # 添加类型词扩展
        for base_word, synonyms in self.SYNONYMS.items():
            if base_word in query:
                for syn in synonyms:
                    new_query = query.replace(base_word, syn)
                    if new_query not in queries:
                        queries.append(new_query)

        # 添加价格相关词
        price_range = context.get("price_range", "") if context else ""
        if price_range:
            price_keywords = {
                "经济实惠": ["便宜", "性价比", "划算"],
                "适中": ["中等", "普通"],
                "高端": ["高级", "奢华", "米其林"],
            }
            if price_range in price_keywords:
                for kw in price_keywords[price_range]:
                    queries.append(f"{query} {kw}")

        # 去重
        return list(set(queries))

    def expand_for_restaurant(self, base_query: str, scene: str = None) -> List[str]:
        """为餐厅搜索扩展查询"""
        queries = [base_query]

        # 场景相关扩展
        scene_extensions = {
            "business_dinner": ["商务", "宴请", "包间", "高端"],
            "date_night": ["约会", "浪漫", "氛围", "烛光"],
            "family_meal": ["家庭", "聚餐", "分量足"],
            "quick_bite": ["快餐", "小吃", "便捷"],
            "special_occasion": ["纪念日", "生日", "米其林"],
        }

        if scene and scene in scene_extensions:
            for ext in scene_extensions[scene]:
                queries.append(f"{base_query} {ext}")

        # 添加常见搜索词
        queries.extend([
            f"{base_query} 推荐",
            f"{base_query} 必吃",
            f"{base_query} 攻略",
        ])

        return list(set(queries))

    def expand_for_attraction(self, base_query: str, travel_type: str = None) -> List[str]:
        """为景点搜索扩展查询"""
        queries = [base_query]

        # 景点类型扩展
        attraction_extensions = {
            "自然": ["风景", "自然风光", "公园"],
            "人文": ["历史", "文化", "古迹"],
            "购物": ["商场", "免税店", "药妆"],
            "娱乐": ["乐园", "博物馆", "温泉"],
        }

        # 添加热门标签
        queries.extend([
            f"{base_query} 攻略",
            f"{base_query} 小红书",
            f"{base_query} 推荐",
            f"{base_query} 打卡",
        ])

        return list(set(queries))

    def clean_query(self, query: str) -> str:
        """清理查询文本"""
        # 移除特殊字符
        query = re.sub(r'[^\w\s\u4e00-\u9fff]', ' ', query)
        # 移除多余空格
        query = re.sub(r'\s+', ' ', query)
        return query.strip()


class QueryParser:
    """查询解析器 - 解析用户输入"""

    # 目的地模式
    DESTINATION_PATTERNS = [
        r"去(.+?)(?:旅游|玩|旅行)",
        r"到(.+?)(?:旅游|玩|旅行)",
        r"去(.+?)玩",
        r"想去(.+?)",
    ]

    # 预算模式
    BUDGET_PATTERNS = [
        r"预算[是为]*(\d+)",  # 预算为3000
        r"花(\d+)",  # 花3000
        r"¥?(\d+)[万千]?",  # 3000或3万
    ]

    def parse(self, text: str) -> Dict[str, Any]:
        """解析文本，提取关键信息"""
        result = {
            "destination": None,
            "duration": None,
            "budget": None,
            "original_text": text,
        }

        # 提取目的地
        for pattern in self.DESTINATION_PATTERNS:
            match = re.search(pattern, text)
            if match:
                result["destination"] = match.group(1)
                break

        # 提取预算
        for pattern in self.BUDGET_PATTERNS:
            match = re.search(pattern, text)
            if match:
                budget_str = match.group(1)
                # 处理"万"
                if "万" in text[match.start():match.end()]:
                    result["budget"] = int(budget_str) * 10000
                else:
                    result["budget"] = int(budget_str)
                break

        # 提取天数
        duration_match = re.search(r"(\d+)天", text)
        if duration_match:
            result["duration"] = int(duration_match.group(1))

        return result
