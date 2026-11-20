"""快照文件导入：把标签快照文件恢复成画像卡片，并登记导入记录。

业务规则：
- 同一份文件（内容指纹相同）重传只产生一份导入记录；失败后重传也落到原记录。
- 画像卡片用文件里的标签定义和分群统计恢复历史数据，文件中的历史字段
  含义以文件为准，不被当前字典改写。
- 导入标签以命名空间化编号登记进标签列表，与本地同号标签互不影响，
  可供新卡片引用。
- 只有标签字段和分群数据都读全且校验成功的卡片才能启用。
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.store import store
from app.services.tag_snapshot import SNAPSHOT_FILE_TYPE, compute_file_checksum

IMPORT_STATUS_OK = "导入成功"
IMPORT_STATUS_FAILED = "导入失败"

# 文件中每个标签必须读全的定义字段
REQUIRED_TAG_FIELDS = ["tag_id", "tag_name", "tag_level", "compute_logic", "source_attrs", "version"]
# 文件中每个分群必须读全的统计字段
REQUIRED_SEGMENT_FIELDS = ["segment_id", "segment_name", "user_count", "tier_distribution"]


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _next_import_id() -> str:
    max_seq = 0
    for row in store.rows("snapshot_import"):
        import_id = str(row.get("import_id", ""))
        if import_id.startswith("IMP-"):
            try:
                max_seq = max(max_seq, int(import_id.split("-", 1)[1]))
            except ValueError:
                continue
    return f"IMP-{max_seq + 1:04d}"


def get_import_record(import_id: str) -> dict[str, Any] | None:
    """按导入批次编号查询导入记录。"""
    return store.find_by_field("snapshot_import", "import_id", import_id)


def find_import_by_hash(file_hash: str) -> dict[str, Any] | None:
    """按文件内容指纹查询导入记录（幂等键）。"""
    return store.find_by_field("snapshot_import", "file_hash", file_hash)


def list_import_records() -> list[dict[str, Any]]:
    """列出所有导入记录。"""
    return store.rows("snapshot_import")


def validate_snapshot_file(payload: Any) -> list[str]:
    """校验快照文件：结构、校验和、标签字段与分群数据都要读全。返回错误列表。"""
    errors: list[str] = []
    if not isinstance(payload, dict):
        return ["快照文件必须是 JSON 对象"]
    if payload.get("file_type") != SNAPSHOT_FILE_TYPE:
        errors.append(f"文件类型应为 {SNAPSHOT_FILE_TYPE}")
    for field in ("snapshot_id", "snapshot_date", "tags", "segments", "tag_count", "segment_count"):
        if field not in payload:
            errors.append(f"缺少必填字段: {field}")
    if errors:
        return errors

    # 内容校验和：确认文件未被篡改
    checksum = payload.get("checksum")
    if checksum:
        content = {k: v for k, v in payload.items() if k != "checksum"}
        if compute_file_checksum(content) != checksum:
            errors.append("文件校验和不匹配，内容可能被篡改")

    tags = payload.get("tags")
    segments = payload.get("segments")
    if not isinstance(tags, list):
        errors.append("tags 必须是列表")
        tags = []
    if not isinstance(segments, list):
        errors.append("segments 必须是列表")
        segments = []

    # 标签定义字段读全
    for index, tag in enumerate(tags):
        if not isinstance(tag, dict):
            errors.append(f"tags[{index}] 不是对象")
            continue
        for field in REQUIRED_TAG_FIELDS:
            if field not in tag or tag[field] is None or tag[field] == "":
                errors.append(f"标签 {tag.get('tag_id', index)} 缺少字段: {field}")

    # 分群统计数据读全
    for index, seg in enumerate(segments):
        if not isinstance(seg, dict):
            errors.append(f"segments[{index}] 不是对象")
            continue
        for field in REQUIRED_SEGMENT_FIELDS:
            if field not in seg or seg[field] is None or seg[field] == "":
                errors.append(f"分群 {seg.get('segment_id', index)} 缺少字段: {field}")
        if "user_count" in seg and not isinstance(seg["user_count"], int):
            errors.append(f"分群 {seg.get('segment_id', index)} 的 user_count 必须是整数")
        if "tier_distribution" in seg and not isinstance(seg["tier_distribution"], dict):
            errors.append(f"分群 {seg.get('segment_id', index)} 的 tier_distribution 必须是对象")

    # 声明数量与实读数量一致，防止半截文件
    if isinstance(payload.get("tag_count"), int) and payload["tag_count"] != len(tags):
        errors.append(f"声明标签数 {payload['tag_count']} 与实读 {len(tags)} 不一致")
    if isinstance(payload.get("segment_count"), int) and payload["segment_count"] != len(segments):
        errors.append(f"声明分群数 {payload['segment_count']} 与实读 {len(segments)} 不一致")

    return errors


def import_snapshot_file(payload: dict[str, Any]) -> dict[str, Any]:
    """导入快照文件：幂等登记导入记录，校验通过后恢复画像卡片。"""
    if not isinstance(payload, dict):
        raise ValueError("快照文件必须是 JSON 对象")

    file_hash = compute_file_checksum(payload)
    record = find_import_by_hash(file_hash)
    if record is not None and record.get("status") == IMPORT_STATUS_OK:
        # 同一份文件重传：直接返回原导入记录，不产生新记录
        return record

    if record is None:
        import_id = _next_import_id()
        store.insert("snapshot_import", {
            "import_id": import_id,
            "file_hash": file_hash,
            "status": "校验中",
            "pending": True,
            "abnormal": False,
            "snapshot_id": payload.get("snapshot_id", ""),
            "snapshot_date": payload.get("snapshot_date", ""),
            "card_id": "",
            "tag_count": 0,
            "segment_count": 0,
            "imported_tag_ids": [],
            "field_mapping": {},
            "error": "",
            "created_at": _now(),
            "updated_at": _now(),
        })
        record = get_import_record(import_id)
    # 失败后重传：落在原导入记录上重新校验，不新建记录

    assert record is not None  # 刚插入或按指纹命中，必然存在
    errors = validate_snapshot_file(payload)
    if errors:
        _finalize_failed_import(record, payload, errors)
    else:
        _finalize_success_import(record, payload)
    return get_import_record(record["import_id"]) or record


def _finalize_failed_import(record: dict[str, Any], payload: dict[str, Any], errors: list[str]) -> None:
    """校验失败：记录原因，卡片保留但不启用。"""
    card = _ensure_import_card(record, payload)
    store.update("profile_card", card["id"], {
        "status": IMPORT_STATUS_FAILED,
        "pending": False,
        "abnormal": True,
    })
    store.update("snapshot_import", record["id"], {
        "status": IMPORT_STATUS_FAILED,
        "pending": False,
        "abnormal": True,
        "card_id": card["card_id"],
        "error": "；".join(errors),
        "updated_at": _now(),
    })


def _finalize_success_import(record: dict[str, Any], payload: dict[str, Any]) -> None:
    """校验成功：注册导入标签、恢复画像卡片并启用、记录字段对应关系。"""
    import_id = record["import_id"]

    # 1. 注册导入标签：命名空间化编号，保留文件中的历史定义
    imported_tag_ids = _register_imported_tags(import_id, payload)

    # 2. 保存文件内容产物，供恢复画像与新卡片引用
    store.set_artifact("snapshot_import", import_id, payload)

    # 3. 建/更新画像卡片并挂上导入标签
    card = _ensure_import_card(record, payload)
    store.update("profile_card", card["id"], {"display_tags": imported_tag_ids})

    # 4. 记录实际使用的字段对应关系
    field_mapping = _build_field_mapping()

    store.update("snapshot_import", record["id"], {
        "status": IMPORT_STATUS_OK,
        "pending": False,
        "abnormal": False,
        "card_id": card["card_id"],
        "tag_count": len(payload.get("tags", [])),
        "segment_count": len(payload.get("segments", [])),
        "imported_tag_ids": imported_tag_ids,
        "field_mapping": field_mapping,
        "error": "",
        "updated_at": _now(),
    })

    # 5. 用文件中的标签定义和分群统计重建画像产物（启用卡片）
    build_imported_card_result(card["card_id"])


def _ensure_import_card(record: dict[str, Any], payload: dict[str, Any]) -> dict[str, Any]:
    """为导入记录建/取画像卡片。"""
    card_id = f"PC-{record['import_id']}"
    card = store.find_by_field("profile_card", "card_id", card_id)
    if card is None:
        store.insert("profile_card", {
            "card_id": card_id,
            "card_name": f"快照{payload.get('snapshot_id', '')}历史画像",
            "display_tags": [],
            "data_source": "snapshot_import",
            "display_style": "grid",
            "refresh_strategy": "manual",
            "segment_id": "",
            "import_id": record["import_id"],
            "version": "v1.0",
            "status": "校验中",
            "pending": True,
            "abnormal": False,
        })
        card = store.find_by_field("profile_card", "card_id", card_id)
    assert card is not None
    return card


def _register_imported_tags(import_id: str, payload: dict[str, Any]) -> list[str]:
    """把文件中的标签定义注册进标签列表。

    编号加导入批次前缀做命名空间隔离：来源方和接收方即使用同一个标签
    编号标识不同人群，也不会覆盖或改写本地同号标签。
    """
    imported_tag_ids: list[str] = []
    for tag in payload.get("tags", []):
        imported_tag_id = f"{import_id}-{tag['tag_id']}"
        imported_tag_ids.append(imported_tag_id)
        row = {
            "tag_id": imported_tag_id,
            # 历史字段含义以文件为准，不被当前字典改写
            "tag_name": tag["tag_name"],
            "tag_level": tag.get("tag_level", ""),
            "compute_logic": tag.get("compute_logic", ""),
            "source_attrs": list(tag.get("source_attrs", [])),
            "update_cycle": tag.get("update_cycle", "manual"),
            "coverage_threshold": tag.get("coverage_threshold", 0.0),
            "version": tag.get("version", ""),
            "status": "已生效",
            "pending": False,
            "abnormal": False,
            "source": "snapshot_import",
            "import_id": import_id,
            "origin_tag_id": tag["tag_id"],  # 文件中的原始标签编号
            "snapshot_date": payload.get("snapshot_date", ""),
        }
        existing = store.find_by_field("tag_define", "tag_id", imported_tag_id)
        if existing is None:
            store.insert("tag_define", row)
        else:
            store.update("tag_define", existing["id"], row)
    return imported_tag_ids


def _build_field_mapping() -> dict[str, Any]:
    """画像卡片各字段与快照文件字段的实际对应关系。"""
    return {
        "tag_fields": {
            "tag_id": "tags[].tag_id",
            "tag_name": "tags[].tag_name",
            "compute_logic": "tags[].compute_logic",
            "result_count": "tags[].result_count",
        },
        "segment_fields": {
            "segment_id": "segments[].segment_id",
            "segment_name": "segments[].segment_name",
            "user_count": "segments[].user_count",
            "tier_distribution": "segments[].tier_distribution",
        },
        "card_fields": {
            "card_name": "generated:snapshot_id",
            "source_snapshot": "snapshot_id,snapshot_date",
            "user_count": "user_count",
        },
    }


def build_imported_card_result(card_id: str) -> dict[str, Any]:
    """用快照文件中的标签定义和分群统计恢复画像卡片的历史数据。

    只有导入记录校验成功的卡片才能构建（启用）；历史字段含义全部取自
    文件内容，不查当前字典。
    """
    card = store.find_by_field("profile_card", "card_id", card_id)
    if card is None:
        raise ValueError(f"Profile card not found: {card_id}")
    import_id = card.get("import_id", "")
    record = get_import_record(import_id)
    if record is None or record.get("status") != IMPORT_STATUS_OK:
        raise ValueError(f"快照文件校验未通过，卡片不能启用: {card_id}")
    payload = store.get_artifact("snapshot_import", import_id)
    if payload is None:
        raise ValueError(f"快照文件内容缺失: {import_id}")

    tags_by_origin = {t["tag_id"]: t for t in payload.get("tags", [])}
    display_tags: list[dict[str, Any]] = []
    for imported_tag_id in card.get("display_tags", []):
        tag_row = store.find_by_field("tag_define", "tag_id", imported_tag_id)
        origin_id = (tag_row or {}).get("origin_tag_id", "")
        tag_def = tags_by_origin.get(origin_id, {})
        display_tags.append({
            "tag_id": imported_tag_id,
            "origin_tag_id": origin_id,
            "tag_name": tag_def.get("tag_name", ""),
            "compute_logic": tag_def.get("compute_logic", ""),
            "result_count": tag_def.get("result_count", 0),
        })

    result = {
        "card_id": card_id,
        "card_name": card["card_name"],
        "data_source": "snapshot_import",
        "display_style": card.get("display_style", "grid"),
        "display_tags": display_tags,
        "segment_info": {
            "segments": [
                {
                    "segment_id": s["segment_id"],
                    "segment_name": s["segment_name"],
                    "user_count": s["user_count"],
                    "tier_distribution": s["tier_distribution"],
                }
                for s in payload.get("segments", [])
            ],
            "total_user_count": payload.get("user_count", 0),
        },
        "source_snapshot": {
            "snapshot_id": payload.get("snapshot_id", ""),
            "snapshot_date": payload.get("snapshot_date", ""),
        },
        "field_mapping": record.get("field_mapping", {}),
        "import_id": import_id,
    }

    store.set_artifact("profile_card", card_id, result)
    store.update("profile_card", card["id"], {
        "status": "已发布",
        "pending": False,
        "abnormal": False,
    })
    return result


def get_imported_tag_value(tag_id: str) -> dict[str, Any] | None:
    """读取导入标签在快照文件中的历史统计，供新卡片编排时引用。"""
    tag_row = store.find_by_field("tag_define", "tag_id", tag_id)
    if tag_row is None or tag_row.get("source") != "snapshot_import":
        return None
    payload = store.get_artifact("snapshot_import", tag_row.get("import_id", ""))
    if payload is None:
        return None
    origin_id = tag_row.get("origin_tag_id", "")
    for tag_def in payload.get("tags", []):
        if tag_def.get("tag_id") == origin_id:
            return {
                "tag_id": tag_id,
                "origin_tag_id": origin_id,
                "tag_name": tag_def.get("tag_name", ""),
                "result_count": tag_def.get("result_count", 0),
                "compute_scope": "snapshot_import",
            }
    return None
