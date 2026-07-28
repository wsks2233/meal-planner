<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">📅 菜谱计划</h2>
    <template v-if="plan">
      <div class="card" style="padding:10px 14px">
        <div style="display:flex;justify-content:space-between;align-items:center">
          <div>
            <b>{{ plan.mode === 'long_term' ? '长期计划' : '周计划' }}</b>
            <van-tag style="margin-left:6px" :type="plan.status === 'confirmed' ? 'success' : 'warning'">
              {{ plan.status === 'confirmed' ? '已确认' : '草稿' }}</van-tag>
          </div>
          <div><b>¥{{ plan.total_cost }}</b><span class="muted"> / ¥{{ plan.budget.toFixed(0) }}</span></div>
        </div>
        <van-button v-if="plan.status !== 'confirmed'" type="primary" size="small" block
          style="margin-top:8px" @click="confirm">✅ 确认计划（自动扣减库存、生成采购清单）</van-button>
      </div>

      <!-- 周切换：手机左右滑屏 -->
      <van-swipe :loop="false" :show-indicators="weeks.length > 1" :initial-swipe="0"
        @change="i => (weekIdx = i)" style="min-height:400px">
        <van-swipe-item v-for="(week, wi) in weeks" :key="wi">
          <div class="muted" style="text-align:center;margin:4px 0">
            ← 滑动切周 · 第 {{ wi + 1 }}/{{ weeks.length }} 周 →</div>
          <div v-for="day in week" :key="day.date" class="card" style="padding:10px">
            <div class="card-title" style="margin-bottom:6px">
              {{ fmtDate(day.date) }}
              <span class="muted">{{ weekdayName(day.date) }}</span>
            </div>
            <van-cell v-for="m in day.meals" :key="m.id" :border="false" style="padding:6px 0"
              @click="openMeal(m)">
              <template #title>
                <van-tag plain type="primary" style="margin-right:6px">{{ mealNames[m.meal_type] }}</van-tag>
                {{ m.recipe_name }}
                <span class="muted" v-if="m.cook_minutes"> · {{ m.cook_minutes }}min</span>
              </template>
              <template #value>
                <span class="muted">¥{{ m.est_cost }}</span>
                <van-icon name="exchange" style="margin-left:8px;color:#1989fa" />
              </template>
            </van-cell>
          </div>
        </van-swipe-item>
      </van-swipe>
    </template>

    <van-empty v-else description="还没有菜谱计划">
      <van-button type="primary" round to="/plan/generate">立即生成</van-button>
    </van-empty>

    <div style="display:flex;gap:8px;margin-top:8px" class="no-print">
      <van-button block plain type="primary" to="/plan/generate">🔄 重新生成</van-button>
      <van-button block plain to="/long-term">📦 长期采购模式</van-button>
      <van-button block plain to="/recipes">📖 食谱库</van-button>
    </div>

    <!-- 餐次详情/替换弹层 -->
    <van-popup v-model:show="showMeal" round position="bottom" style="max-height:75%">
      <div style="padding:16px" v-if="curMeal">
        <h3 style="margin:0 0 4px">{{ curMeal.recipe_name }}</h3>
        <div class="muted">{{ fmtDate(curMeal.date) }} {{ mealNames[curMeal.meal_type] }}
          · 预计 ¥{{ curMeal.est_cost }}</div>
        <van-button size="small" plain style="margin:10px 0"
          :to="`/recipes/${curMeal.recipe_id}`">查看食谱详情 →</van-button>
        <h4 style="margin:8px 0">🔁 替换建议（代价最小优先）</h4>
        <van-cell v-for="c in candidates" :key="c.recipe_id"
          :title="c.name" is-link
          :label="`新增采购 ¥${c.est_cost} · 食材相似度 ${(c.similarity * 100).toFixed(0)}% · ${c.cook_minutes}min`"
          @click="doReplace(c)" />
        <div v-if="!candidates.length" class="muted">加载中…</div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showSuccessToast, showConfirmDialog } from 'vant'
import api from '../api'

const plan = ref(null)
const weekIdx = ref(0)
const showMeal = ref(false)
const curMeal = ref(null)
const candidates = ref([])
const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }

const weeks = computed(() => {
  if (!plan.value) return []
  const byDate = {}
  for (const m of plan.value.meals) (byDate[m.date] ||= []).push(m)
  const days = Object.keys(byDate).sort().map(d => ({ date: d, meals: byDate[d] }))
  const out = []
  for (let i = 0; i < days.length; i += 7) out.push(days.slice(i, i + 7))
  return out
})

const fmtDate = d => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`
const weekdayName = d => '周' + '日一二三四五六'[new Date(d).getDay()]

async function load() {
  const plans = await api.plans()
  plan.value = plans[0] || null
}

async function openMeal(m) {
  curMeal.value = m
  candidates.value = []
  showMeal.value = true
  const res = await api.replaceCandidates(m.id)
  candidates.value = res.candidates
}

async function doReplace(c) {
  await api.updateMeal(curMeal.value.id, { recipe_id: c.recipe_id })
  showSuccessToast(`已替换为「${c.name}」`)
  showMeal.value = false
  load()
}

async function confirm() {
  await showConfirmDialog({
    title: '确认计划',
    message: '将按临期优先自动扣减库存，缺量食材写入采购清单。确认？',
  })
  const res = await api.confirmPlan(plan.value.id)
  showSuccessToast(res.message)
  load()
}

onMounted(load)
</script>
