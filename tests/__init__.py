"""Travel Agent 测试用例"""
import pytest
from unittest.mock import MagicMock, patch

from travel_agent.models.user_profile import UserProfile, FoodPreferences
from travel_agent.models.attraction import Attraction
from travel_agent.models.restaurant import Restaurant
from travel_agent.models.trip_plan import TripPlan, DayPlan, TimeSlot
from travel_agent.agent.state import AgentState, Stages, Message
from travel_agent.rag.query_expander import QueryExpander, QueryParser
from travel_agent.rag.sentiment import SentimentAnalyzer


class TestModels:
    """测试数据模型"""

    def test_user_profile(self):
        """测试用户画像"""
        profile = UserProfile(
            destination="东京",
            travel_type="家庭出游",
            duration_days=5,
            budget_total=10000
        )

        assert profile.destination == "东京"
        assert profile.travel_type == "家庭出游"
        assert profile.duration_days == 5
        assert profile.budget_total == 10000

    def test_user_profile_is_info_sufficient(self):
        """测试信息是否足够"""
        profile = UserProfile(
            destination="东京",
            travel_type="家庭出游",
            duration_days=5,
            budget_total=10000
        )

        # 初始信息不足
        assert not profile.is_info_sufficient()

        # 设置info_stage
        profile.info_stage = 5
        assert profile.is_info_sufficient()

    def test_attraction(self):
        """测试景点模型"""
        attraction = Attraction(
            id="test_1",
            name="浅草寺",
            location="东京",
            city="东京",
            category="景点",
            tags=["寺庙", "打卡"]
        )

        assert attraction.name == "浅草寺"
        assert "寺庙" in attraction.tags

    def test_restaurant(self):
        """测试餐厅模型"""
        restaurant = Restaurant(
            id="rest_1",
            name="一兰拉面",
            location="东京",
            city="东京",
            cuisine_type="日式拉面",
            price_level="适中"
        )

        assert restaurant.name == "一兰拉面"
        assert restaurant.cuisine_type == "日式拉面"

    def test_trip_plan(self):
        """测试行程计划"""
        day_plan = DayPlan(
            day=1,
            theme="经典打卡",
            morning=TimeSlot(
                time_range="09:00-12:00",
                place_name="浅草寺",
                place_type="景点"
            )
        )

        trip_plan = TripPlan(
            destination="东京",
            duration="5天4晚",
            daily_plans=[day_plan]
        )

        assert trip_plan.destination == "东京"
        assert len(trip_plan.daily_plans) == 1
        assert trip_plan.daily_plans[0].morning.place_name == "浅草寺"


class TestQueryExpander:
    """测试查询扩展器"""

    def test_expand(self):
        """测试查询扩展"""
        expander = QueryExpander()
        queries = expander.expand("东京景点", {"travel_type": "家庭出游"})

        assert "东京景点" in queries
        assert len(queries) > 1

    def test_query_parser(self):
        """测试查询解析"""
        parser = QueryParser()

        # 测试目的地提取
        result = parser.parse("我想去东京旅游")
        assert result["destination"] == "东京"

        # 测试预算提取
        result = parser.parse("预算5000去东京")
        assert result["budget"] == 5000

        # 测试天数提取
        result = parser.parse("去东京玩3天")
        assert result["duration"] == 3


class TestSentimentAnalyzer:
    """测试情感分析"""

    def test_positive_sentiment(self):
        """测试正面情感"""
        analyzer = SentimentAnalyzer()
        score = analyzer.analyze("这家餐厅太好吃了！强烈推荐！")

        assert score > 0

    def test_negative_sentiment(self):
        """测试负面情感"""
        analyzer = SentimentAnalyzer()
        score = analyzer.analyze("踩雷了，非常难吃，强烈不推荐！")

        assert score < 0

    def test_marketing_detection(self):
        """测试营销内容识别"""
        analyzer = SentimentAnalyzer()

        # 正常内容
        assert not analyzer.is_marketing("这家拉面很好吃，汤底浓郁，面条劲道")

        # 营销内容
        assert analyzer.is_marketing("广告推广合作，链接见主页，买手代购引流")


class TestAgentState:
    """测试Agent状态"""

    def test_initial_state(self):
        """测试初始状态"""
        from travel_agent.agent.graph import TravelAgent

        agent = TravelAgent()
        state = agent.get_initial_state()

        assert state["current_stage"] == Stages.WELCOME
        assert state["user_profile"] is None
        assert len(state["messages"]) == 0


class TestMessage:
    """测试消息"""

    def test_message_creation(self):
        """测试消息创建"""
        msg = Message(
            role="assistant",
            content="请问您想去哪里旅行？",
            is_question=True
        )

        assert msg.role == "assistant"
        assert msg.is_question is True


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
