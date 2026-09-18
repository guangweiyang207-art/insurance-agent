from langchain_core.messages import AIMessage, SystemMessage
from langgraph.graph import StateGraph

from .models import ParentState
from ..core.chat_model import create_chat_model
from ..core.logging import get_logger
#这是**闲聊子图（chitchat 子工作流）**，继承父图 `ParentState`，专门处理意图识别为 `chitchat` 的对话。
logger = get_logger(__name__)

SYSTEM_MESSAGE = """
你是保险智能客服，负责处理与保险业务无关的普通聊天。

要求：
1. 回复友好、自然，最多两句话。
2. 不假装有个人经历、情感、实时信息或外部能力。
3. 不回答医疗、法律、投资等高风险专业建议。
4. 不展开长期闲聊；每次回复都自然引导用户咨询保险产品、投保、保单或理赔。
5. 如果用户的问题本身需要实时信息或不属于你的能力范围，明确说明无法提供。
"""
MAX_CHIT_CHAT_COUNT = 3

# 闲聊工作流的状态
class ChitchatState(ParentState):
    chitchat_count: int  # 统计闲聊轮次


class Chitchat:

    def __init__(self):
        # 初始化模型，应该是一个本地小模型
        self.model = create_chat_model(
            extra_body={'thinking': {'type': 'disabled'}}
        )

    # 闲聊节点
    async def _chat_node(self, state: ChitchatState):
        # 取count
        count = state.get('chitchat_count', 0)
        logger.info(count=count)
        # 判断上一次是否是闲聊，如果不是，重置闲聊轮次为0
        previous_workflow = state.get('previous_workflow', '')
        if previous_workflow != 'chitchat':
            count = 0
        # 判断闲聊轮次，如果超过最大值，就不再调用模型，而是回复固定模版
        if count >= MAX_CHIT_CHAT_COUNT:
            return {
                'messages': [AIMessage("我主要协助处理保险产品、投保、保单和理赔咨询。 您可以直接告诉我想办理或了解的事项。其它问题我无法帮您。")],
                'chitchat_count': count + 1
            }
        # 闲聊
        response = await self.model.ainvoke([SystemMessage(content=SYSTEM_MESSAGE)] + state['messages'])
        return {'messages': [response], 'chitchat_count': count + 1}

    # 初始化sub graph
    def build_graph(self):
        builder = StateGraph(ChitchatState)
        builder.add_node('chat', self._chat_node)
        builder.set_entry_point('chat')  # START -> chat
        builder.set_finish_point('chat')  # chat -> END
        return builder.compile(checkpointer=True)
