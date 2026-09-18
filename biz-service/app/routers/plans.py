from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from app.database import db, from_json, row_to_json, to_json
from app.responses import ApiList, api_error
from app.security import current_user_id

router = APIRouter()


def _product_from_row(row: dict) -> dict:
    return row_to_json(
        {
            "id": row["product_info_id"],
            "name": row["product_name"],
            "clause_name": row["product_clause_name"],
            "category": row["product_category"],
            "insurer": row["product_insurer"],
            "image_url": row["product_image_url"],
            "description": row["product_description"],
            "min_premium": row["product_min_premium"],
            "max_premium": row["product_max_premium"],
            "target_group": row["product_target_group"],
            "highlights": row["product_highlights"],
            "status": row["product_status"],
        }
    )


def _plan_item_from_row(row: dict) -> dict:
    return row_to_json(
        {
            "id": row["id"],
            "plan_id": row["plan_id"],
            "product_id": row["product_id"],
            "category": row["category"],
            "priority": row["priority"],
            "recommendation_reason": row["recommendation_reason"],
            "annual_premium_budget": row["annual_premium_budget"],
            "product": _product_from_row(row),
            "status": row["status"],
            "created_at": row["created_at"],
            "updated_at": row["updated_at"],
        }
    )


def _plan_items(plan_id: UUID | str) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT item.id AS id, item.plan_id, item.product_id, item.category, item.priority,
               item.recommendation_reason, item.annual_premium_budget,
               item.status, item.created_at, item.updated_at,
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
        FROM customer_insurance_plan_items item
        JOIN products product ON product.id = item.product_id
        WHERE item.plan_id = %s
        ORDER BY item.priority, item.created_at
        """,
        (plan_id,),
    )
    return [_plan_item_from_row(row) for row in rows]


def _plan_json(row: dict) -> dict:
    plan = row_to_json(row)
    plan["insured_profile"] = from_json(row.get("insured_profile"))
    plan["items"] = _plan_items(row["id"])
    return plan


def _find_current(user_id: int) -> dict | None:
    return db.fetch_one(
        """
        SELECT id, user_id, plan_name, summary, budget_note,
               insured_profile::text AS insured_profile, status,
               annual_premium_budget, version, created_at, updated_at
        FROM customer_insurance_plans
        WHERE user_id = %s
        ORDER BY CASE WHEN status = 'insured' THEN 1 ELSE 0 END, updated_at DESC
        LIMIT 1
        """,
        (user_id,),
    )


@router.get("")
def list_plans(user_id: int = Depends(current_user_id)) -> ApiList:
    rows = db.fetch_all(
        """
        SELECT id, user_id, plan_name, summary, budget_note,
               insured_profile::text AS insured_profile, status,
               annual_premium_budget, version, created_at, updated_at
        FROM customer_insurance_plans
        WHERE user_id = %s
        ORDER BY updated_at DESC
        """,
        (user_id,),
    )
    return ApiList(items=[_plan_json(row) for row in rows])


@router.get("/current")
def get_current_plan(user_id: int = Depends(current_user_id)) -> dict:
    row = _find_current(user_id)
    if row is None:
        raise api_error(404, "INSURANCE_PLAN_NOT_FOUND", "Insurance plan not found")
    return _plan_json(row)


@router.put("/current")
def save_current_plan(request: dict, user_id: int = Depends(current_user_id)) -> dict:
    current = _find_current(user_id)
    items = request.get("items") or []
    annual_budget = _sum_budget(items)

    if current is None or current["status"] == "insured":
        plan_id = uuid4()
        db.execute(
            """
            INSERT INTO customer_insurance_plans (
                id, user_id, plan_name, summary, budget_note,
                insured_profile, status, annual_premium_budget, version
            )
            VALUES (%s, %s, %s, %s, %s, %s::jsonb, 'uninsured', %s, 1)
            """,
            (
                plan_id,
                user_id,
                request.get("plan_name") or request.get("planName"),
                request.get("summary"),
                request.get("budget_note") or request.get("budgetNote"),
                to_json(request.get("insured_profile") or request.get("insuredProfile")),
                annual_budget,
            ),
        )
    else:
        plan_id = current["id"]
        db.execute(
            """
            UPDATE customer_insurance_plans
            SET plan_name = %s,
                summary = %s,
                budget_note = %s,
                insured_profile = %s::jsonb,
                annual_premium_budget = %s,
                version = version + 1,
                updated_at = CURRENT_TIMESTAMP
            WHERE id = %s AND user_id = %s AND status <> 'insured'
            """,
            (
                request.get("plan_name") or request.get("planName"),
                request.get("summary"),
                request.get("budget_note") or request.get("budgetNote"),
                to_json(request.get("insured_profile") or request.get("insuredProfile")),
                annual_budget,
                plan_id,
                user_id,
            ),
        )
        db.execute("DELETE FROM customer_insurance_plan_items WHERE plan_id = %s AND status = 'uninsured'", (plan_id,))

    insured_products = {
        row["product_id"]
        for row in db.fetch_all(
            "SELECT product_id FROM customer_insurance_plan_items WHERE plan_id = %s AND status = 'insured'",
            (plan_id,),
        )
    }
    for item in items:
        product_id = item.get("product_id") or item.get("productId")
        if product_id in insured_products:
            continue
        db.execute(
            """
            INSERT INTO customer_insurance_plan_items (
                id, plan_id, product_id, category, priority,
                recommendation_reason, annual_premium_budget, status
            )
            VALUES (%s, %s, %s, %s, %s, %s, %s, 'uninsured')
            """,
            (
                uuid4(),
                plan_id,
                product_id,
                item.get("category"),
                item.get("priority") or 1,
                item.get("recommendation_reason") or item.get("recommendationReason"),
                item.get("annual_premium_budget") or item.get("annualPremiumBudget"),
            ),
        )
    _refresh_plan_summary(plan_id)
    return get_plan(plan_id, user_id)


@router.get("/{plan_id}")
def get_plan(plan_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    row = db.fetch_one(
        """
        SELECT id, user_id, plan_name, summary, budget_note,
               insured_profile::text AS insured_profile, status,
               annual_premium_budget, version, created_at, updated_at
        FROM customer_insurance_plans
        WHERE id = %s AND user_id = %s
        """,
        (plan_id, user_id),
    )
    if row is None:
        raise api_error(404, "INSURANCE_PLAN_NOT_FOUND", "Insurance plan not found")
    return _plan_json(row)


@router.patch("/{plan_id}/items/{item_id}/insured")
def mark_item_insured(plan_id: UUID, item_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    updated = db.execute(
        """
        UPDATE customer_insurance_plan_items item
        SET status = 'insured', updated_at = CURRENT_TIMESTAMP
        WHERE item.id = %s AND item.plan_id = %s
          AND EXISTS (
              SELECT 1 FROM customer_insurance_plans plan
              WHERE plan.id = item.plan_id AND plan.user_id = %s
          )
        """,
        (item_id, plan_id, user_id),
    )
    if updated == 0:
        raise api_error(404, "PLAN_ITEM_NOT_FOUND", "Plan item not found")
    _create_active_policy_for_item(plan_id, item_id, user_id)
    _refresh_plan_summary(plan_id)
    return get_plan(plan_id, user_id)


def _sum_budget(items: list[dict]) -> Decimal | None:
    total = Decimal("0")
    has_value = False
    for item in items:
        value = item.get("annual_premium_budget") or item.get("annualPremiumBudget")
        if value is not None:
            total += Decimal(str(value))
            has_value = True
    return total if has_value else None


def _refresh_plan_summary(plan_id: UUID) -> None:
    db.execute(
        """
        UPDATE customer_insurance_plans plan
        SET status = CASE
                WHEN NOT EXISTS (
                    SELECT 1 FROM customer_insurance_plan_items item
                    WHERE item.plan_id = plan.id AND item.status = 'insured'
                ) THEN 'uninsured'
                WHEN NOT EXISTS (
                    SELECT 1 FROM customer_insurance_plan_items item
                    WHERE item.plan_id = plan.id AND item.status = 'uninsured'
                ) THEN 'insured'
                ELSE 'applying'
            END,
            annual_premium_budget = totals.annual_budget,
            updated_at = CURRENT_TIMESTAMP
        FROM (
            SELECT COALESCE(SUM(annual_premium_budget), 0) AS annual_budget
            FROM customer_insurance_plan_items
            WHERE plan_id = %s
        ) totals
        WHERE plan.id = %s
        """,
        (plan_id, plan_id),
    )


def _create_active_policy_for_item(plan_id: UUID, item_id: UUID, user_id: int) -> None:
    suffix = str(item_id)[:8].upper()
    db.execute(
        """
        INSERT INTO policies (
            id, user_id, product_id, policy_number, application_no, status,
            effective_at, expires_at, holder_name, insured_name,
            insured_id_no_masked, insured_phone, coverage_amount, premium_amount,
            payment_frequency, beneficiary, policy_snapshot, coverage_snapshot,
            paid_at, issued_at
        )
        SELECT %s, %s, item.product_id, %s, %s, 'active',
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP + INTERVAL '1 year',
               COALESCE(plan.insured_profile ->> 'holder_name', plan.insured_profile ->> 'name', '演示投保人'),
               COALESCE(plan.insured_profile ->> 'insured_name', plan.insured_profile ->> 'name', '演示被保人'),
               COALESCE(plan.insured_profile ->> 'id_no_masked', '未提供'),
               COALESCE(plan.insured_profile ->> 'phone', '未提供'),
               CASE item.category
                   WHEN 'medical' THEN 2000000
                   WHEN 'critical_illness' THEN 300000
                   WHEN 'life' THEN 500000
                   WHEN 'accident' THEN 100000
                   ELSE 100000
               END,
               item.annual_premium_budget,
               'annual',
               jsonb_build_object('type', '法定受益人'),
               jsonb_build_object(
                   'plan_id', plan.id,
                   'plan_name', plan.plan_name,
                   'plan_summary', plan.summary,
                   'budget_note', plan.budget_note,
                   'plan_item_id', item.id,
                   'recommendation_reason', item.recommendation_reason,
                   'product_id', product.id,
                   'product_name', product.name,
                   'category', product.category,
                   'insurer', product.insurer,
                   'clause_name', product.clause_name
               ),
               CASE item.category
                   WHEN 'medical' THEN jsonb_build_object('category', item.category, 'annual_limit', 2000000, 'deductible', 10000, 'reimbursement_ratio', 1, 'hospital_scope', '二级及以上公立医院普通部')
                   WHEN 'critical_illness' THEN jsonb_build_object('category', item.category, 'coverage_amount', 300000, 'waiting_period_days', 90)
                   WHEN 'life' THEN jsonb_build_object('category', item.category, 'death_benefit_amount', 500000, 'waiting_period_days', 180)
                   WHEN 'accident' THEN jsonb_build_object('category', item.category, 'death_disability_amount', 100000, 'medical_amount', 20000)
                   ELSE jsonb_build_object('category', item.category)
               END,
               CURRENT_TIMESTAMP, CURRENT_TIMESTAMP
        FROM customer_insurance_plan_items item
        JOIN customer_insurance_plans plan ON plan.id = item.plan_id
        JOIN products product ON product.id = item.product_id
        WHERE item.id = %s AND item.plan_id = %s
        ON CONFLICT (policy_number) DO UPDATE
            SET status = 'active',
                application_no = EXCLUDED.application_no,
                holder_name = EXCLUDED.holder_name,
                insured_name = EXCLUDED.insured_name,
                insured_id_no_masked = EXCLUDED.insured_id_no_masked,
                insured_phone = EXCLUDED.insured_phone,
                coverage_amount = EXCLUDED.coverage_amount,
                premium_amount = EXCLUDED.premium_amount,
                payment_frequency = EXCLUDED.payment_frequency,
                beneficiary = EXCLUDED.beneficiary,
                policy_snapshot = EXCLUDED.policy_snapshot,
                coverage_snapshot = EXCLUDED.coverage_snapshot,
                paid_at = EXCLUDED.paid_at,
                issued_at = EXCLUDED.issued_at,
                updated_at = CURRENT_TIMESTAMP
        """,
        (uuid4(), user_id, f"POL-DEMO-{suffix}", f"APP-DEMO-{suffix}", item_id, plan_id),
    )
