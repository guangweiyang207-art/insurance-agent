"""RAG 检索质量评测脚本（RAGAS）。

对保险条款问答做忠实度/相关性/召回率评测，量化检索与生成质量。

依赖（首次运行前安装）:
    .venv/Scripts/python.exe -m pip install ragas datasets

用法:
    .venv/Scripts/python.exe scripts/evaluate_rag.py
"""
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.embedding import BGEM3Embedding
from app.rag.vector_store import MilvusVectorStore
from app.rag.crud import PostgresKnowledgeRepository
from app.rag.retrieval import KnowledgeRetriever
from app.core.config import settings
from app.core.database import init_db, get_session_factory, close_db
from app.core.chat_model import create_chat_model
from langchain_core.embeddings import Embeddings


class BGEM3LangchainEmbeddings(Embeddings):
    """把项目的 BGEM3Embedding 包装成 LangChain Embeddings 接口，供 RAGAS 计算语义相似度。"""

    def __init__(self, bge: BGEM3Embedding) -> None:
        self._bge = bge

    def embed_documents(self, texts: list[str]) -> list[list[float]]:
        dense = self._bge.embed_documents(texts)["dense"]
        return dense.tolist() if hasattr(dense, "tolist") else list(dense)

    def embed_query(self, text: str) -> list[float]:
        dense = self._bge.embed_query(text)["dense"]
        return dense.tolist() if hasattr(dense, "tolist") else list(dense)


# 评测集：问题 + 标准答案（ground_truth）。product_id 对应条款所属产品。
EVAL_SET = [
    {
        "question": "达尔文12号重大疾病保险的等待期是多久？",
        "ground_truth": "等待期为180天，等待期内因非意外原因确诊重疾、中症或轻症不承担保险责任",
        "product_id": 2,
    },
    {
        "question": "众安尊享e生百万医疗险的免赔额是多少？",
        "ground_truth": "免赔额可选0元或1万元",
        "product_id": 6,
    },
    {
        "question": "太平洋小蜜蜂6号综合意外险的适用年龄范围？",
        "ground_truth": "18-50周岁，1-3类职业",
        "product_id": 10,
    },
    {
        "question": "人保小学童2号Pro学平险的适用年龄范围？",
        "ground_truth": "3-24周岁",
        "product_id": 12,
    },
    {
        "question": "达尔文宝贝计划12号的适用年龄范围？",
        "ground_truth": "0-17周岁",
        "product_id": 1,
    },
    {
        "question": "复星联合星相守2号长期医疗险保证续保多久？",
        "ground_truth": "保证续保20年",
        "product_id": 4,
    },
    {
        "question": "中英人寿福满佳C款的保险类型是什么？",
        "ground_truth": "终身寿险，分红型",
        "product_id": 7,
    },
    {
        "question": "复星联合医联有盟重疾险的适用年龄范围？",
        "ground_truth": "18-59周岁，1-4类职业",
        "product_id": 3,
    },
    {
        "question": "新华人寿E增福优享版的最大适用年龄是多少？",
        "ground_truth": "70周岁",
        "product_id": 9,
    },
    {
        "question": "太平洋小蜜蜂6号玫瑰版的适用场景是什么？",
        "ground_truth": "女性场景综合意外险",
        "product_id": 11,
    },
]


async def build_retriever():
    await init_db()
    embedding = BGEM3Embedding()
    vector_store = MilvusVectorStore(uri=settings.milvus_uri, collection_name=settings.milvus_collection)
    repository = PostgresKnowledgeRepository(get_session_factory())
    retriever = KnowledgeRetriever(
        rerank_model=settings.rerank_model,
        embedding=embedding,
        vector_store=vector_store,
        repository=repository,
    )
    return retriever, vector_store


async def collect_samples():
    """对评测集逐条检索并生成答案，返回 RAGAS 所需的结构。"""
    retriever, vector_store = await build_retriever()
    llm = create_chat_model(extra_body={"thinking": {"type": "disabled"}})

    questions, answers, contexts_list, ground_truths = [], [], [], []
    for item in EVAL_SET:
        q = item["question"]
        evidence = await retriever.search(q, item["product_id"], top_k=5)
        contexts = [e.content for e in evidence]
        # 基于检索到的条款生成答案
        if contexts:
            prompt = (
                "基于以下保险条款内容回答用户问题，只依据条款内容，不编造：\n"
                + "\n---\n".join(contexts)
                + f"\n\n用户问题：{q}"
            )
            resp = await llm.ainvoke(prompt)
            answer = str(resp.content)
        else:
            answer = "未检索到相关条款，无法回答。"
        questions.append(q)
        answers.append(answer)
        contexts_list.append(contexts if contexts else [""])
        ground_truths.append(item["ground_truth"])
        print(f"[{len(questions)}/{len(EVAL_SET)}] {q}  → 召回 {len(contexts)} 条")

    vector_store.close()
    await close_db()
    return questions, answers, contexts_list, ground_truths


def main():
    questions, answers, contexts_list, ground_truths = asyncio.run(collect_samples())

    try:
        from datasets import Dataset
        from ragas import evaluate
        from ragas.llms import LangchainLLMWrapper
        from ragas.metrics import (
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        )
    except ImportError as e:
        print(f"\n[依赖缺失] {e}")
        print("请先安装: .venv/Scripts/python.exe -m pip install ragas datasets")
        sys.exit(1)

    # judge LLM 用 DeepSeek；embedding 用本地 BGE-M3（DeepSeek 无 embedding 端点）
    judge_llm = LangchainLLMWrapper(create_chat_model(extra_body={"thinking": {"type": "disabled"}}))
    embeddings = BGEM3LangchainEmbeddings(BGEM3Embedding())

    dataset = Dataset.from_dict({
        "question": questions,
        "answer": answers,
        "contexts": contexts_list,
        "ground_truth": ground_truths,
    })
    result = evaluate(
        dataset,
        metrics=[faithfulness, answer_relevancy, context_precision, context_recall],
        llm=judge_llm,
        embeddings=embeddings,
    )
    print("\n=== RAGAS 评测结果 ===")
    print(result)


if __name__ == "__main__":
    main()
