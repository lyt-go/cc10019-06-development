"""标签定义路由：管理标签规则的定义与依赖校验。"""
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Request

from app.schemas import ActionPayload, ActionResult
from app.services.tag_define import (
    list_tags, get_tag, create_tag, update_tag, delete_tag, get_tags_by_level, validate_tag_logic,
    list_imported_tags,
)
from app.store import store, query_filters

router = APIRouter(prefix="/api/tag-define", tags=["tag_define"])


@router.get("")
def index(request: Request, page: int = 1, size: int = 20) -> dict[str, Any]:
    rows = store.rows("tag_define")
    # query contract: filters=query_filters(request)
    filters = query_filters(request)
    if filters:
        rows = [r for r in rows if all(str(r.get(k)) == str(v) for k, v in filters.items())]
    total = len(rows)
    start = (page - 1) * size
    return {"items": rows[start : start + size], "total": total, "page": page, "size": size}


@router.get("/imported")
def imported(import_id: str | None = None) -> dict[str, Any]:
    """列出快照文件导入的标签：与本地同号标签隔离，可供新卡片引用。"""
    rows = list_imported_tags(import_id)
    return {"items": rows, "total": len(rows)}


@router.get("/{entry_id}")
def detail(entry_id: int) -> dict[str, Any]:
    row = store.find("tag_define", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    return row


@router.post("")
def create(payload: dict[str, Any]) -> ActionResult:
    row = create_tag(payload)
    return ActionResult(ok=True, message="Created", entry=row)


@router.put("/{entry_id}")
def update(entry_id: int, payload: dict[str, Any]) -> ActionResult:
    row = store.find("tag_define", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    updated = update_tag(row["tag_id"], payload)
    return ActionResult(ok=True, message="Updated", entry=updated)


@router.delete("/{entry_id}")
def remove(entry_id: int) -> ActionResult:
    row = store.find("tag_define", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    delete_tag(row["tag_id"])
    return ActionResult(ok=True, message="Deleted")


@router.get("/by-level/{level}")
def by_level(level: str) -> list[dict[str, Any]]:
    return get_tags_by_level(level)


@router.get("/{tag_id}/validate")
def validate(tag_id: str) -> dict[str, Any]:
    return validate_tag_logic(tag_id)


@router.post("/{entry_id}/actions")
def run_action(entry_id: int, payload: ActionPayload) -> ActionResult:
    row = store.find("tag_define", entry_id)
    if row is None:
        raise HTTPException(status_code=404, detail="Not found")
    action = payload.action
    row["status"] = action
    row["pending"] = False
    return ActionResult(ok=True, message=action, entry=row)
