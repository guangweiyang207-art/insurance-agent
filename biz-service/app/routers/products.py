from decimal import Decimal

from fastapi import APIRouter, Query

from app.database import db, row_to_json
from app.responses import ApiPage, api_error

router = APIRouter()


PRODUCT_FIELDS = """
id, name, clause_name, category, insurer, image_url, description,
min_premium, max_premium, target_group, highlights, status
"""


def product_json(row: dict) -> dict:
    return row_to_json(row)


@router.get("")
def list_products(
    category: str | None = None,
    product_name: str | None = None,
    page: int = 1,
    page_size: int = Query(default=20, alias="page_size"),
) -> ApiPage:
    where = ["status = 'active'"]
    params: list[object] = []
    if category:
        where.append("category = %s")
        params.append(category)
    if product_name:
        where.append("(name ILIKE %s OR clause_name ILIKE %s)")
        pattern = f"%{product_name.strip()}%"
        params.extend([pattern, pattern])

    where_sql = " AND ".join(where)
    total = db.fetch_one(f"SELECT COUNT(*) AS count FROM products WHERE {where_sql}", tuple(params))["count"]
    offset = max(page - 1, 0) * page_size
    rows = db.fetch_all(
        f"""
        SELECT {PRODUCT_FIELDS}
        FROM products
        WHERE {where_sql}
        ORDER BY id
        LIMIT %s OFFSET %s
        """,
        tuple(params + [page_size, offset]),
    )
    return ApiPage(items=[product_json(row) for row in rows], page=page, page_size=page_size, total=total)


@router.get("/candidates")
def list_candidate_products(
    categories: list[str] = Query(default=[]),
    premium_min: Decimal | None = Query(default=None, alias="premium_min"),
    limit_per_category: int = Query(default=5, alias="limit_per_category"),
) -> list[dict]:
    if not categories:
        return []
    premium_condition = "AND min_premium < %s" if premium_min is not None else ""
    params: list[object] = [categories]
    if premium_min is not None:
        params.append(premium_min)
    params.append(limit_per_category)
    rows = db.fetch_all(
        f"""
        WITH ranked_products AS (
            SELECT {PRODUCT_FIELDS},
                   ROW_NUMBER() OVER (PARTITION BY category ORDER BY id) AS category_rank
            FROM products
            WHERE status = 'active' AND category = ANY(%s) {premium_condition}
        )
        SELECT {PRODUCT_FIELDS}
        FROM ranked_products
        WHERE category_rank <= %s
        ORDER BY category, id
        """,
        tuple(params),
    )
    return [product_json(row) for row in rows]


@router.get("/{product_id}")
def get_product(product_id: int) -> dict:
    product = db.fetch_one(f"SELECT {PRODUCT_FIELDS} FROM products WHERE id = %s", (product_id,))
    if product is None:
        raise api_error(404, "PRODUCT_NOT_FOUND", "Product not found")
    clauses = db.fetch_all(
        """
        SELECT c.id, c.file_name, c.file_path, c.clause_type, c.created_at, c.updated_at
        FROM clauses c
        JOIN product_clauses pc ON pc.clause_id = c.id
        WHERE pc.product_id = %s
        ORDER BY c.id
        """,
        (product_id,),
    )
    data = product_json(product)
    data["clauses"] = [row_to_json(row) for row in clauses]
    return data


@router.get("/{product_id}/clauses")
def get_product_clauses(product_id: int) -> list[dict]:
    rows = db.fetch_all(
        """
        SELECT c.id, c.file_name, c.file_path, c.clause_type, c.created_at, c.updated_at
        FROM clauses c
        JOIN product_clauses pc ON pc.clause_id = c.id
        WHERE pc.product_id = %s
        ORDER BY c.id
        """,
        (product_id,),
    )
    return [row_to_json(row) for row in rows]


@router.get("/{product_id}/pricing-schema")
def get_pricing_schema(product_id: int) -> dict:
    row = db.fetch_one(
        """
        SELECT product_id, scenario, schema_version, schema_json AS schema
        FROM product_pricing_schemas
        WHERE product_id = %s AND status = 'active'
        ORDER BY activated_at DESC NULLS LAST, created_at DESC
        LIMIT 1
        """,
        (product_id,),
    )
    if row is None:
        raise api_error(404, "PRICING_SCHEMA_NOT_FOUND", "Pricing schema not found")
    return row_to_json(row)

