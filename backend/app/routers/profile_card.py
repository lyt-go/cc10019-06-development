"""画像卡片路由：消费标签计算和分群结果生成画像，支持导入快照文件恢复历史画像。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionPayload, ActionResult
from app.services.profile_card import build_profile_card, change_card_status, get_profile_result
from app.services.snapshot_import import (
    IMPORT_STATUS_OK,
    get_import_record,
    import_snapshot_file,
    list_import_records,
)
from app.store import store

router = APIRouter(prefix="/api/profile-card", tags=["profile_card"])


@router.get("")
def index(page: int = 1, size: int = 20) -> dict[str, Any]:
    rows = store.rows("profile_card")
    total = len(rows)
    start = (page - 1) * size
    return {"items": rows[start : start + size], "total": total, "page": page, "size": size}


@router.get("/export")
def export_entries() -> dict[str, Any]:
    rows = store.rows("profile_card")
    return {"items": rows, "total": len(rows)}


@router.post("/import-snapshot")
def import_snapshot(payload: dict[str, Any]) -> ActionResult:
    """导入快照文件：同一份文件重传只产生一份导入记录。"""
    try:
        record = import_snapshot_file(payload)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    ok = record["status"] == IMPORT_STATUS_OK
    return ActionResult(ok=ok, message=record.get("error") or "Imported", entry=record)


@router.get("/imports")
def imports() -> dict[str, Any]:
    rows = list_import_records()
    return {"items": rows, "total": len(rows)}


@router.get("/imports/{import_id}")
def import_detail(import_id: str) -> dict[str, Any]:
    record = get_import_record(import_id)
    if record is None:
        raise HTTPException(status_code=404, detail="Not found")
    return record


@router.get("/{entry_id}")
def detail(entry_id: int) -> dict[str, Any]:
    row = store.find("profile_card", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/{card_id}/build")
def build(card_id: str) -> ActionResult:
    try:
        result = build_profile_card(card_id)
        return ActionResult(ok=True, message="Built", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{card_id}/result")
def result(card_id: str) -> dict[str, Any]:
    res = get_profile_result(card_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return res


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    try:
        row = change_card_status(entry_id, payload.action)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return ActionResult(ok=True, message=payload.action, entry=row)
