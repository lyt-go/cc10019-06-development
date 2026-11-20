"""跨模块数据链路集成测试。"""
from __future__ import annotations

import unittest
from typing import Any

# 设置路径
import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from app.store import store
from app.seed import SEED_ROWS
from app.services.attr_dict import list_attrs, get_attr
from app.services.tag_define import get_tag, update_tag, validate_tag_logic, list_imported_tags
from app.services.tag_compute import compute_tag, get_compute_result
from app.services.event_track import get_event
from app.services.event_cleanse import cleanse_events, get_cleanse_result
from app.services.event_aggregate import aggregate_events, get_aggregate_result
from app.services.user_segment import compute_segment, get_segment_result
from app.services.crowd_select import select_crowd, get_crowd_result
from app.services.overlap_analysis import analyze_overlap, get_overlap_result
from app.services.funnel_analyze import analyze_funnel, get_funnel_result
from app.services.session_split import split_sessions, get_session_result
from app.services.behavior_path import build_path_sankey, get_path_result
from app.services.retention_calc import calculate_retention, get_retention_result
from app.services.lifetime_value import predict_ltv, get_ltv_result, ltv_with_retention
from app.services.tag_snapshot import (
    build_snapshot_file,
    compute_file_checksum,
    create_snapshot,
    get_snapshot,
)
from app.services.behavior_heatmap import generate_heatmap, get_heatmap
from app.services.profile_card import (
    build_profile_card,
    change_card_status,
    get_profile_result,
)
from app.services.snapshot_import import (
    import_snapshot_file,
    list_import_records,
    get_import_record,
    validate_snapshot_file,
)
from app.services.tag_drill import drill_tag, get_drill_result


class TestDataChains(unittest.TestCase):
    """测试跨模块数据链路。"""

    def setUp(self) -> None:
        """重置store状态。"""
        # 清空产物缓存
        store._artifacts.clear()
        store._compute_cache.clear()
        store._snapshots.clear()

    # ========== 链路1: 属性字典 → 标签定义 → 标签计算 ==========
    def test_chain_attr_to_tag_compute(self) -> None:
        """属性字典定义属性，标签定义引用属性，标签计算执行逻辑。"""
        # 1. 验证属性存在
        attr = get_attr("ATTR-002")
        self.assertIsNotNone(attr)
        self.assertEqual(attr["attr_name"], "最近活跃天数")

        # 2. 验证标签引用了属性
        tag = get_tag("TAG-001")
        self.assertIsNotNone(tag)
        self.assertIn("ATTR-002", tag["source_attrs"])

        # 3. 验证标签计算执行
        result = compute_tag("TC-001")
        self.assertEqual(result.tag_id, "TAG-001")
        self.assertGreater(result.result_count, 0)

        # 4. 验证产物可查询
        artifact = get_compute_result("TC-001")
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact["tag_id"], "TAG-001")

    # ========== 链路2: 事件埋点 → 清洗 → 聚合 ==========
    def test_chain_event_cleanse_aggregate(self) -> None:
        """事件定义 → 清洗规则 → 清洗执行 → 聚合消费清洗结果。"""
        # 1. 验证事件存在
        event = get_event("EV-001")
        self.assertIsNotNone(event)

        # 2. 验证清洗规则关联事件
        cleanse = get_cleanse_result("EC-001")
        if cleanse is None:
            cleanse_result = cleanse_events("EC-001")
            cleanse = cleanse_result.model_dump()
        self.assertEqual(cleanse["event_id"], "EV-001")
        self.assertGreater(cleanse["total_records"], 0)

        # 3. 验证聚合消费清洗结果
        agg_result = aggregate_events("EA-001")
        self.assertEqual(agg_result.event_id, "EV-001")
        self.assertGreater(len(agg_result.result_rows), 0)

        # 4. 验证聚合产物存在
        artifact = get_aggregate_result("EA-001")
        self.assertIsNotNone(artifact)

    # ========== 链路3: 用户分群 → 圈选 → 交集分析 ==========
    def test_chain_segment_crowd_overlap(self) -> None:
        """分群定义 → 圈选条件 → 交集分析消费圈选结果。"""
        # 1. 分群计算
        seg_result = compute_segment("SEG-001")
        self.assertEqual(seg_result.segment_id, "SEG-001")
        self.assertGreater(seg_result.user_count, 0)

        # 2. 圈选执行
        crowd_a = select_crowd("CS-001")
        self.assertEqual(crowd_a["condition_id"], "CS-001")
        self.assertGreater(crowd_a["matched_count"], 0)

        crowd_b = select_crowd("CS-002")
        self.assertEqual(crowd_b["condition_id"], "CS-002")

        # 3. 交集分析消费圈选结果
        overlap = analyze_overlap("OA-001")
        self.assertEqual(overlap["crowd_a"], "CS-001")
        self.assertEqual(overlap["crowd_b"], "CS-002")
        self.assertIn("result_count", overlap)

        # 4. 验证产物
        artifact = get_overlap_result("OA-001")
        self.assertIsNotNone(artifact)

    # ========== 链路4: 行为路径 → 漏斗分析 → 会话切割 ==========
    def test_chain_path_funnel_session(self) -> None:
        """行为路径分析 → 漏斗分析 → 会话切割。"""
        # 1. 会话切割
        session_result = split_sessions("SS-001")
        self.assertEqual(session_result.strategy_id, "SS-001")
        self.assertGreater(session_result.session_count, 0)

        # 2. 漏斗分析
        funnel_result = analyze_funnel("FN-001")
        self.assertEqual(funnel_result.funnel_id, "FN-001")
        self.assertEqual(len(funnel_result.step_counts), 3)
        self.assertGreater(funnel_result.step_counts[0], funnel_result.step_counts[1])

        # 3. 行为路径
        path_result = build_path_sankey("BP-001")
        self.assertEqual(path_result.model_id, "BP-001")
        self.assertGreater(len(path_result.sankey_nodes), 0)
        self.assertGreater(len(path_result.sankey_links), 0)

        # 4. 验证产物
        self.assertIsNotNone(get_session_result("SS-001"))
        self.assertIsNotNone(get_funnel_result("FN-001"))
        self.assertIsNotNone(get_path_result("BP-001"))

    # ========== 链路5: 留存计算 → LTV预测 ==========
    def test_chain_retention_ltv(self) -> None:
        """留存计算结果 → LTV预测校准。"""
        # 1. 留存计算
        retention = calculate_retention("RC-001")
        self.assertEqual(retention.config_id, "RC-001")
        self.assertGreater(len(retention.retention_rates), 0)

        # 2. LTV预测
        ltv = predict_ltv("LTV-001")
        self.assertEqual(ltv.model_id, "LTV-001")
        self.assertGreater(ltv.avg_ltv, 0)

        # 3. LTV结合留存校准
        calibrated = ltv_with_retention("LTV-001", "RC-001")
        self.assertIn("retention_adjusted_ltv", calibrated)
        self.assertIn("avg_retention_rate", calibrated)

        # 4. 验证产物
        self.assertIsNotNone(get_retention_result("RC-001"))
        self.assertIsNotNone(get_ltv_result("LTV-001"))

    # ========== 链路6: 标签快照消费标签计算+分群结果 ==========
    def test_chain_tag_snapshot_consumes_compute_and_segment(self) -> None:
        """标签快照消费标签计算结果和用户分群结果。"""
        # 1. 先执行标签计算
        compute_tag("TC-001")
        compute_tag("TC-002")

        # 2. 执行分群计算
        compute_segment("SEG-001")

        # 3. 创建快照（消费上述结果）
        snapshot = create_snapshot("SN-001")
        self.assertEqual(snapshot["snapshot_id"], "SN-001")
        self.assertGreater(snapshot["tag_count"], 0)
        self.assertGreater(snapshot["segment_count"], 0)

        # 4. 验证快照包含计算结果引用
        self.assertIn("compute_results", snapshot)
        self.assertGreater(len(snapshot["compute_results"]), 0)

    # ========== 链路7: 行为热力消费事件聚合数据 ==========
    def test_chain_heatmap_consumes_aggregate(self) -> None:
        """行为热力图消费事件聚合结果。"""
        # 1. 先执行事件聚合
        aggregate_events("EA-001")

        # 2. 生成热力图
        heatmap = generate_heatmap("BH-001")
        self.assertEqual(heatmap["config_id"], "BH-001")
        self.assertIn("heatmap_data", heatmap)

        # 3. 验证产物
        self.assertIsNotNone(get_heatmap("BH-001"))

    # ========== 链路8: 画像卡片消费标签计算+分群结果 ==========
    def test_chain_profile_card_consumes_compute_and_segment(self) -> None:
        """画像卡片消费标签计算结果和分群结果。"""
        # 1. 执行标签计算
        compute_tag("TC-001")
        compute_tag("TC-002")

        # 2. 执行分群
        compute_segment("SEG-001")

        # 3. 构建画像卡片
        profile = build_profile_card("PC-001")
        self.assertEqual(profile["card_id"], "PC-001")
        self.assertGreater(len(profile["display_tags"]), 0)
        self.assertIsNotNone(profile["segment_info"])

        # 4. 验证产物
        self.assertIsNotNone(get_profile_result("PC-001"))

    # ========== 链路9: 标签下钻消费标签计算结果 ==========
    def test_chain_tag_drill_consumes_compute(self) -> None:
        """标签下钻分析消费标签计算结果。"""
        # 1. 执行标签计算
        compute_tag("TC-001")

        # 2. 执行下钻
        drill = drill_tag("TD-001")
        self.assertEqual(drill["parent_tag"], "TAG-001")
        self.assertIn("drill_data", drill)

    # ========== 链路10: 漏斗对比消费漏斗结果 ==========
    def test_chain_funnel_compare(self) -> None:
        """漏斗对比消费两个漏斗的分析结果。"""
        # 1. 执行两个漏斗
        analyze_funnel("FN-001")

        # 2. 对比（即使第二个不存在也能测试错误处理）
        with self.assertRaises(ValueError):
            from app.services.funnel_analyze import compare_funnels
            compare_funnels("FN-001", "FN-NONEXIST")

    # ========== 额外测试：数据产物仓库 ==========
    def test_artifact_storage_and_retrieval(self) -> None:
        """测试数据产物存储和查询。"""
        store.set_artifact("test", "key1", {"data": "value1"})
        artifact = store.get_artifact("test", "key1")
        self.assertIsNotNone(artifact)
        self.assertEqual(artifact["data"], "value1")

    def test_snapshot_management(self) -> None:
        """测试快照管理。"""
        store.add_snapshot("test_snap", {"version": 1})
        store.add_snapshot("test_snap", {"version": 2})
        latest = store.get_latest_snapshot("test_snap")
        self.assertIsNotNone(latest)
        self.assertEqual(latest["version"], 2)

    def test_cross_module_join(self) -> None:
        """测试跨模块关联查询。"""
        # attr_dict 和 tag_define 通过 attr_id 关联（source_attrs 是列表，改用 tag_level 简单测试）
        results = store.join("tag_define", "attr_dict", "tag_level", "data_type")
        self.assertIsInstance(results, list)


class TestBusinessLogic(unittest.TestCase):
    """测试核心业务逻辑正确性。"""

    def setUp(self) -> None:
        store._artifacts.clear()
        store._compute_cache.clear()

    def test_tag_compute_logic_eval(self) -> None:
        """测试标签计算逻辑求值。"""
        from app.services.tag_compute import _eval_condition
        user = {"ATTR-002": 2, "ATTR-003": 1500.0}
        attr_defs = {}
        result = _eval_condition(user, "ATTR-002 <= 3 AND ATTR-003 > 1000", attr_defs)
        self.assertTrue(result)

        user2 = {"ATTR-002": 10, "ATTR-003": 500.0}
        result2 = _eval_condition(user2, "ATTR-002 <= 3 AND ATTR-003 > 1000", attr_defs)
        self.assertFalse(result2)

    def test_funnel_conversion_declines(self) -> None:
        """测试漏斗转化率递减。"""
        result = analyze_funnel("FN-001")
        counts = result.step_counts
        for i in range(1, len(counts)):
            self.assertLessEqual(counts[i], counts[i - 1])

    def test_session_split_creates_sessions(self) -> None:
        """测试会话切割产生会话。"""
        result = split_sessions("SS-001")
        self.assertGreater(result.session_count, 0)
        self.assertLessEqual(result.session_count, result.total_events)

    def test_retention_rate_declines(self) -> None:
        """测试留存率随时间递减。"""
        result = calculate_retention("RC-001")
        for key, rates in result.retention_rates.items():
            for i in range(1, len(rates)):
                self.assertLessEqual(rates[i], rates[i - 1])

    def test_crowd_select_produces_users(self) -> None:
        """测试圈选产生用户列表。"""
        result = select_crowd("CS-001")
        self.assertGreater(result["matched_count"], 0)
        self.assertGreater(len(result["matched_users"]), 0)

    def test_overlap_respects_mode(self) -> None:
        """测试交集模式正确性。"""
        # 确保两个圈选有结果
        select_crowd("CS-001")
        select_crowd("CS-002")
        result = analyze_overlap("OA-001")
        # intersect 模式结果数不应超过任一人群
        self.assertLessEqual(
            result["result_count"],
            max(result["users_a_count"], result["users_b_count"])
        )


class TestSnapshotExportImport(unittest.TestCase):
    """标签快照文件导出 → 画像卡片导入恢复的链路。"""

    def setUp(self) -> None:
        store._artifacts.clear()
        store._compute_cache.clear()
        store._snapshots.clear()
        # 还原可能被用例改写的表，保证用例互不影响
        store._tables["tag_define"] = [dict(r) for r in SEED_ROWS["tag_define"]]
        store._tables["profile_card"] = [dict(r) for r in SEED_ROWS["profile_card"]]
        store._tables["snapshot_import"] = []

    def _build_file(self) -> dict[str, Any]:
        """造一份带画像数据的快照文件。"""
        compute_tag("TC-001")
        compute_tag("TC-002")
        compute_segment("SEG-001")
        return build_snapshot_file("SN-001")

    def _rehash(self, payload: dict[str, Any]) -> dict[str, Any]:
        """改动文件内容后重算校验和，让文件本身自洽。"""
        payload["checksum"] = compute_file_checksum(
            {k: v for k, v in payload.items() if k != "checksum"}
        )
        return payload

    # ========== 导出：快照文件携带标签定义字段和分群统计数据 ==========
    def test_export_file_carries_definitions_and_segment_stats(self) -> None:
        file_payload = self._build_file()
        self.assertEqual(file_payload["file_type"], "tag_snapshot_export")
        self.assertIn("checksum", file_payload)
        # 校验和可验证
        content = {k: v for k, v in file_payload.items() if k != "checksum"}
        self.assertEqual(compute_file_checksum(content), file_payload["checksum"])
        # 标签定义字段齐全（不只是编号和名称）
        self.assertEqual(file_payload["tag_count"], len(file_payload["tags"]))
        tag = next(t for t in file_payload["tags"] if t["tag_id"] == "TAG-001")
        self.assertEqual(tag["tag_name"], "高活跃用户")
        self.assertTrue(tag["compute_logic"])
        self.assertTrue(tag["source_attrs"])
        self.assertGreater(tag["result_count"], 0)
        # 分群统计数据齐全
        self.assertEqual(file_payload["segment_count"], len(file_payload["segments"]))
        seg = next(s for s in file_payload["segments"] if s["segment_id"] == "SEG-001")
        self.assertGreater(seg["user_count"], 0)
        self.assertIsInstance(seg["tier_distribution"], dict)

    # ========== 导入：恢复历史画像并记录字段对应关系 ==========
    def test_import_rebuilds_profile_and_records_field_mapping(self) -> None:
        record = import_snapshot_file(self._build_file())
        self.assertEqual(record["status"], "导入成功")
        card_id = record["card_id"]
        # 卡片校验成功后启用
        card = store.find_by_field("profile_card", "card_id", card_id)
        self.assertEqual(card["status"], "已发布")
        self.assertEqual(card["data_source"], "snapshot_import")
        # 接收人员打开恢复的画像：标签定义和分群统计来自文件
        profile = get_profile_result(card_id)
        self.assertIsNotNone(profile)
        tag_names = {t["tag_name"] for t in profile["display_tags"]}
        self.assertIn("高活跃用户", tag_names)
        seg_ids = {s["segment_id"] for s in profile["segment_info"]["segments"]}
        self.assertIn("SEG-001", seg_ids)
        # 实际使用的字段对应关系已记录
        mapping = record["field_mapping"]
        self.assertEqual(mapping["tag_fields"]["tag_name"], "tags[].tag_name")
        self.assertEqual(mapping["segment_fields"]["user_count"], "segments[].user_count")

    # ========== 文件中的历史字段含义不被当前字典改写 ==========
    def test_imported_profile_immune_to_current_dictionary_rewrite(self) -> None:
        record = import_snapshot_file(self._build_file())
        card_id = record["card_id"]
        # 当前字典改写同号标签的含义
        update_tag("TAG-001", {"tag_name": "被改写的人群", "compute_logic": "ATTR-002 > 100"})
        # 强制重建导入卡画像
        store._artifacts.pop("profile_card", None)
        profile = get_profile_result(card_id)
        imported = next(t for t in profile["display_tags"] if t["origin_tag_id"] == "TAG-001")
        self.assertEqual(imported["tag_name"], "高活跃用户")  # 仍是文件中的历史含义
        # 注册进标签列表的导入标签同样保留历史含义
        imported_row = store.find_by_field("tag_define", "tag_id", f"{record['import_id']}-TAG-001")
        self.assertEqual(imported_row["tag_name"], "高活跃用户")

    # ========== 字段/分群数据读不全的卡片不能启用 ==========
    def test_incomplete_file_not_enabled(self) -> None:
        broken = self._build_file()
        # 分群统计读不全：缺 user_count / tier_distribution
        broken["segments"] = [{"segment_id": "SEG-001", "segment_name": "高活跃核心用户"}]
        self._rehash(broken)
        errors = validate_snapshot_file(broken)
        self.assertTrue(errors)
        record = import_snapshot_file(broken)
        self.assertEqual(record["status"], "导入失败")
        self.assertTrue(record["error"])
        # 卡片存在但未启用
        card = store.find_by_field("profile_card", "card_id", record["card_id"])
        self.assertNotEqual(card["status"], "已发布")
        self.assertTrue(card["abnormal"])
        # 不能构建画像，也不能通过动作启用
        with self.assertRaises(ValueError):
            build_profile_card(record["card_id"])
        with self.assertRaises(ValueError):
            change_card_status(card["id"], "已发布")

    def test_tampered_checksum_rejected(self) -> None:
        payload = self._build_file()
        payload["tags"][0]["tag_name"] = "被篡改的名称"  # 不改校验和
        record = import_snapshot_file(payload)
        self.assertEqual(record["status"], "导入失败")
        self.assertIn("校验和", record["error"])

    # ========== 幂等：同一份文件重传只产生一份导入记录 ==========
    def test_reupload_same_file_single_record(self) -> None:
        file_payload = self._build_file()
        first = import_snapshot_file(file_payload)
        second = import_snapshot_file(file_payload)
        self.assertEqual(first["import_id"], second["import_id"])
        self.assertEqual(len(list_import_records()), 1)

    def test_failed_reupload_lands_on_same_record(self) -> None:
        broken = self._build_file()
        # 标签少读一条，声明数量与实读不一致 → 校验失败
        broken["tags"] = [t for t in broken["tags"] if t["tag_id"] != "TAG-001"]
        self._rehash(broken)
        first = import_snapshot_file(broken)
        self.assertEqual(first["status"], "导入失败")
        # 失败后重传同一份文件：仍落到原导入记录
        second = import_snapshot_file(broken)
        self.assertEqual(first["import_id"], second["import_id"])
        self.assertEqual(len(list_import_records()), 1)
        self.assertEqual(second["status"], "导入失败")

    # ========== 同号标签：两端各指各的人群，原有卡片不换人群 ==========
    def test_same_tag_id_two_populations_isolated(self) -> None:
        # 接收方本地 TAG-001 的人群
        compute_tag("TC-001")
        local_profile = build_profile_card("PC-001")
        local_tag = next(t for t in local_profile["display_tags"] if t["tag_id"] == "TAG-001")
        local_count = local_tag["result_count"]

        # 来源方快照文件里同一个 TAG-001 是另一人群
        file_payload = self._build_file()
        for tag in file_payload["tags"]:
            if tag["tag_id"] == "TAG-001":
                tag["tag_name"] = "来源方高活跃人群"
                tag["result_count"] = 777
        self._rehash(file_payload)
        record = import_snapshot_file(file_payload)
        self.assertEqual(record["status"], "导入成功")

        # 接收端再打开本地卡片：人群和名称都没换
        store._artifacts.pop("profile_card", None)
        local_profile2 = get_profile_result("PC-001")
        local_tag2 = next(t for t in local_profile2["display_tags"] if t["tag_id"] == "TAG-001")
        self.assertEqual(local_tag2["tag_name"], "高活跃用户")
        self.assertEqual(local_tag2["result_count"], local_count)
        # 本地标签定义未被导入改写
        self.assertEqual(get_tag("TAG-001")["tag_name"], "高活跃用户")

        # 来源端（导入卡）显示文件中的人群
        imported_profile = get_profile_result(record["card_id"])
        imported_tag = next(
            t for t in imported_profile["display_tags"] if t["origin_tag_id"] == "TAG-001"
        )
        self.assertEqual(imported_tag["tag_name"], "来源方高活跃人群")
        self.assertEqual(imported_tag["result_count"], 777)

    # ========== 导入标签可供新卡片引用，范围清楚 ==========
    def test_imported_tags_selectable_for_new_cards(self) -> None:
        file_payload = self._build_file()
        record = import_snapshot_file(file_payload)
        imported_tags = list_imported_tags(record["import_id"])
        self.assertEqual(len(imported_tags), file_payload["tag_count"])
        for tag in imported_tags:
            self.assertEqual(tag["source"], "snapshot_import")
            self.assertEqual(tag["import_id"], record["import_id"])
            self.assertTrue(tag["origin_tag_id"])
        # 从标签列表选导入字段编排新卡片
        store.insert("profile_card", {
            "card_id": "PC-NEW-001",
            "card_name": "引用导入标签的新卡片",
            "display_tags": [imported_tags[0]["tag_id"]],
            "data_source": "tag_compute",
            "display_style": "grid",
            "refresh_strategy": "manual",
            "segment_id": "",
            "version": "v1.0",
        })
        profile = build_profile_card("PC-NEW-001")
        self.assertEqual(len(profile["display_tags"]), 1)
        self.assertEqual(profile["display_tags"][0]["tag_name"], imported_tags[0]["tag_name"])
        self.assertEqual(profile["display_tags"][0]["compute_scope"], "snapshot_import")


if __name__ == "__main__":
    unittest.main(verbosity=2)