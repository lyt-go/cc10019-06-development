"""标签快照服务：消费标签计算和分群结果，生成全量快照，并导出快照文件。

快照文件是跨环境搬迁画像数据的载体：除了配置表记录，还携带建档时的
标签定义字段和分群统计数据，并附内容校验和，供接收方导入画像卡片。
"""
from __future__ import annotations

import hashlib
import json
from typing import Any

from app.store import store
from app.services.user_segment import get_segment_result

# 快照文件标识：导入侧只接受这个类型的文件
SNAPSHOT_FILE_TYPE = "tag_snapshot_export"
SNAPSHOT_FILE_VERSION = "1.0"


def canonical_json(payload: Any) -> str:
    """内容规范化 JSON 串：键排序、无空白，用于计算文件指纹。"""
    return json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def compute_file_checksum(payload: dict[str, Any]) -> str:
    """对文件内容计算 sha256 校验和。"""
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def create_snapshot(snapshot_id: str) -> dict[str, Any]:
    """创建标签快照，消费标签计算和分群结果。"""
    snapshot = store.find_by_field("tag_snapshot", "snapshot_id", snapshot_id)
    if snapshot is None:
        raise ValueError(f"Snapshot not found: {snapshot_id}")

    # 获取所有标签定义
    tags = store.rows("tag_define")
    # 获取所有分群
    segments = store.rows("user_segment")
    # 获取标签计算结果
    compute_results = store.list_artifacts("tag_compute")

    # 每个标签的覆盖人数：取该标签各计算任务的最大结果数
    tag_user_counts: dict[str, int] = {}
    for result in compute_results:
        tag_id = result.get("tag_id")
        if tag_id:
            tag_user_counts[tag_id] = max(tag_user_counts.get(tag_id, 0), result.get("result_count", 0))

    # 计算用户基数（从标签计算结果汇总）
    total_users = max(tag_user_counts.values(), default=0)
    if total_users == 0:
        total_users = 50000  # 默认值

    # 建档时的标签定义字段 + 覆盖人数（画像数据，不只是配置）
    tag_definitions = [
        {
            "tag_id": t["tag_id"],
            "tag_name": t["tag_name"],
            "tag_level": t.get("tag_level", ""),
            "compute_logic": t.get("compute_logic", ""),
            "source_attrs": list(t.get("source_attrs", [])),
            "update_cycle": t.get("update_cycle", ""),
            "coverage_threshold": t.get("coverage_threshold", 0.0),
            "version": t.get("version", ""),
            "result_count": tag_user_counts.get(t["tag_id"], 0),
        }
        for t in tags
    ]

    # 分群统计数据（消费分群计算产物）
    segment_stats = []
    for s in segments:
        seg_result = get_segment_result(s["segment_id"]) or {}
        segment_stats.append({
            "segment_id": s["segment_id"],
            "segment_name": s["segment_name"],
            "user_count": seg_result.get("user_count", s.get("size_estimate", 0)),
            "tier_distribution": seg_result.get("tier_distribution", {}),
        })

    # 汇总快照数据
    snapshot_data = {
        "snapshot_id": snapshot_id,
        "snapshot_date": snapshot["snapshot_date"],
        "user_count": total_users,
        "tag_count": len(tag_definitions),
        "segment_count": len(segment_stats),
        "tags": tag_definitions,
        "segments": segment_stats,
        "compute_results": [
            {
                "task_id": r.get("task_id"),
                "tag_id": r.get("tag_id"),
                "result_count": r.get("result_count"),
                "compute_scope": r.get("compute_scope"),
            }
            for r in compute_results
        ],
        "snapshot_path": snapshot["snapshot_path"],
        "storage_format": snapshot["storage_format"],
    }

    # 存储快照产物
    store.set_artifact("tag_snapshot", snapshot_id, snapshot_data)
    store.add_snapshot("tag_snapshot", snapshot_data)

    # 更新快照记录
    store.update("tag_snapshot", snapshot["id"], {
        "status": "已完成",
        "pending": False,
        "user_count": total_users,
        "tag_count": len(tag_definitions),
        "segment_count": len(segment_stats),
    })

    return snapshot_data


def build_snapshot_file(snapshot_id: str) -> dict[str, Any]:
    """导出快照文件：携带标签定义字段与分群统计数据，附内容校验和。"""
    snapshot = get_snapshot(snapshot_id)
    if snapshot is None:
        raise ValueError(f"Snapshot not found: {snapshot_id}")

    file_payload: dict[str, Any] = {
        "file_type": SNAPSHOT_FILE_TYPE,
        "file_version": SNAPSHOT_FILE_VERSION,
        "snapshot_id": snapshot["snapshot_id"],
        "snapshot_date": snapshot["snapshot_date"],
        "user_count": snapshot.get("user_count", 0),
        "tag_count": len(snapshot.get("tags", [])),
        "segment_count": len(snapshot.get("segments", [])),
        "tags": snapshot.get("tags", []),
        "segments": snapshot.get("segments", []),
    }
    # 校验和覆盖除自身外的全部内容，导入侧据此确认文件未被篡改
    file_payload["checksum"] = compute_file_checksum(file_payload)
    return file_payload


def get_snapshot(snapshot_id: str) -> dict[str, Any] | None:
    """获取标签快照。"""
    artifact = store.get_artifact("tag_snapshot", snapshot_id)
    if artifact:
        return artifact
    try:
        return create_snapshot(snapshot_id)
    except ValueError:
        return None


def compare_snapshots(snapshot_id_a: str, snapshot_id_b: str) -> dict[str, Any]:
    """对比两个快照的差异。"""
    snap_a = get_snapshot(snapshot_id_a)
    snap_b = get_snapshot(snapshot_id_b)
    if snap_a is None or snap_b is None:
        raise ValueError("Snapshot not found")

    return {
        "snapshot_a": snapshot_id_a,
        "snapshot_b": snapshot_id_b,
        "user_count_diff": snap_b.get("user_count", 0) - snap_a.get("user_count", 0),
        "tag_count_diff": snap_b.get("tag_count", 0) - snap_a.get("tag_count", 0),
        "segment_count_diff": snap_b.get("segment_count", 0) - snap_a.get("segment_count", 0),
        "date_a": snap_a.get("snapshot_date"),
        "date_b": snap_b.get("snapshot_date"),
    }


def list_snapshots() -> list[dict[str, Any]]:
    """列出所有标签快照。"""
    return store.list_snapshots("tag_snapshot")
