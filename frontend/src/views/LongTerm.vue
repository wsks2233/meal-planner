<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">🗓️ 长期采购模式</h2>
    <div class="card">
      <div class="card-title">📋 批量采购计划
        <span class="muted">按保质期分批 · 导出采购日历</span>
      </div>
      <van-cell title="起始日期">
        <template #value>
          <van-button size="mini" plain @click="dateShow = true">{{ form.start_date }}</van-button>
        </template>
      </van-cell>
      <van-cell title="计划天数">
        <template #value>
          <van-radio-group v-model="form.days" direction="horizontal">
            <van-radio :name="30">30天</van-radio>
            <van-radio :name="60">60天</van-radio>
            <van-radio :name="90">90天</van-radio>
          </van-radio-group>
        </template>
      </van-cell>
      <van-cell title="预算(元)" label="留空=家庭周预算折算">
        <template #value>
          <van-stepper v-model="form.budget" min="0" max="20000" step="50" integer />
        </template>
      </van-cell>
      <van-cell title="优先消耗库存">
        <template #value><van-switch v-model="form.use_inventory" /></template>
      </van-cell>
      <van-cell title="营养模板">
        <template #value>
          <van-dropdown-menu active-color="#07c160" style="width:150px">
            <van-dropdown-item v-model="form.template_id" :options="tplOpts" />
          </van-dropdown-menu>
        </template>
      </van-cell>
      <van-button block type="primary" :loading="loading" @click="generate">生成长期计划</van-button>
    </div>

    <!-- 结果 -->
    <div class="card" v-if="result?.feasible && result.plan">
      <div class="card-title">✅ 计划已生成</div>
      <van-row gutter="8" style="text-align:center">
        <van-col span="8"><b>{{ result.plan.days }}</b><div class="muted">天</div></van-col>
        <van-col span="8"><b>{{ result.plan.meals.length }}</b><div class="muted">餐次</div></van-col>
        <van-col span="8"><b>¥{{ result.plan.total_cost }}</b><div class="muted">预计花费</div></van-col>
      </van-row>
      <div class="muted" style="text-align:center;margin:8px 0">
        预算 ¥{{ result.plan.budget }} · 已按保质期分批采购
      </div>
      <van-button block type="success" :loading="confirming" @click="confirm">确认计划（扣库存+生成采购单）</van-button>
      <van-button block plain type="primary" style="margin-top:8px"
        :href="`/api/shopping/calendar.ics?plan_id=${result.plan.id}`">📅 导出采购日历(ICS)</van-button>
      <van-button block plain style="margin-top:8px" to="/plan">查看周计划 →</van-button>
    </div>

    <!-- 不可行提示 -->
    <van-popup v-model:show="infShow" round position="bottom" style="padding:16px">
      <div class="card-title">⚠️ 预算不足，建议</div>
      <p class="muted">{{ result?.message }}</p>
      <van-cell v-for="(s, i) in result?.suggestions || []" :key="i" :title="s" />
      <van-button block type="primary" @click="infShow = false">知道了</van-button>
    </van-popup>

    <van-calendar v-model:show="dateShow" @confirm="onDate" :min-date="minDate" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showSuccessToast, showToast } from 'vant'
import api from '../api'

const minDate = new Date()
const loading = ref(false)
const confirming = ref(false)
const infShow = ref(false)
const dateShow = ref(false)
const result = ref(null)
const templates = ref([])
const form = ref({
  start_date: new Date().toISOString().slice(0, 10),
  days: 30, budget: 0, use_inventory: true, template_id: null,
})
const tplOpts = computed(() => [
  { text: '默认(当前启用)', value: null },
  ...templates.value.map(t => ({ text: t.name, value: t.id })),
])

function onDate(d) {
  form.value.start_date = `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
  dateShow.value = false
}
async function generate() {
  loading.value = true
  result.value = null
  try {
    const res = await api.generatePlan({
      start_date: form.value.start_date,
      days: form.value.days,
      budget: form.value.budget > 0 ? form.value.budget : null,
      mode: 'long_term',
      use_inventory: form.value.use_inventory,
      template_id: form.value.template_id,
    })
    result.value = res
    if (!res.feasible) infShow.value = true
  } finally {
    loading.value = false
  }
}
async function confirm() {
  if (!result.value?.plan) return
  confirming.value = true
  try {
    await api.confirmPlan(result.value.plan.id)
    showSuccessToast('已确认，采购单已生成')
  } finally {
    confirming.value = false
  }
}
onMounted(async () => { templates.value = await api.templates() })
</script>
