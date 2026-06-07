"""LangGraph状态机图构建"""
from typing import Annotated, Sequence
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langgraph.checkpoint.memory import MemorySaver

from travel_agent.agent.state import AgentState, Stages
from travel_agent.agent.nodes import (
    welcome_node,
    ask_travel_type_node,
    ask_duration_node,
    ask_budget_node,
    ask_rhythm_node,
    ask_food_preferences_node,
    ask_accommodation_node,
    ask_transport_node,
    confirm_info_node,
    need_more_info_node,
    update_profile_node,
)
from travel_agent.agent.edges import (
    should_collect_more_info,
    should_generate_plan,
    after_question,
    after_update_profile,
    should_revise,
    is_welcome,
)


def create_travel_agent_graph():
    """创建旅行规划Agent状态机"""

    # 创建图
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("welcome", welcome_node)
    workflow.add_node("ask_travel_type", ask_travel_type_node)
    workflow.add_node("ask_duration", ask_duration_node)
    workflow.add_node("ask_budget", ask_budget_node)
    workflow.add_node("ask_rhythm", ask_rhythm_node)
    workflow.add_node("ask_food_preferences", ask_food_preferences_node)
    workflow.add_node("ask_accommodation", ask_accommodation_node)
    workflow.add_node("ask_transport", ask_transport_node)
    workflow.add_node("update_profile", update_profile_node)
    workflow.add_node("confirm_info", confirm_info_node)
    workflow.add_node("need_more_info", need_more_info_node)

    # 设置入口
    workflow.set_entry_point("welcome")

    # 添加边
    workflow.add_edge("welcome", "ask_travel_type")

    # 问题 -> 更新 -> 判断下一个问题
    question_nodes = [
        "ask_travel_type",
        "ask_duration",
        "ask_budget",
        "ask_rhythm",
        "ask_food_preferences",
        "ask_accommodation",
        "ask_transport",
    ]

    for node in question_nodes:
        workflow.add_edge(node, "update_profile")

    # 更新后判断下一个问题
    workflow.add_conditional_edges(
        "update_profile",
        after_update_profile,
        {
            "ask_travel_type": "ask_travel_type",
            "ask_duration": "ask_duration",
            "ask_budget": "ask_budget",
            "ask_rhythm": "ask_rhythm",
            "ask_food_preferences": "ask_food_preferences",
            "ask_accommodation": "ask_accommodation",
            "ask_transport": "ask_transport",
            "confirm_info": "confirm_info",
        }
    )

    # 确认信息后进入RAG检索和生成阶段
    workflow.add_edge("confirm_info", "need_more_info")

    # 结束
    workflow.add_edge("need_more_info", END)

    # 编译图
    return workflow.compile()


def create_simple_conversation_graph():
    """创建简化的对话图 - 用于单轮对话"""

    workflow = StateGraph(AgentState)

    # 节点
    workflow.add_node("welcome", welcome_node)
    workflow.add_node("ask_travel_type", ask_travel_type_node)
    workflow.add_node("ask_duration", ask_duration_node)
    workflow.add_node("ask_budget", ask_budget_node)
    workflow.add_node("update_profile", update_profile_node)
    workflow.add_node("confirm_info", confirm_info_node)

    # 入口
    workflow.set_entry_point("welcome")

    # 流程
    workflow.add_edge("welcome", "ask_travel_type")
    workflow.add_edge("ask_travel_type", "update_profile")
    workflow.add_edge("update_profile", "ask_duration")
    workflow.add_edge("ask_duration", "update_profile")
    workflow.add_edge("update_profile", "ask_budget")
    workflow.add_edge("ask_budget", "update_profile")
    workflow.add_edge("update_profile", "confirm_info")
    workflow.add_edge("confirm_info", END)

    return workflow.compile()


# 导出预编译的图实例
travel_agent_graph = create_travel_agent_graph()
simple_conversation_graph = create_simple_conversation_graph()


class TravelAgent:
    """旅行规划Agent封装类"""

    def __init__(self, use_full_flow: bool = True):
        self.graph = travel_agent_graph if use_full_flow else simple_conversation_graph
        self.checkpointer = MemorySaver()

    def invoke(self, state: AgentState) -> AgentState:
        """执行一次推理"""
        return self.graph.invoke(state)

    def stream(self, state: AgentState):
        """流式执行"""
        return self.graph.stream(state)

    def get_initial_state(self) -> AgentState:
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
