from pymilvus import MilvusClient

client = MilvusClient(uri="./data/milvus_local.db")
collection = "insurance_knowledge"

# 1. 总数
stats = client.get_collection_stats(collection)
print(f"=== 向量库总条数: {stats['row_count']} ===")
print()

# 2. 按条款分组统计
print("=== 每个条款的向量条数 ===")
client.load_collection(collection)  # 先加载，否则 query 报 released 状态
rows = client.query(
    collection_name=collection,
    filter="",  # 空 filter 查全部（Milvus Lite 支持）
    output_fields=["clause_id", "document_name", "product_ids"],
    limit=10000,
)
from collections import defaultdict
by_clause = defaultdict(lambda: {"count": 0, "name": "", "product_ids": set()})
for r in rows:
    cid = r["clause_id"]
    by_clause[cid]["count"] += 1
    by_clause[cid]["name"] = r["document_name"]
    by_clause[cid]["product_ids"].update(r.get("product_ids", []))

for cid in sorted(by_clause.keys()):
    info = by_clause[cid]
    print(f"  clause_id={cid:>3}  向量{info['count']:>3}条  产品{list(info['product_ids'])}  {info['name']}")

# 3. 展示 3 条实际内容片段
print()
print("=== 内容片段示例 ===")
samples = client.query(
    collection_name=collection,
    filter="clause_id == 7",
    output_fields=["content", "section_path", "document_name"],
    limit=3,
)
for i, r in enumerate(samples, 1):
    content = r["content"]
    print(f"--- 示例 {i} ({r['document_name']}) ---")
    print(f"    章节: {r.get('section_path')}")
    print(f"    内容: {content[:120]}...")

client.close()
