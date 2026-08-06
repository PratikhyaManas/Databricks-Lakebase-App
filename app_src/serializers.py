"""Serialization helpers for API payloads."""

from __future__ import annotations


def order_to_dict(row: tuple) -> dict:
    return {
        "order_id": row[0],
        "customer": row[1],
        "item": row[2],
        "quantity": row[3],
        "amount": float(row[4]),
        "status": row[5],
        "ordered_at": row[6].isoformat() if row[6] else None,
    }


def note_to_dict(row: tuple) -> dict:
    return {
        "id": row[0],
        "content": row[1],
        "created_at": row[2].isoformat() if row[2] else None,
    }
