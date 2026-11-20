<template>
  <section class="page" data-module="tag_snapshot">
    <header class="page-head">
      <div><h2>标签快照</h2><p class="page-desc">维护用户标签体系的周期快照、版本追溯与变更对比管理，为标签快照提供可验证的数据工程流程。</p></div>
      <div class="page-actions">
        <button class="btn primary" type="button" data-testid="open-create" @click="openCreate">登记快照记录</button>
        <button class="btn" type="button" data-testid="export" @click="exportRows">导出作业清单</button>
      </div>
    </header>
    <div class="filter-bar">
      <label><span>开始日期</span><input type="date" v-model="dateFrom" /></label>
      <label><span>结束日期</span><input type="date" v-model="dateTo" /></label>
      <button class="btn" type="button" @click="reload">查询</button>
    </div>
    <div class="timeline-wrap">
      <div v-for="item in timelineItems" :key="item.id" class="timeline-row">
        <span class="timeline-label">{{ item.name || item.label }}</span>
        <div class="timeline-track">
          <div class="timeline-bar" :class="`status-${item.status}`" :style="{ left: barLeft(item) + '%', width: barWidth(item) + '%' }" :data-testid="`bar-${item.id}`" :title="`${item.start} ~ ${item.end}`" @click="selectItem(item)">&nbsp;</div>
        </div>
        <span style="font-size:12px;color:var(--muted);margin-left:8px;">{{ item.start }} ~ {{ item.end }}</span>
      </div>
      <p v-if="!timelineItems.length" style="text-align:center;color:var(--muted)">暂无作业记录</p>
    </div>
    <div v-if="selectedItem" class="timeline-log" data-testid="timeline-log">
      <strong>{{ selectedItem.name || selectedItem.label }}</strong> — 状态：{{ selectedItem.status }}
      <div style="margin-top:4px;">{{ selectedItem.logs || '暂无日志' }}</div>
    </div>
    <h3 class="section-title">快照记录与快照文件</h3>
    <p class="page-desc">快照文件携带建档时的标签定义字段和分群统计数据，可导入接收方的画像卡片重建历史统计。</p>
    <table class="data-table" data-testid="snapshot-file-table">
      <thead>
        <tr><th>快照编号</th><th>快照日期</th><th>用户基数</th><th>标签数量</th><th>分群数量</th><th>操作</th></tr>
      </thead>
      <tbody>
        <tr v-for="row in snapshotRows" :key="row.snapshot_id" :data-testid="`snapshot-${row.snapshot_id}`">
          <td>{{ row.snapshot_id }}</td>
          <td>{{ row.snapshot_date }}</td>
          <td>{{ row.user_count }}</td>
          <td>{{ row.tag_count }}</td>
          <td>{{ row.segment_count }}</td>
          <td>
            <button class="link" type="button" :data-testid="`export-file-${row.snapshot_id}`" @click="exportSnapshotFile(row)">导出快照文件</button>
          </td>
        </tr>
        <tr v-if="!snapshotRows.length"><td colspan="6" class="empty-state">暂无快照记录</td></tr>
      </tbody>
    </table>
    <div v-if="showCreate" class="modal-backdrop" data-testid="create-modal">
      <form class="modal" @submit.prevent="submitCreate"><h3>登记快照记录</h3>
        <label v-for="field in columns.slice(0,3)" :key="field" class="create-field"><span>{{ field }}</span><input v-model="createValues[field]" :placeholder="`请输入${field}`" required /></label>
        <div style="display:flex;gap:8px;justify-content:flex-end;margin-top:12px">
          <button class="btn" type="button" @click="showCreate=false">取消</button>
          <button class="btn primary" type="submit" data-testid="submit-create">提交</button>
        </div>
      </form>
    </div>
  </section>
</template>
<script setup lang="ts">
import { onMounted, ref } from 'vue'
import { request } from '@/api/client'
const ENDPOINT = '/api/tag_snapshot'
const SNAP_API = '/api/tag-snapshot'
const columns = ["快照编号", "快照日期", "用户基数", "标签数量", "分群数量", "快照路径", "存储格式", "保留天数"]
const actions = ["创建快照", "确认完成", "标记过期"]
const timelineItems = ref<any[]>([])
const selectedItem = ref<any>(null)
const dateFrom = ref(''); const dateTo = ref('')
const errorMessage = ref(''); const showCreate = ref(false)
const createValues = ref<Record<string,string>>({})
const allItems = ref<any[]>([])
const snapshotRows = ref<any[]>([])
function barLeft(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 0; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return ((new Date(item.start).getTime() - min) / range) * 100 }
function barWidth(item: any) { const all = allItems.value.filter(i => i.start && i.end); if(!all.length) return 20; const min = Math.min(...all.map(i => new Date(i.start).getTime())); const max = Math.max(...all.map(i => new Date(i.end).getTime())); const range = max - min || 86400000; return Math.max(5, ((new Date(item.end).getTime() - new Date(item.start).getTime()) / range) * 100) }
function selectItem(item: any) { selectedItem.value = selectedItem.value?.id === item.id ? null : item }
async function reload() {
  try { const res = await request(ENDPOINT); const data = await res.json(); allItems.value = data.items || []; applyFilter() } catch(e) { errorMessage.value = '加载失败' }
}
function applyFilter() {
  let items = allItems.value
  if(dateFrom.value) items = items.filter((i: any) => i.start >= dateFrom.value)
  if(dateTo.value) items = items.filter((i: any) => i.end <= dateTo.value)
  timelineItems.value = items; selectedItem.value = null
}
function openCreate() { createValues.value = {}; showCreate.value = true }
async function submitCreate() {
  try { const res = await request(ENDPOINT, { method: 'POST', body: JSON.stringify({ values: createValues.value }) }); if(!res.ok) throw new Error('创建失败'); showCreate.value = false; await reload() } catch(e: any) { errorMessage.value = e.message }
}
function exportRows() { window.open(`${ENDPOINT}/export`, '_blank') }
async function loadSnapshots() {
  try { const res = await request(SNAP_API); const data = await res.json(); snapshotRows.value = data.items || [] } catch(e) { errorMessage.value = '快照记录加载失败' }
}
function exportSnapshotFile(row: any) { window.open(`${SNAP_API}/${row.snapshot_id}/export-file`, '_blank') }
onMounted(reload)
onMounted(loadSnapshots)
</script>
