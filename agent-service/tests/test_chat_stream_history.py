"""Exercise real LangGraph streaming/checkpoints without network model calls."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from langchain_core.language_models.fake_chat_models import FakeListChatModel
from langchain_core.messages import AIMessage, HumanMessage, ToolMessage
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.config import get_stream_writer
from langgraph.graph import END, START, StateGraph
from langgraph.types import StateSnapshot

from app.agent.models import ChatRuntimeContext, ParentState
from app.agent.service import (
    _project_history_from_snapshots,
    chat_stream,
    delete_message_history,
    get_message_history,
)


USER = SimpleNamespace(id=7, token='test-token')


def compile_graph(node, *, name='route', saver=None):
    builder = StateGraph(ParentState, context_schema=ChatRuntimeContext)
    builder.add_node(name, node)
    builder.add_edge(START, name)
    builder.add_edge(name, END)
    return builder.compile(checkpointer=saver or InMemorySaver())


async def collect(agent, thread_id, message):
    return [event async for event in chat_stream(agent, thread_id, message, None, USER)]


@pytest.mark.asyncio
async def test_direct_greeting_streams_once_and_done_has_durable_history():
    async def greeting(state):
        return {'messages': [AIMessage(content='你好！请问有什么保险问题？')]}

    agent = compile_graph(greeting)
    thread_id = uuid4()
    events = []
    async for event in chat_stream(agent, thread_id, '你好', None, USER):
        events.append(event)
        if event['event'] == 'done':
            history = await get_message_history(agent, thread_id)
            assert [(item.role, item.content) for item in history] == [
                ('user', '你好'), ('assistant', '你好！请问有什么保险问题？'),
            ]
    assert events == [
        {'event': 'message', 'data': '你好！请问有什么保险问题？'},
        {'event': 'done', 'data': {'thread_id': str(thread_id), 'finish': 'stop'}},
    ]
    await delete_message_history(agent, thread_id)
    assert await get_message_history(agent, thread_id) == []


@pytest.mark.asyncio
async def test_nested_tokens_do_not_leak_intent_or_repeat_old_replies():
    classifier = FakeListChatModel(responses=['{"intent":"chitchat"}'])
    model = FakeListChatModel(responses=['Hello world!'], sleep=0.001)

    async def route(state):
        await classifier.ainvoke(state['messages'], config={'tags': ['internal_intent']})
        return {}

    async def answer(state):
        return {'messages': [await model.ainvoke(state['messages'])]}

    child = StateGraph(ParentState)
    child.add_node('chat', answer)
    child.add_edge(START, 'chat')
    child.add_edge('chat', END)
    parent = StateGraph(ParentState, context_schema=ChatRuntimeContext)
    parent.add_node('route', route)
    parent.add_node('chitchat', child.compile(checkpointer=True))
    parent.add_edge(START, 'route')
    parent.add_edge('route', 'chitchat')
    parent.add_edge('chitchat', END)
    agent = parent.compile(checkpointer=InMemorySaver())
    thread_id = uuid4()

    for prompt in ['first', 'second']:
        events = await collect(agent, thread_id, prompt)
        chunks = [event['data'] for event in events if event['event'] == 'message']
        assert len(chunks) > 1, 'Expected actual token streaming before node completion'
        assert ''.join(chunks) == 'Hello world!'
        assert events[-1]['event'] == 'done'

    history = await get_message_history(agent, thread_id)
    assert [(item.role, item.content) for item in history] == [
        ('user', 'first'), ('assistant', 'Hello world!'),
        ('user', 'second'), ('assistant', 'Hello world!'),
    ]


@pytest.mark.asyncio
async def test_failed_turn_remains_in_history_and_emits_error():
    async def answer(state):
        prompt = state['messages'][-1].content
        if prompt == 'fail':
            raise RuntimeError('private upstream diagnostics')
        return {'messages': [AIMessage(content='answer')]}

    agent = compile_graph(answer)
    thread_id = uuid4()
    await collect(agent, thread_id, 'working')
    events = await collect(agent, thread_id, 'fail')
    assert events == [{'event': 'error', 'data': {'message': '对话生成失败，请稍后重试。'}}]
    history = await get_message_history(agent, thread_id)
    assert [(item.role, item.content) for item in history] == [
        ('user', 'working'), ('assistant', 'answer'), ('user', 'fail'),
    ]


@pytest.mark.asyncio
async def test_sources_are_preserved_per_turn_and_tool_messages_are_hidden():
    async def answer(state):
        prompt = state['messages'][-1].content
        if prompt == 'ordinary':
            return {'messages': [AIMessage(content='plain answer')]}
        sources = {'sources': [{'source_id': prompt}]}
        get_stream_writer()({'type': 'additional_info', 'data': sources})
        return {
            'messages': [
                AIMessage(content='private tool plan', tool_calls=[
                    {'id': 'tool-call', 'name': 'lookup', 'args': {}},
                ]),
                ToolMessage(content='private tool result', tool_call_id='tool-call'),
                AIMessage(content=f'answer {prompt}'),
            ],
            'additional_info': sources,
        }

    agent = compile_graph(answer)
    thread_id = uuid4()
    for prompt in ['one', 'two', 'ordinary']:
        events = await collect(agent, thread_id, prompt)
        visible = ''.join(event['data'] for event in events if event['event'] == 'message')
        assert 'private' not in visible
        assert events[-1]['event'] == 'done'
        info = [event for event in events if event['event'] == 'additional_info']
        assert len(info) == (0 if prompt == 'ordinary' else 1)
    history = await get_message_history(agent, thread_id)
    assert len(history) == 6
    assert history[1].additional_info == {'sources': [{'source_id': 'one'}]}
    assert history[3].additional_info == {'sources': [{'source_id': 'two'}]}
    assert history[5].additional_info is None
    assert all(item.additional_info is None for item in history if item.role == 'user')


@pytest.mark.asyncio
async def test_checkpoint_failure_never_claims_done():
    class FailingSaver(InMemorySaver):
        async def aput(self, config, checkpoint, metadata, new_versions):
            messages = checkpoint.get('channel_values', {}).get('messages', [])
            if any(isinstance(item, AIMessage) for item in messages):
                raise RuntimeError('checkpoint unavailable')
            return await super().aput(config, checkpoint, metadata, new_versions)

    async def answer(state):
        return {'messages': [AIMessage(content='not yet durable')]}

    events = await collect(compile_graph(answer, saver=FailingSaver()), uuid4(), 'hello')
    assert events[-1]['event'] == 'error'
    assert not any(event['event'] == 'done' for event in events)


def snapshot(messages, additional_info=None, *, pending=()):
    return StateSnapshot(
        values={'messages': messages, 'additional_info': additional_info},
        next=pending, config={}, metadata={}, created_at=None, parent_config=None, tasks=(),
    )


def test_pending_sources_do_not_attach_to_previous_assistant():
    first = [HumanMessage(content='first', id='u1'), AIMessage(content='reply one', id='a1')]
    second = first + [HumanMessage(content='second', id='u2')]
    sources = {'sources': ['second-turn-only']}
    history = _project_history_from_snapshots([
        snapshot(first), snapshot(second, sources, pending=('answer',)),
    ])
    assert [item.content for item in history] == ['first', 'reply one', 'second']
    assert all(item.additional_info is None for item in history)


def test_latest_snapshot_controls_message_replacements_without_count_slicing():
    user = HumanMessage(content='question', id='user')
    history = _project_history_from_snapshots([
        snapshot([user, AIMessage(content='old text', id='answer')]),
        snapshot([user, AIMessage(content='corrected text', id='answer')], {'sources': ['new']}),
    ])
    assert [item.content for item in history] == ['question', 'corrected text']
    assert history[-1].additional_info == {'sources': ['new']}
