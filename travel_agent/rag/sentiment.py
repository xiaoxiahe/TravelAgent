"""情感分析模块"""
from typing import List, Dict, Any, Optional
import re


class SentimentAnalyzer:
    """情感分析器"""

    # 正面词汇
    POSITIVE_WORDS = {
        "好吃", "美味", "棒", "推荐", "必吃", "超赞", "绝绝子", "爱了",
        "惊艳", "完美", "良心", "宝藏", "yyds", "绝了", "太可了",
        "满意", "开心", "惊喜", "值得", "划算", "性价比", "良心价",
        "方便", "舒适", "干净", "整洁", "漂亮", "美", "nice",
        "热情", "贴心", "周到", "服务好", "态度好", "专业"
    }

    # 负面词汇
    NEGATIVE_WORDS = {
        "踩雷", "坑", "难吃", "失望", "不值", "后悔", "别去", "避雷",
        "脏", "差", "烂", "骗人", "欺诈", "虚假", "营销", "广告",
        "排队", "久等", "人多", "嘈杂", "拥挤", "吵", "乱",
        "贵", "宰客", "不值", "性价比低", "被坑", "套路"
    }

    # 营销识别词
    MARKETING_WORDS = {
        "广告", "推广", "赞助", "合作", "恰饭", "植入",
        "软文", "营销号", "买手", "代购", "引流"
    }

    def __init__(self, model_name: str = None):
        self.model_name = model_name
        self._model = None

    def _load_model(self):
        """延迟加载模型"""
        if self._model is None and self.model_name:
            try:
                from transformers import pipeline
                self._model = pipeline(
                    "sentiment-analysis",
                    model=self.model_name,
                    truncation=True,
                    max_length=512
                )
            except ImportError:
                pass

    def analyze(self, text: str) -> float:
        """
        分析文本情感，返回 -1 到 1 之间的分数
        -1: 完全负面
         0: 中性
         1: 完全正面
        """
        if not text:
            return 0

        # 基于规则的分析
        rule_score = self._rule_based_analysis(text)

        # 如果有预训练模型，尝试使用
        if self._model:
            try:
                ml_result = self._model(text[:512])[0]
                ml_score = 1 if ml_result["label"] == "POSITIVE" else -1
                ml_score *= ml_result["score"]
                # 融合规则和ML结果
                return rule_score * 0.3 + ml_score * 0.7
            except Exception:
                pass

        return rule_score

    def _rule_based_analysis(self, text: str) -> float:
        """基于规则的情感分析"""
        text_lower = text.lower()

        # 统计正负面词出现次数
        pos_count = sum(1 for word in self.POSITIVE_WORDS if word in text)
        neg_count = sum(1 for word in self.NEGATIVE_WORDS if word in text)

        total = pos_count + neg_count
        if total == 0:
            return 0

        # 计算情感分数
        score = (pos_count - neg_count) / total

        return max(-1, min(1, score))  # 限制在 [-1, 1]

    def is_marketing(self, text: str) -> bool:
        """判断是否为营销内容"""
        # 出现多个营销词
        marketing_count = sum(1 for word in self.MARKETING_WORDS if word in text)

        # 检查链接密度（营销内容通常链接较多）
        link_density = text.count("http") / max(len(text), 1)

        # 检查图片提及（"图1"、"实拍"等）
        photo_mentions = len(re.findall(r"[图图123456789]+", text))

        # 综合判断
        if marketing_count >= 2:
            return True
        if link_density > 0.01:
            return True
        if marketing_count >= 1 and photo_mentions >= 3:
            return True

        return False

    def calculate_authenticity(self, text: str) -> float:
        """
        计算内容真实度 0-1
        越接近1表示越真实（非营销）
        """
        if self.is_marketing(text):
            return 0.3

        # 检查是否有具体细节（真实内容通常有细节）
        has_numbers = bool(re.search(r"\d+", text))  # 数字
        has_time_words = bool(re.search(r"[时分秒天周月年]", text))  # 时间词
        has_location_words = bool(re.search(r"[街路号栋楼座层]", text))  # 地址词

        detail_score = (
            (0.2 if has_numbers else 0) +
            (0.2 if has_time_words else 0) +
            (0.2 if has_location_words else 0)
        )

        # 情感适中度（过于正面或负面可能不真实）
        sentiment = abs(self.analyze(text))
        if 0.3 <= sentiment <= 0.8:
            detail_score += 0.2

        return min(1, detail_score + 0.2)


class BatchSentimentAnalyzer:
    """批量情感分析器"""

    def __init__(self, analyzer: SentimentAnalyzer = None):
        self.analyzer = analyzer or SentimentAnalyzer()

    def analyze_batch(
        self,
        texts: List[str],
        return_details: bool = False
    ) -> List[Dict[str, Any]]:
        """批量分析"""
        results = []

        for text in texts:
            sentiment = self.analyzer.analyze(text)
            authenticity = self.analyzer.calculate_authenticity(text)
            is_marketing = self.analyzer.is_marketing(text)

            result = {
                "sentiment": sentiment,
                "authenticity": authenticity,
                "is_marketing": is_marketing,
                "quality_score": sentiment * 0.6 + authenticity * 0.4
            }

            if return_details:
                result["details"] = {
                    "word_count": len(text),
                    "positive_count": sum(1 for w in self.analyzer.POSITIVE_WORDS if w in text),
                    "negative_count": sum(1 for w in self.analyzer.NEGATIVE_WORDS if w in text),
                }

            results.append(result)

        return results

    def summarize_sentiment(self, texts: List[str]) -> Dict[str, Any]:
        """总结一组文本的情感"""
        batch_results = self.analyze_batch(texts)

        sentiments = [r["sentiment"] for r in batch_results]
        authenticities = [r["authenticity"] for r in batch_results]

        return {
            "avg_sentiment": sum(sentiments) / len(sentiments) if sentiments else 0,
            "avg_authenticity": sum(authenticities) / len(authenticities) if authenticities else 0,
            "positive_ratio": sum(1 for s in sentiments if s > 0.3) / len(sentiments) if sentiments else 0,
            "negative_ratio": sum(1 for s in sentiments if s < -0.3) / len(sentiments) if sentiments else 0,
            "marketing_ratio": sum(1 for r in batch_results if r["is_marketing"]) / len(batch_results) if batch_results else 0,
            "overall_score": (
                sum(r["quality_score"] for r in batch_results) / len(batch_results)
                if batch_results else 0
            )
        }
