<template>
  <div class="page">
    <div class="card">
      <div class="card-title">📈 {{ current?.name || '选择食材' }} 价格走势
        <van-button size="mini" plain @click="showPicker = true">切换食材</van-button>
      </div>
      <van-tabs v-model:active="rangeTab" @change="loadTrend" shrink>
        <van-tab title="周" /><van-tab title="月" /><van-tab title="季" />
      </van-tabs>
      <div ref="chartEl" style="width:100%;height:260px;margin-top:8px"></div>
      <div class="muted">数据来源：{{ chartSource || '—' }} · 支持双指缩放/横滑</div>
    </div>

    <div class="card">
      <div class="card-title">今日行情
        <van-search v-model="kw" placeholder="搜索食材" shape="round"
          style="flex:1;margin-left:8px;padding:0" />
      </div>
      <div v-for="p in filtered" :key="p.ingredient_id">
        <van-cell :title="`${p.icon} ${p.name}`"
          :label="`${p.category} · ${p.spec || '—'}`"
          clickable @click="toggleExpand(p)">
          <template #value>
            <template v-if="p.available">
              <b>¥{{ p.price }}</b>
              <span v-if="p.change_7d != null" :class="p.change_7d >= 0 ? 'up' : 'down'" style="font-size:12px;margin-left:6px">
                {{ p.change_7d >= 0 ? '↑' : '↓' }}{{ Math.abs(p.change_7d) }}%</span>
              <span v-else class="muted" style="font-size:12px;margin-left:6px">—</span>
              <van-tag plain type="primary" style="margin-left:6px;vertical-align:middle">{{ p.source }}</van-tag>
            </template>
            <van-tag v-else color="#c8c9cc">暂无可靠价</van-tag>
          </template>
        </van-cell>

        <!-- 展开：数据来源详情 + 修正单位 -->
        <div v-if="expanded === p.ingredient_id" class="detail-panel">
          <div class="detail-row">
            <span class="detail-label">来源</span>
            <span>{{ p.source }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">规格</span>
            <span>{{ p.spec || '—' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">价格</span>
            <span>¥{{ p.price }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-label">日期</span>
            <span>{{ p.date || '—' }}</span>
          </div>

          <!-- 电商参考价未被归一化 → 允许手动修正单位 -->
          <div v-if="p.source === '电商平台参考价' && !isNormalized(p.spec)" style="margin-top:10px">
            <van-field v-model="editWeight[p.ingredient_id]" placeholder="如 5kg、500g、1斤"
              label="修正为" center clearable
              :rules="[{ required: true }]">
              <template #button>
                <van-button size="small" type="primary" :loading="saving[p.ingredient_id]"
                  @click.stop="doNormalize(p)">确定</van-button>
              </template>
            </van-field>
            <div class="muted" style="padding:0 16px 8px">输入该商品的实际克重，系统自动按 元/500克 计算</div>
          </div>

          <van-button size="small" style="margin-top:6px" @click="select(p)">查看走势</van-button>
        </div>
      </div>
    </div>

    <van-popup v-model:show="showPicker" round position="bottom">
      <van-picker :columns="pickCols" @confirm="onPickConfirm" @cancel="showPicker = false" />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick, reactive } from 'vue'
import { showSuccessToast, showFailToast } from 'vant'
import * as echarts from 'echarts'
import api from '../api'

const prices = ref([])
const current = ref(null)
const kw = ref('')
const rangeTab = ref(1)
const showPicker = ref(false)
const chartEl = ref(null)
const chartSource = ref('')
const expanded = ref(null)
const editWeight = reactive({})
const saving = reactive({})
let chart = null

const pickCols = computed(() =>
  prices.value.map(p => ({ text: p.icon + ' ' + p.name, value: p.ingredient_id })))

const filtered = computed(() =>
  prices.value.filter(p => !kw.value || p.name.includes(kw.value)))

function isNormalized(spec) {
  return spec && spec !== '参考价(电商)' && spec !== '500g' && spec !== '—'
}

function toggleExpand(p) {
  expanded.value = expanded.value === p.ingredient_id ? null : p.ingredient_id
}

function select(p) {
  current.value = p
  loadTrend()
}

async function doNormalize(p) {
  const w = editWeight[p.ingredient_id]
  if (!w) return
  saving[p.ingredient_id] = true
  try {
    const res = await api.normalizePrice(p.ingredient_id, w)
    showSuccessToast(`已修正: ¥${res.old_price}→¥${res.new_price} (${res.parsed_weight_g}g)`)
    // 刷新当前页
    prices.value = await api.latestPrices()
    expanded.value = null
  } catch {
    showFailToast('修正失败，请检查格式（如 5kg、500g、1斤）')
  } finally {
    saving[p.ingredient_id] = false
  }
}

async function loadTrend() {
  if (!current.value) return
  const days = [7, 30, 90][rangeTab.value]
  const t = await api.priceTrend(current.value.ingredient_id, days)
  chartSource.value = t.source
  await nextTick()
  chart ||= echarts.init(chartEl.value)
  chart.setOption({
    grid: { left: 40, right: 12, top: 20, bottom: 40 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: t.dates.map(d => d.slice(5)) },
    yAxis: { type: 'value', scale: true, name: '¥/500g' },
    dataZoom: [
      { type: 'inside', start: days > 30 ? 60 : 0, end: 100 },
      { type: 'slider', height: 16, bottom: 6 },
    ],
    series: [{
      type: 'line', data: t.prices, smooth: true, showSymbol: false,
      lineStyle: { color: '#07c160' },
      areaStyle: { color: 'rgba(7,193,96,0.12)' },
    }],
  })
}

function onPickConfirm(o) {
  const id = o.selectedOptions[0]?.value
  const p = prices.value.find(x => x.ingredient_id === id)
  if (p) select(p)
  showPicker.value = false
}

onMounted(async () => {
  prices.value = await api.latestPrices()
  if (prices.value.length) select(prices.value[0])
  window.addEventListener('resize', () => chart?.resize())
})
</script>

<style scoped>
.detail-panel {
  padding: 12px 16px 12px 48px;
  background: var(--van-gray-1, #f8f8f8);
  border-bottom: 1px solid var(--van-border-color, #ebedf0);
  font-size: 13px;
}
.detail-row {
  display: flex;
  justify-content: space-between;
  padding: 3px 0;
}
.detail-label {
  color: var(--van-gray-6, #969799);
}
</style>
