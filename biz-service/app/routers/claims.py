from pathlib import Path
from uuid import UUID

from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse

from app.config import get_settings
from app.database import db, row_to_json
from app.responses import ApiList, api_error
from app.routers.policies import SELECT_POLICY, policy_json
from app.security import current_user_id

router = APIRouter()


SELECT_CLAIM = """
SELECT claim.id AS claim_id, claim.user_id AS claim_user_id,
       claim.policy_id, claim.claim_number, claim.claim_type,
       claim.amount, claim.description, claim.status AS claim_status,
       claim.submitted_at, claim.updated_at AS claim_updated_at,
       policy_row.*
FROM claims claim
JOIN LATERAL (
    %s WHERE policy.id = claim.policy_id
) policy_row ON TRUE
""" % SELECT_POLICY


def _status_message(status: str) -> str:
    return {
        "submitted": "理赔申请已提交，等待保险公司受理",
        "reviewing": "保险公司正在审核材料，可能要求补充资料",
        "approved": "理赔审核已通过，等待后续赔付处理",
        "rejected": "理赔审核未通过，请查看通知并联系保险公司复核",
        "paid": "理赔款已支付，请核对收款账户",
    }.get(status, "理赔案件状态待确认")


def claim_json(row: dict) -> dict:
    return {
        "id": str(row["claim_id"]),
        "user_id": row["claim_user_id"],
        "policy_id": str(row["policy_id"]) if row.get("policy_id") else None,
        "claim_number": row["claim_number"],
        "claim_type": row["claim_type"],
        "amount": row_to_json({"v": row["amount"]})["v"],
        "description": row["description"],
        "status": row["claim_status"],
        "status_message": _status_message(row["claim_status"]),
        "policy": policy_json(row),
        "submitted_at": row_to_json({"v": row["submitted_at"]})["v"],
        "updated_at": row_to_json({"v": row["claim_updated_at"]})["v"],
    }


@router.get("/claims")
def list_claims(
    policy_id: UUID | None = None,
    status: str | None = None,
    user_id: int = Depends(current_user_id),
) -> ApiList:
    where = ["claim.user_id = %s"]
    params: list[object] = [user_id]
    if policy_id is not None:
        where.append("claim.policy_id = %s")
        params.append(policy_id)
    if status:
        where.append("claim.status = %s")
        params.append(status)
    rows = db.fetch_all(
        SELECT_CLAIM + " WHERE " + " AND ".join(where) + " ORDER BY claim.updated_at DESC",
        tuple(params),
    )
    return ApiList(items=[claim_json(row) for row in rows])


@router.get("/claims/{claim_id}")
def get_claim(claim_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    row = db.fetch_one(SELECT_CLAIM + " WHERE claim.id = %s AND claim.user_id = %s", (claim_id, user_id))
    if row is None:
        raise api_error(404, "CLAIM_NOT_FOUND", "Claim not found")
    return claim_json(row)


@router.get("/claim-guides/application-form")
def download_application_form() -> FileResponse:
    local_path = Path(__file__).resolve().parents[2] / "static" / "forms" / "claim-application-form.pdf"
    full_path = local_path
    if not full_path.exists():
        full_path = get_settings().app_workspace_root / "biz-service/static/forms/claim-application-form.pdf"
    if not full_path.exists():
        raise api_error(404, "APPLICATION_FORM_NOT_FOUND", "Application form not found")
    return FileResponse(full_path, media_type="application/pdf", filename="claim-application-form.pdf")


@router.get("/claim-guides/{policy_id}")
def get_claim_guide(policy_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    policy = db.fetch_one(SELECT_POLICY + " WHERE policy.id = %s AND policy.user_id = %s", (policy_id, user_id))
    if policy is None:
        raise api_error(404, "POLICY_NOT_FOUND", "Policy not found")
    product = policy_json(policy)["product"]
    return {
        "policy_id": str(policy_id),
        "product_id": product["id"],
        "product_name": product["name"],
        "download_uri": "/api/v1/claim-guides/application-form",
        "steps": [
            {"title": "准备材料", "description": "按保单责任和就诊情况准备理赔材料。"},
            {"title": "联系承保公司", "description": "商城仅提供指引，实际理赔申请由承保公司受理。"},
            {"title": "提交申请", "description": "通过保险公司官方渠道提交申请表和材料。"},
            {"title": "等待审核", "description": "保险公司完成材料审核后给出理赔结论。"},
        ],
        "materials": [
            {"name": "理赔申请书", "required": True, "remark": "可下载教学版申请表参考填写。"},
            {"name": "身份证明", "required": True, "remark": "投保人、被保人或受益人的有效证件。"},
            {"name": "费用票据/病历资料", "required": product["category"] in ["medical", "accident"], "remark": "医疗或意外医疗场景通常需要。"},
            {"name": "事故证明/诊断证明", "required": True, "remark": "按险种和事故类型准备。"},
        ],
        "notes": [
            "本商城不直接受理、审核或支付理赔。",
            "具体材料、时效和结论以承保公司要求为准。",
            "如涉及争议、拒赔复核或投诉，请直接联系承保公司或人工客服。",
        ],
    }
