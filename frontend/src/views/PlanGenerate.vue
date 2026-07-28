<template>
  <div class="page">
    <div class="card">
      <van-form @submit="generate">
        <van-cell-group inset style="margin:0">
          <van-field v-model="form.start_date" label="开始日期" type="date" required />
          <van-field v-model.number="form.days" label="天数" type="digit"
            placeholder="7=周计划，30/60=长期" />
          <van-field v-model.number="form.budget" label="预算(¥)" type="number"
            :placeholder="`默认按家庭周预算折算`" />
          <van-cell title="优先使用库存" center>
            <template #right-icon><van-switch v-model="form.use_inventory" size="20" /></template>
          </van-cell>
          <van-field label="营养模板" readonly is-link
            :model-value="tplName" @click="showTpl = true" />
        </van-cell-group>
        <div style="margin:16px 0">
          <van-button round block type="primary" native-type="submit" :loading="loading">
            🤖 智能生成菜谱</van-button>
        </div>
      </van-form>
      <div class="muted">餐次组合与忌口请在「设置」中配置；天数 > 7 自动进入长期模式（每周主菜轮换 ≥ 70%）。</div>
    </div>

    <!-- 预算不可行提示 -->
    <div class="card" v-if="failMsg" style="border:1px solid #ffd21e">
      <div class="card-title" style="color:#ed6a0c">⚠️ {{ failMsg }}</div>
      <van-cell v-for="(s, i) in suggestions" :key="i" :title="s" is-link
        @click="applySuggestion(i)" />
    </div>

    <van-popup v-model:show="showTpl" round position="bottom">
      <van-picker :columns="tplColumns" @confirm="pickTpl" @cancel="showTpl = false" />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showSuccessToast } from 'vant'
import api from '../api'

const router = useRouter()
const loading = ref(false)
const showTpl = ref(false)
const templates = ref([])
const failMsg = ref('')
const suggestions = ref([])
const form = ref({
  start_date: new Date().toISOString().slice(0, 10),
  days: 7, budget: null, use_inventory: true, template_id: null,
})

const tplName = computed(() =>
  templates.value.find(t => t.id === form.value.template_id)?.name
  || templates.value.find(t => t.is_active)?.name || '默认')
const tplColumns = computed(() =>
  templates.value.map(t => ({ text: `${t.name} (蛋白${t.protein_g}g/碳水${t.carb_g}g/脂肪${t.fat_g}g)`, value: t.id })))

function pickTpl({ selectedOptions }) {
  form.value.template_id = selectedOptions[0]?.value
  showTpl.value = false
}

async function generate() {
  loading.value = true
  failMsg.value = ''
  try {
    const payload = { ...form.value, mode: form.value.days > 7 ? 'long_term' : 'week' }
    if (!payload.budget) delete payload.budget
    const res = await api.generatePlan(payload)
    if (!res.feasible) {
      failMsg.value = res.message
      suggestions.value = res.suggestions
      return
    }
    showSuccessToast('生成成功！')
    router.replace('/plan')
  } finally { loading.value = false }
}

function applySuggestion(i) {
  if (i === 0 && form.value.budget) form.value.budget = Math.round(form.value.budget * 1.1)
  else router.push('/settings')
}

onMounted(async () => { templates.value = await api.templates() })
</script>
