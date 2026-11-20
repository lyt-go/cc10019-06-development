"""标签快照路由：创建快照并获取结果。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse

from app.schemas import ActionPayload, ActionResult
from app.services.tag_snapshot import (
    build_snapshot_file,
    create_snapshot,
    get_snapshot,
    compare_snapshots,
    list_snapshots,
)
from app.store import store

router = APIRouter(prefix="/api/tag-snapshot", tags=["tag_snapshot"])


@router.get("")
def index(page: int = 1, size: int = 20) -> dict[str, Any]:
    rows = store.rows("tag_snapshot")
    total = len(rows)
    start = (page - 1) * size
    return {"items": rows[start : start + size], "total": total, "page": page, "size": size}




@router.get("/export")
def export_entries() -> dict[str, Any]:
    rows = store.rows("tag_snapshot")
    return {"items": rows, "total": len(rows)}
@router.get("/{entry_id}")
def detail(entry_id: int) -> dict[str, Any]:
    row = store.find("tag_snapshot", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("/{snapshot_id}/create")
def create(snapshot_id: str) -> ActionResult:
    try:
        result = create_snapshot(snapshot_id)
        return ActionResult(ok=True, message="Created", entry=result)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{snapshot_id}/export-file")
def export_file(snapshot_id: str) -> JSONResponse:
    """导出快照文件：携带标签定义字段和分群统计数据，供接收方导入画像卡片。"""
    try:
        file_payload = build_snapshot_file(snapshot_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    return JSONResponse(
        content=file_payload,
        headers={"Content-Disposition": f'attachment; filename="tag_snapshot_{snapshot_id}.json"'},
    )


@router.get("/{snapshot_id}/result")
def result(snapshot_id: str) -> dict[str, Any]:
    res = get_snapshot(snapshot_id)
    if res is None:
        raise HTTPException(status_code=404, detail="Result not found")
    return res


@router.get("/compare/{snapshot_id_a}/{snapshot_id_b}")
def compare(snapshot_id_a: str, snapshot_id_b: str) -> dict[str, Any]:
    try:
        return compare_snapshots(snapshot_id_a, snapshot_id_b)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/list/all")
def all_snapshots() -> list[dict[str, Any]]:
    return list_snapshots()


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    row = store.find("tag_snapshot", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    action = payload.action
    row["status"] = action
    row["pending"] = False
    return ActionResult(ok=True, message=action, entry=row)
