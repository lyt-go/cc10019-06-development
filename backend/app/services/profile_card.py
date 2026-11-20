"""画像卡片服务：消费标签计算和分群结果，生成画像卡片数据。

导入卡片（data_source=snapshot_import）的数据来自快照文件，只有导入
校验成功才能启用；普通卡片可以引用导入标签，历史统计取自快照文件。
"""
from __future__ import annotations

from typing import Any

from app.store import store
from app.services.tag_compute import get_compute_result
from app.services.user_segment import get_segment_result
from app.services.snapshot_import import (
    IMPORT_STATUS_OK,
    build_imported_card_result,
    get_import_record,
    get_imported_tag_value,
)

# 会把卡片置为启用态的动作
ENABLE_ACTIONS = {"已发布", "发布", "启用", "已启用"}


def build_profile_card(card_id: str) -> dict[str, Any]:
    """构建画像卡片，消费标签计算和分群结果。"""
    card = store.find_by_field("profile_card", "card_id", card_id)
    if card is None:
        raise ValueError(f"Profile card not found: {card_id}")

    # 导入卡片：只能从校验成功的快照文件恢复历史数据
    if card.get("data_source") == "snapshot_import":
        return build_imported_card_result(card_id)

    display_tags = card.get("display_tags", [])
    segment_id = card.get("segment_id", "")

    # 获取标签计算结果
    tag_values: list[dict[str, Any]] = []
    for tag_id in display_tags:
        # 导入标签：历史统计来自快照文件，不查当前计算任务
        imported_value = get_imported_tag_value(tag_id)
        if imported_value is not None:
            tag_values.append(imported_value)
            continue
        # 查找对应计算任务
        tasks = store.find_all_by_field("tag_compute", "tag_id", tag_id)
        for task in tasks:
            result = get_compute_result(task["task_id"])
            if result:
                tag_values.append({
                    "tag_id": tag_id,
                    "tag_name": _get_tag_name(tag_id),
                    "result_count": result.get("result_count", 0),
                    "compute_scope": result.get("compute_scope", ""),
                })

    # 获取分群结果
    segment_info = None
    if segment_id:
        seg_result = get_segment_result(segment_id)
        if seg_result:
            segment_info = {
                "segment_id": segment_id,
                "segment_name": _get_segment_name(segment_id),
                "user_count": seg_result.get("user_count", 0),
                "tier_distribution": seg_result.get("tier_distribution", {}),
            }

    result = {
        "card_id": card_id,
        "card_name": card["card_name"],
        "display_tags": tag_values,
        "segment_info": segment_info,
        "data_source": card["data_source"],
        "display_style": card["display_style"],
    }

    # 存储产物
    store.set_artifact("profile_card", card_id, result)

    # 更新状态
    store.update("profile_card", card["id"], {
        "status": "已发布",
        "pending": False,
    })

    return result


def change_card_status(entry_id: int, action: str) -> dict[str, Any]:
    """画像卡片状态流转：导入卡片只有快照文件校验成功才能启用。"""
    card = store.find("profile_card", entry_id)
    if card is None:
        raise ValueError(f"Profile card not found: {entry_id}")
    if action in ENABLE_ACTIONS and card.get("data_source") == "snapshot_import":
        record = get_import_record(card.get("import_id", ""))
        if record is None or record.get("status") != IMPORT_STATUS_OK:
            raise ValueError("快照文件校验未通过，卡片不能启用")
    updated = store.update("profile_card", entry_id, {"status": action, "pending": False})
    assert updated is not None
    return updated


def _get_tag_name(tag_id: str) -> str:
    """获取标签名称。"""
    tag = store.find_by_field("tag_define", "tag_id", tag_id)
    return tag["tag_name"] if tag else tag_id


def _get_segment_name(segment_id: str) -> str:
    """获取分群名称。"""
    seg = store.find_by_field("user_segment", "segment_id", segment_id)
    return seg["segment_name"] if seg else segment_id


def get_profile_result(card_id: str) -> dict[str, Any] | None:
    """获取画像卡片结果。"""
    artifact = store.get_artifact("profile_card", card_id)
    if artifact:
        return artifact
    try:
        return build_profile_card(card_id)
    except ValueError:
        return None
