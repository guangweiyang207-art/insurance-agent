from datetime import datetime
from decimal import Decimal
from uuid import UUID, uuid4

from fastapi import APIRouter, Depends

from app.database import db, from_json, row_to_json, to_json
from app.responses import ApiList, api_error
from app.security import current_user_id

router = APIRouter()


def order_json(row: dict) -> dict:
    data = row_to_json(row)
    data["items"] = from_json(row.get("items"))
    data["recommendation_snapshot"] = from_json(row.get("recommendation_snapshot"))
    return data


@router.get("")
def list_orders(user_id: int = Depends(current_user_id)) -> ApiList:
    rows = db.fetch_all(
        """
        SELECT id, user_id, thread_id, order_number, confirmation_id,
               idempotency_key, items::text AS items, quote_ids,
               total_premium, recommendation_snapshot::text AS recommendation_snapshot,
               status, created_at, updated_at
        FROM orders
        WHERE user_id = %s
        ORDER BY created_at DESC
        """,
        (user_id,),
    )
    return ApiList(items=[order_json(row) for row in rows])


@router.post("")
def create_order(request: dict, user_id: int = Depends(current_user_id)) -> dict:
    idempotency_key = request.get("idempotency_key")
    if idempotency_key:
        existing = db.fetch_one(
            """
            SELECT id, user_id, thread_id, order_number, confirmation_id,
                   idempotency_key, items::text AS items, quote_ids,
                   total_premium, recommendation_snapshot::text AS recommendation_snapshot,
                   status, created_at, updated_at
            FROM orders
            WHERE user_id = %s AND idempotency_key = %s
            """,
            (user_id, idempotency_key),
        )
        if existing:
            return order_json(existing)

    quote_ids = [UUID(str(value)) for value in (request.get("quote_ids") or request.get("quoteIds") or [])]
    quotes = []
    total = Decimal("0")
    for quote_id in quote_ids:
        quote = db.fetch_one(
            "SELECT id, product_id, result::text AS result, total_premium, expires_at FROM premium_quotes WHERE id = %s",
            (quote_id,),
        )
        if quote is None:
            raise api_error(404, "QUOTE_NOT_FOUND", "Quote not found")
        quotes.append(quote)
        total += Decimal(str(quote["total_premium"]))

    order_id = uuid4()
    order_number = "ORD-" + datetime.now().strftime("%Y%m%d%H%M%S") + "-" + str(order_id)[:8].upper()
    items = request.get("items") or [{"quote_id": str(quote["id"]), "product_id": quote["product_id"]} for quote in quotes]
    row = db.fetch_one(
        """
        INSERT INTO orders (
            id, user_id, thread_id, order_number, confirmation_id,
            idempotency_key, items, quote_ids, total_premium,
            recommendation_snapshot, status
        )
        VALUES (%s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s::jsonb, 'pending_payment')
        RETURNING id, user_id, thread_id, order_number, confirmation_id,
                  idempotency_key, items::text AS items, quote_ids,
                  total_premium, recommendation_snapshot::text AS recommendation_snapshot,
                  status, created_at, updated_at
        """,
        (
            order_id,
            user_id,
            _uuid_or_none(request.get("thread_id") or request.get("threadId")),
            order_number,
            request.get("confirmation_id"),
            idempotency_key,
            to_json(items),
            quote_ids,
            total,
            to_json(request.get("recommendation_snapshot")),
        ),
    )
    return order_json(row)


@router.get("/{order_id}")
def get_order(order_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    row = db.fetch_one(
        """
        SELECT id, user_id, thread_id, order_number, confirmation_id,
               idempotency_key, items::text AS items, quote_ids,
               total_premium, recommendation_snapshot::text AS recommendation_snapshot,
               status, created_at, updated_at
        FROM orders
        WHERE id = %s AND user_id = %s
        """,
        (order_id, user_id),
    )
    if row is None:
        raise api_error(404, "ORDER_NOT_FOUND", "Order not found")
    return order_json(row)


@router.post("/{order_id}/cancel")
def cancel_order(order_id: UUID, user_id: int = Depends(current_user_id)) -> dict:
    updated = db.execute(
        """
        UPDATE orders
        SET status = 'cancelled', updated_at = CURRENT_TIMESTAMP
        WHERE id = %s AND user_id = %s AND status <> 'cancelled'
        """,
        (order_id, user_id),
    )
    if updated == 0:
        row = db.fetch_one("SELECT id FROM orders WHERE id = %s AND user_id = %s", (order_id, user_id))
        if row is None:
            raise api_error(404, "ORDER_NOT_FOUND", "Order not found")
    return get_order(order_id, user_id)


def _uuid_or_none(value: object) -> UUID | None:
    if value is None:
        return None
    return UUID(str(value))
