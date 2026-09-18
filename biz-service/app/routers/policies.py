from uuid import UUID

from fastapi import APIRouter, Depends

from app.database import db, from_json, row_to_json
from app.responses import ApiList, api_error
from app.security import current_user_id

router = APIRouter()


SELECT_POLICY = """
SELECT policy.id, policy.user_id, policy.product_id, policy.policy_number,
       policy.application_no, policy.status, policy.effective_at, policy.expires_at,
       policy.holder_name, policy.insured_name, policy.insured_id_no_masked,
       policy.insured_phone, policy.coverage_amount, policy.premium_amount,
       policy.payment_frequency, policy.beneficiary::text AS beneficiary,
       policy.policy_snapshot::text AS policy_snapshot,
       policy.coverage_snapshot::text AS coverage_snapshot,
       policy.paid_at, policy.issued_at,
       policy.created_at, policy.updated_at,
       product.id AS product_info_id, product.name AS product_name,
       product.clause_name AS product_clause_name,
       product.category AS product_category, product.insurer AS product_insurer,
       product.image_url AS product_image_url,
       product.description AS product_description,
       product.min_premium AS product_min_premium,
       product.max_premium AS product_max_premium,
       product.target_group AS product_target_group,
       product.highlights AS product_highlights,
       product.status AS product_status
FROM policies policy
JOIN products product ON product.id = policy.product_id
"""


def policy_json(row: dict) -> dict:
    data = row_to_json(row)
    data["beneficiary"] = from_json(row.get("beneficiary"))
    data["policy_snapshot"] = from_json(row.get("policy_snapshot"))
    data["coverage_snapshot"] = from_json(row.get("coverage_snapshot"))
    data["product"] = {
        "id": row["product_info_id"],
        "name": row["product_name"],
        "clause_name": row["product_clause_name"],
        "category": row["product_category"],
        "insurer": row["product_insurer"],
        "image_url": row["product_image_url"],
        "description": row["product_description"],
        "min_premium": row_to_json({"v": row["product_min_premium"]})["v"],
        "max_premium": row_to_json({"v": row["product_max_premium"]})["v"],
        "target_group": row["product_target_group"],
        "highlights": row["product_highlights"],
        "status": row["product_status"],
    }
    for key in list(data.keys()):
        if key.startswith("product_"):
            data.pop(key)
    return data


@router.get("")
def list_policies(status: str = "active", user_id: int = Depends(current_user_id)) -> ApiList:
    params: list[object] = [user_id]
    status_sql = ""
    if status != "all":
        status_sql = " AND policy.status = %s"
        params.append(status)
    rows = db.fetch_all(
        SELECT_POLICY + f" WHERE policy.user_id = %s{status_sql} ORDER BY policy.effective_at DESC",
        tuple(params),
    )
    return ApiList(items=[policy_json(row) for row in rows])


@router.get("/{policy_id}")
def get_policy(policy_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    row = db.fetch_one(SELECT_POLICY + " WHERE policy.id = %s AND policy.user_id = %s", (policy_id, user_id))
    if row is None:
        raise api_error(404, "POLICY_NOT_FOUND", "Policy not found")
    return policy_json(row)

