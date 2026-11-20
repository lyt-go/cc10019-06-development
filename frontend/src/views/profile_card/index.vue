<template>
  <section class="page" data-module="profile_card">
    <header class="page-head">
      <div><h2>画像卡片</h2><p class="page-desc">维护用户画像卡片的标签组合、数据绑定与展示配置，为画像卡片提供可验证的数据工程流程。</p></div>
    </header>
    <div class="analysis-summary">
      <article v-for="m in summaryMetrics" :key="m.label" class="analysis-card" data-testid="kpi-card">
        <span style="font-size:12px;color:var(--muted)">{{ m.label }}</span>
        <strong style="font-size:22px;display:block">{{ m.value }}</strong>
        <span :class="m.trend > 0 ? 'trend-up' : 'trend-down'" style="font-size:12px">{{ m.trend > 0 ? '↑' : '↓' }}{{ Math.abs(m.trend) }}%</span>
      </article>
    </div>
    <form class="analysis-form" @submit.prevent="runAnalysis">
      <label v-for="field in paramFields" :key="field"><span>{{ field }}</span>
        <select v-if="field.includes('方法')||field.includes('策略')||field.includes('粒度')" v-model="params[field]"><option v-for="o in options[field]" :key="o" :value="o">{{ o }}</option></select>
        <input v-else v-model="params[field]" :placeholder="`请输入${field}`" />
      </label>
      <button class="btn primary" type="submit" data-testid="run-analysis">运行分析</button>
    </form>
    <div v-if="chartData.length" class="analysis-chart">
      <div v-for="(bar, i) in chartData" :key="i" class="analysis-bar" :style="{ height: barHeight(bar.value) + 'px' }"><span>{{ bar.label }}</span></div>
    </div>
    <table class="data-table" v-if="results.length">
      <thead><tr><th v-for="c in resultColumns" :key="c">{{ c }}</th></tr></thead>
      <tbody><tr v-for="row in results" :key="row.id"><td v-for="c in resultColumns" :key="c">{{ row[c] ?? '—' }}</td></tr></tbody>
    </table>
    <p v-if="!results.length && !loading" style="text-align:center;color:var(--muted)">请配置参数后运行分析</p>

    <section class="import-panel">
      <h3>快照文件导入</h3>
      <p class="page-desc">把标签快照文件导入画像卡片，用文件中的标签定义和分群统计重建历史画像；同一份文件重传只产生一条导入记录，校验失败的卡片不能启用。</p>
      <div class="import-actions">
        <input type="file" accept="application/json,.json" data-testid="import-file" @change="onFilePicked" />
        <button class="btn primary" type="button" data-testid="submit-import" :disabled="!importPayload" @click="submitImport">导入快照文件</button>
        <span v-if="importMessage" class="error-text">{{ importMessage }}</span>
      </div>
      <table class="data-table" v-if="imports.length" data-testid="import-table">
        <thead>
          <tr><th>导入批次</th><th>来源快照</th><th>状态</th><th>标签数</th><th>分群数</th><th>失败原因</th><th>操作</th></tr>
        </thead>
        <tbody>
          <tr v-for="rec in imports" :key="rec.import_id" :data-testid="`import-${rec.import_id}`">
            <td>{{ rec.import_id }}</td>
            <td>{{ rec.snapshot_id }}</td>
            <td>{{ rec.status }}</td>
            <td>{{ rec.tag_count }}</td>
            <td>{{ rec.segment_count }}</td>
            <td>{{ rec.error || '—' }}</td>
            <td>
              <button class="link" type="button" :data-testid="`open-profile-${rec.import_id}`" :disabled="rec.status !== '导入成功'" @click="openProfile(rec)">打开画像</button>
              <button class="link" type="button" :data-testid="`show-mapping-${rec.import_id}`" @click="showMapping(rec)">字段对应</button>
            </td>
          </tr>
        </tbody>
      </table>
      <div v-if="profile" class="restored-profile" data-testid="restored-profile">
        <h4>{{ profile.card_name }}（{{ profile.source_snapshot.snapshot_id }} · {{ profile.source_snapshot.snapshot_date }}）</h4>
        <table class="data-table">
          <thead><tr><th>标签编号</th><th>原始编号</th><th>历史名称</th><th>覆盖人数</th></tr></thead>
          <tbody>
            <tr v-for="t in profile.display_tags" :key="t.tag_id">
              <td>{{ t.tag_id }}</td><td>{{ t.origin_tag_id }}</td><td>{{ t.tag_name }}</td><td>{{ t.result_count }}</td>
            </tr>
          </tbody>
        </table>
        <table class="data-table">
          <thead><tr><th>分群编号</th><th>分群名称</th><th>用户基数</th><th>分层分布</th></tr></thead>
          <tbody>
            <tr v-for="s in profile.segment_info.segments" :key="s.segment_id">
              <td>{{ s.segment_id }}</td><td>{{ s.segment_name }}</td><td>{{ s.user_count }}</td><td>{{ s.tier_distribution }}</td>
            </tr>
          </tbody>
        </table>
      </div>
      <div v-if="mapping" class="field-mapping" data-testid="field-mapping">
        <h4>实际使用的字段对应关系</h4>
        <pre>{{ mappingText }}</pre>
      </div>
    </section>
  </section>
</template>
<script setup lang="ts">
import { computed, onMounted, ref } from 'vue'
import { request } from '@/api/client'
const ENDPOINT = '/api/profile_card'
const CARD_API = '/api/profile-card'
const summaryMetrics = ref<{label:string;value:number;trend:number}[]>([])
const results = ref<any[]>([]); const chartData = ref<{label:string;value:number}[]>([])
const loading = ref(false)
const params = ref<Record<string,string>>({})
const paramFields = ["卡片编号", "卡片名称", "展示标签", "数据来源", "展示样式", "刷新策略", "关联分群", "卡片版本"].filter((f: string) => !['编号','名称','版本'].includes(f)).slice(0, 4)
const options: Record<string,string[]> = { '统计粒度': ['按日','按周','按月'], '分组字段': ['全量','按类型','按区域'], '比较方法': ['环比','同比','绝对值'], '时间范围': ['最近7天','最近30天','最近90天'] }
const resultColumns = computed(() => ["卡片编号", "卡片名称", "展示标签", "数据来源", "展示样式", "刷新策略", "关联分群", "卡片版本"].slice(0, 5))
function barHeight(v: number) { const max = Math.max(...chartData.value.map(d => d.value), 1); return Math.max(10, (v / max) * 140) }
async function fetchSummary() { try { const res = await request(`${ENDPOINT}/summary`); summaryMetrics.value = (await res.json()).metrics || [] } catch(e) {} }
async function runAnalysis() {
  loading.value = true
  try { const res = await request(`${ENDPOINT}/run`, { method: 'POST', body: JSON.stringify({ values: params.value }) }); const data = await res.json(); results.value = data.items || []; chartData.value = (data.items || []).map((r: any) => ({ label: Object.values(r)[0] as string, value: Object.values(r).filter(v => typeof v === 'number')[0] as number || 0 })).slice(0, 6) } catch(e) { results.value = [] }
  loading.value = false
}

// ========== 快照文件导入 ==========
const imports = ref<any[]>([])
const importPayload = ref<any>(null)
const importMessage = ref('')
const profile = ref<any>(null)
const mapping = ref<any>(null)
const mappingText = computed(() => JSON.stringify(mapping.value, null, 2))

function onFilePicked(event: Event) {
  const input = event.target as HTMLInputElement
  const file = input.files?.[0]
  if (!file) return
  const reader = new FileReader()
  reader.onload = () => {
    try { importPayload.value = JSON.parse(String(reader.result)); importMessage.value = '' }
    catch { importPayload.value = null; importMessage.value = '快照文件不是合法 JSON' }
  }
  reader.readAsText(file)
}

async function submitImport() {
  if (!importPayload.value) return
  try {
    const res = await request(`${CARD_API}/import-snapshot`, { method: 'POST', body: JSON.stringify(importPayload.value) })
    const data = await res.json()
    if (!res.ok) throw new Error(data.detail || '导入失败')
    importMessage.value = data.ok ? `导入成功：${data.entry.import_id}` : `导入失败：${data.message}`
    await loadImports()
  } catch (e: any) { importMessage.value = e.message || '导入失败' }
}

async function loadImports() {
  try { const res = await request(`${CARD_API}/imports`); const data = await res.json(); imports.value = data.items || [] } catch(e) {}
}

async function openProfile(rec: any) {
  try {
    const res = await request(`${CARD_API}/${rec.card_id}/result`)
    if (!res.ok) throw new Error('画像尚未启用')
    profile.value = await res.json()
  } catch(e) { profile.value = null }
}

function showMapping(rec: any) { mapping.value = rec.field_mapping }

onMounted(fetchSummary)
onMounted(loadImports)
</script>
