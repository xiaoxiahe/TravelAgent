"""LangGraph状态定义"""
from typing import List, Dict, Any, Optional, Literal, TypedDict
from langgraph.graph import add_messages
from pydantic import BaseModel, Field

from travel_agent.models.user_profile import UserProfile
from travel_agent.models.trip_plan import TripPlan


class Message(BaseModel):
    """对话消息"""
    role: Literal["user", "assistant", "system"]
    content: str
    options: Optional[List[Dict[str, Any]]] = None  # 可选的选项按钮
    is_question: bool = False


class AgentState(TypedDict, total=False):
    """Agent主状态"""

    # 对话历史
    messages: List[Message]

    # 用户画像
    user_profile: Optional[UserProfile]

    # 当前问题阶段
    current_stage: int

    # 收集到的回答
    answers: Dict[str, Any]

    # 是否信息足够
    info_sufficient: bool

    # RAG检索结果
    retrieved_docs: List[Dict[str, Any]]

    # 生成的行程计划
    trip_plan: Optional[Dict[str, Any]]

    # 错误信息
    error: Optional[str]

    # 反馈状态
    feedback_status: Optional[Literal["satisfied", "unsatisfied", "partial"]]

    # 需要修改的部分
    revision_target: Optional[str]


class InfoCollectionState(BaseModel):
    """信息收集阶段状态"""
    stage: int = 0
    question: str = ""
    options: Optional[List[Dict[str, Any]]] = None
    user_response: Optional[Any] = None
    is_custom_input: bool = False


# 阶段常量
class Stages:
    """信息收集阶段枚举"""
    WELCOME = 0
    TRAVEL_TYPE = 1
    DURATION = 2
    BUDGET = 3
    RHYTHM = 4
    FOOD_PREFERENCES = 5
    ACCOMMODATION = 6
    TRANSPORT = 7
    SPECIAL_REQUIREMENTS = 8
    CONFIRM = 9
    PLANNING = 10
    REVIEW = 11
    COMPLETE = 12

    @classmethod
    def get_name(cls, stage: int) -> str:
        names = {
            cls.WELCOME: "欢迎",
            cls.TRAVEL_TYPE: "旅行类型",
            cls.DURATION: "行程天数",
            cls.BUDGET: "预算",
            cls.RHYTHM: "旅行节奏",
            cls.FOOD_PREFERENCES: "口味偏好",
            cls.ACCOMMODATION: "住宿偏好",
            cls.TRANSPORT: "交通方式",
            cls.SPECIAL_REQUIREMENTS: "特殊要求",
            cls.CONFIRM: "确认信息",
            cls.PLANNING: "规划中",
            cls.REVIEW: "回顾",
            cls.COMPLETE: "完成",
        }
        return names.get(stage, "未知")


def get_initial_state() -> AgentState:
    """获取初始状态"""
    return AgentState(
        messages=[],
        user_profile=None,
        current_stage=Stages.WELCOME,
        answers={},
        info_sufficient=False,
        retrieved_docs=[],
        trip_plan=None,
        error=None,
        feedback_status=None,
        revision_target=None,
    )
