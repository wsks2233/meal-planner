<template>
  <div class="page">
    <div class="card">
      <div class="card-title">📈 {{ current?.name || '选择食材' }} 价格走势
        <van-button size="mini" plain @click="showPicker = true">切换食材</van-button>
      </div>
      <van-tabs v-model:active="rangeTab" @change="loadTrend" shrink>
        <van-tab title="周" /><van-tab title="月" /><van-tab title="季" />
      </van-tabs>
      <!-- ECharts + dataZoom(inside)：手机横滑查看长周期 -->
      <div ref="chartEl" style="width:100%;height:260px;margin-top:8px"></div>
      <div class="muted">数据来源：{{ source }} · 图表支持双指缩放/横向滑动</div>
    </div>

    <div class="card">
      <div class="card-title">今日行情
        <van-search v-model="kw" placeholder="搜索食材" shape="round"
          style="flex:1;margin-left:8px;padding:0" />
      </div>
      <van-cell v-for="p in filtered" :key="p.ingredient_id"
        :title="`${p.icon} ${p.name}`" :label="`${p.category} · ${p.spec}`"
        clickable @click="select(p)">
        <template #value>
          <b>¥{{ p.price }}</b>
          <span :class="p.change_7d >= 0 ? 'up' : 'down'" style="font-size:12px;margin-left:6px">
            {{ p.change_7d >= 0 ? '↑' : '↓' }}{{ Math.abs(p.change_7d) }}%</span>
        </template>
      </van-cell>
    </div>

    <van-popup v-model:show="showPicker" round position="bottom">
      <van-picker :columns="prices.map(p => ({ text: p.icon + p.name, value: p.ingredient_id }))"
        @confirm="o => { select(prices.find(p => p.ingredient_id === o.selectedOptions[0].value)); showPicker = false }"
        @cancel="showPicker = false" />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import * as echarts from 'echarts'
import api from '../api'

const prices = ref([])
const current = ref(null)
const kw = ref('')
const rangeTab = ref(1)
const showPicker = ref(false)
const chartEl = ref(null)
const source = ref('模拟数据(演示)')
let chart = null

const filtered = computed(() =>
  prices.value.filter(p => !kw.value || p.name.includes(kw.value)))

function select(p) {
  current.value = p
  loadTrend()
}

async function loadTrend() {
  if (!current.value) return
  const days = [7, 30, 90][rangeTab.value]
  const t = await api.priceTrend(current.value.ingredient_id, days)
  source.value = t.source
  await nextTick()
  chart ||= echarts.init(chartEl.value)
  chart.setOption({
    grid: { left: 40, right: 12, top: 20, bottom: 40 },
    tooltip: { trigger: 'axis' },
    xAxis: { type: 'category', data: t.dates.map(d => d.slice(5)) },
    yAxis: { type: 'value', scale: true, name: '¥/500g' },
    // inside 模式支持手机手指横滑 + 双指缩放
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

onMounted(async () => {
  prices.value = await api.latestPrices()
  if (prices.value.length) select(prices.value[0])
  window.addEventListener('resize', () => chart?.resize())
})
</script>
