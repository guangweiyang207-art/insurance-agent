from datetime import datetime, timedelta
from decimal import Decimal, ROUND_HALF_UP
from uuid import uuid4

from fastapi import APIRouter

from app.database import db, from_json, row_to_json, to_json
from app.responses import api_error

router = APIRouter()


def _answer(answers: dict, key: str, default: object = None) -> object:
    return answers.get(key, default)


def _factor_by_range(items: list[dict], value: int | None) -> Decimal:
    if value is None:
        return Decimal("1")
    for item in items:
        if int(item.get("min", -1)) <= value <= int(item.get("max", 999)):
            return Decimal(str(item.get("factor", 1)))
    return Decimal("1")


def _factor_by_key(config: dict, name: str, key: object) -> Decimal:
    values = config.get(name) or {}
    return Decimal(str(values.get(str(key), values.get(key, 1))))


def _money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)


@router.post("/calculate")
def calculate_premium(request: dict) -> dict:
    product_id = request.get("product_id")
    scenario = request.get("scenario") or "premium_by_coverage"
    answers = request.get("answers") or request
    if product_id is None:
        raise api_error(400, "INVALID_PRICING_PARAMS", "product_id is required")

    binding = db.fetch_one(
        """
        SELECT binding.id, binding.product_id, binding.pricing_schema_id,
               schema.schema_version, binding.adapter_id, binding.mock_config,
               adapter.insurer_code, adapter.adapter_type
        FROM product_pricing_bindings binding
        JOIN product_pricing_schemas schema ON schema.id = binding.pricing_schema_id
        JOIN insurer_api_adapters adapter ON adapter.id = binding.adapter_id
        WHERE binding.product_id = %s
          AND schema.scenario = %s
          AND binding.status = 'active'
          AND schema.status = 'active'
        LIMIT 1
        """,
        (product_id, scenario),
    )
    if binding is None:
        raise api_error(404, "PRICING_BINDING_NOT_FOUND", "Pricing binding not found")

    schema = db.fetch_one(
        "SELECT schema_json FROM product_pricing_schemas WHERE id = %s",
        (binding["pricing_schema_id"],),
    )
    fields = (schema or {}).get("schema_json", {}).get("fields", [])
    missing = [field["key"] for field in fields if field.get("required") and answers.get(field["key"]) is None]
    if missing:
        raise api_error(400, "MISSING_PRICING_PARAMS", f"缺少保费试算参数: {', '.join(missing)}")

    config = from_json(binding["mock_config"])
    plan_code = str(_answer(answers, "plan_code", "basic"))
    base = Decimal(str((config.get("base_premium_by_plan") or {}).get(plan_code, 100)))
    age_factor = _factor_by_range(config.get("age_factor") or [], _as_int(_answer(answers, "insured.age")))
    gender_factor = _factor_by_key(config, "gender_factor", _answer(answers, "insured.gender"))
    social_factor = _factor_by_key(config, "social_security_factor", _answer(answers, "insured.social_security"))
    deductible_factor = _factor_by_key(config, "deductible_factor", _answer(answers, "coverage.deductible"))
    occupation_factor = _factor_by_key(config, "occupation_factor", _answer(answers, "insured.occupation_class"))
    coverage_factor = Decimal("1")
    coverage_amount = _as_decimal(_answer(answers, "coverage.coverage_amount"))
    if config.get("coverage_factor_enabled") and coverage_amount:
        coverage_unit = Decimal(str(config.get("coverage_unit") or coverage_amount or 1))
        coverage_factor = max(Decimal("0.1"), coverage_amount / coverage_unit)

    annual_premium = _money(
        base * age_factor * gender_factor * social_factor * deductible_factor * occupation_factor * coverage_factor
    )
    now = datetime.now()
    expires_at = now + timedelta(minutes=30)
    quote_id = uuid4()
    result = {
        "quote_id": str(quote_id),
        "product_id": product_id,
        "plan_code": plan_code,
        "pricing_mode": "mock_adapter",
        "annual_premium": str(annual_premium),
        "payment_frequency": "annual",
        "breakdown": [
            {
                "item": "main",
                "name": plan_code,
                "premium": str(annual_premium),
                "source": {"adapter": binding["insurer_code"], "mode": "mock"},
            }
        ],
        "warnings": [
            "本结果由教学 mock adapter 生成，不构成真实保险报价",
            "真实产品保费以保险公司试算接口和核保结果为准",
        ],
        "expires_at": expires_at.isoformat(),
    }
    db.execute(
        """
        INSERT INTO premium_quotes (
            id, user_id, product_id, pricing_schema_id, schema_version, adapter_id,
            request_params, answers, external_request, external_response, result,
            total_premium, pricing_mode, expires_at
        )
        VALUES (%s, NULL, %s, %s, %s, %s, %s::jsonb, %s::jsonb, %s::jsonb, %s::jsonb,
                %s::jsonb, %s, 'mock_adapter', %s)
        """,
        (
            quote_id,
            product_id,
            binding["pricing_schema_id"],
            binding["schema_version"],
            binding["adapter_id"],
            to_json(request),
            to_json(answers),
            to_json(answers),
            to_json(result),
            to_json(result),
            annual_premium,
            expires_at,
        ),
    )
    return row_to_json(result)


def _as_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None

