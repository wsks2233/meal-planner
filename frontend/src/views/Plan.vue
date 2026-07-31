<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">📅 菜谱计划</h2>

    <!-- 备菜提示栏 -->
    <div v-if="prepReminders.length" class="prep-bar">
      <div class="prep-bar-title">🔔 备菜提醒 · 未来 3 天需提前准备</div>
      <div v-for="r in prepReminders" :key="r.key" class="prep-row" :class="{ done: r.done }"
        @click="togglePrep(r.key)">
        <span class="ck">{{ r.done ? '✓' : '○' }}</span>
        <span class="txt">{{ r.text }}</span>
      </div>
    </div>
    <div v-if="breakfastHints.length" class="prep-bar soft">
      <div class="prep-bar-title">🍳 可提前备的早餐（前一晚备好更从容）</div>
      <div v-for="b in breakfastHints" :key="b.key" class="prep-row soft">
        <span class="ck">💡</span><span class="txt">{{ b.text }}</span>
      </div>
    </div>

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
            <div v-for="(dishes, type) in day.byMeal" :key="type">
              <van-tag plain type="primary" size="small" style="margin-bottom:4px">{{ mealNames[type] }}
                <span v-if="type !== 'breakfast'" class="muted">（{{ dishes.length }} 道菜 · 含主食）</span>
              </van-tag>
              <van-cell v-for="m in dishes" :key="m.id" :border="false" style="padding:4px 0 4px 16px"
                @click="openMeal(m)">
                <template #title>
                  <span class="muted" v-if="m.cook_minutes">{{ m.cook_minutes }}min </span>
                  {{ m.recipe_name }}
                  <van-tag v-if="m.prep_ahead_hours > 0" size="mini" type="warning" style="margin-left:4px">
                    需备{{ m.prep_ahead_hours }}h</van-tag>
                </template>
                <template #value>
                  <span class="muted">¥{{ m.est_cost }}</span>
                  <van-icon name="exchange" style="margin-left:8px;color:#1989fa" />
                </template>
              </van-cell>
            </div>
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
    <van-popup v-model:show="showMeal" round position="bottom" style="max-height:85%">
      <div style="padding:16px" v-if="curMeal">
        <h3 style="margin:0 0 4px">{{ curMeal.recipe_name }}</h3>
        <div class="muted">{{ fmtDate(curMeal.date) }} {{ mealNames[curMeal.meal_type] }}
          · 预计 ¥{{ curMeal.est_cost }}
          · {{ curRecipe?.cook_minutes || curMeal.cook_minutes }}min
          <template v-if="curRecipe?.kcal"> · {{ curRecipe.kcal }}kcal</template>
        </div>

        <div v-if="curMeal.prep_ahead_hours > 0" class="prep-chip">
          🔔 需提前 {{ curMeal.prep_ahead_hours }} 小时备菜（如腌制 / 泡发 / 过夜冷藏）
        </div>

        <!-- 做法 -->
        <van-divider>🍳 做法（{{ (curRecipe?.steps || []).length }} 步）</van-divider>
        <ol class="steps" v-if="(curRecipe?.steps || []).length">
          <li v-for="(s, i) in curRecipe.steps" :key="i">{{ s }}</li>
        </ol>
        <div v-else class="muted">该食谱暂无步骤文本。</div>

        <!-- 食材 -->
        <van-divider>🧺 食材（{{ (curRecipe?.items || []).length }} 种 · 单人份）</van-divider>
        <div class="ings" v-if="(curRecipe?.items || []).length">
          <van-tag v-for="it in curRecipe.items" :key="it.ingredient_id" plain type="primary" style="margin:2px">
            {{ it.ingredient_name }} {{ it.amount }}{{ it.unit }}
          </van-tag>
        </div>

        <van-button size="small" plain style="margin:12px 0" :to="`/recipes/${curMeal.recipe_id}`">
          查看完整食谱页 →</van-button>

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
import { ref, computed, reactive, onMounted } from 'vue'
import { showSuccessToast, showConfirmDialog } from 'vant'
import api from '../api'

const plan = ref(null)
const weekIdx = ref(0)
const showMeal = ref(false)
const curMeal = ref(null)
const curRecipe = ref(null)
const candidates = ref([])
const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }

// 备菜「已备」状态：存 localStorage（设备本地记忆，跨刷新保留）
const prepDone = reactive({})
function loadPrepDone() {
  try {
    const raw = localStorage.getItem('mealplanner_prep_done')
    if (raw) Object.assign(prepDone, JSON.parse(raw))
  } catch (e) { /* ignore */ }
}
function persistPrep() {
  localStorage.setItem('mealplanner_prep_done', JSON.stringify(prepDone))
}
function togglePrep(key) {
  prepDone[key] = !prepDone[key]
  persistPrep()
}

// 各餐次假定开餐时间，用于推算「需提前几小时开始备菜」
const MEAL_TIME = { breakfast: '07:30', lunch: '12:00', dinner: '18:30' }

const weeks = computed(() => {
  if (!plan.value) return []
  const byDate = {}
  for (const m of plan.value.meals) {
    const day = (byDate[m.date] ||= { date: m.date, meals: [], byMeal: { breakfast: [], lunch: [], dinner: [] } })
    day.meals.push(m)
    ;(day.byMeal[m.meal_type] ||= []).push(m)
  }
  const days = Object.keys(byDate).sort().map(d => byDate[d])
  const out = []
  for (let i = 0; i < days.length; i += 7) out.push(days.slice(i, i + 7))
  return out
})

// 备菜提醒：未来 3 天内、需提前备菜（prep_ahead_hours>0）的餐次
const prepReminders = computed(() => {
  if (!plan.value) return []
  const now = new Date()
  const out = []
  for (const m of plan.value.meals) {
    const h = m.prep_ahead_hours
    if (!h || h <= 0) continue
    const [Y, Mo, D] = m.date.split('-').map(Number)
    const [hh, mm] = MEAL_TIME[m.meal_type].split(':').map(Number)
    const mealDt = new Date(Y, Mo - 1, D, hh, mm)
    const startDt = new Date(mealDt.getTime() - h * 3600 * 1000)
    const daysAhead = (startDt - now) / (24 * 3600 * 1000)
    if (daysAhead > 3) continue            // 超出操作窗口不提示
    const key = `${plan.value.id}_${m.id}`
    out.push({
      key,
      startDt,
      text: `${fmtDate(m.date)} ${mealNames[m.meal_type]}《${m.recipe_name}》需提前 ${h} 小时备菜` +
            `（如腌制/泡发），建议 ${fmtDateTime(startDt)} 前开始`,
      done: !!prepDone[key],
    })
  }
  out.sort((a, b) => a.startDt - b.startDt)
  return out
})

// 可提前备的早餐：下一晚备好更从容（软提示，无强制）
const breakfastHints = computed(() => {
  if (!plan.value) return []
  const now = new Date()
  const seen = new Set()
  const out = []
  for (const m of plan.value.meals) {
    if (m.meal_type !== 'breakfast') continue
    const [Y, Mo, D] = m.date.split('-').map(Number)
    const dt = new Date(Y, Mo - 1, D)
    const daysAhead = (dt - now) / (24 * 3600 * 1000)
    if (daysAhead < -0.5 || daysAhead > 3) continue
    const key = m.date + '_bk'
    if (seen.has(key)) continue
    seen.add(key)
    out.push({ key, text: `${fmtDate(m.date)} 早餐《${m.recipe_name}》可前一晚备好（隔夜燕麦/和面等）` })
  }
  return out
})

const fmtDate = d => `${+d.slice(5, 7)}月${+d.slice(8, 10)}日`
const weekdayName = d => '周' + '日一二三四五六'[new Date(d).getDay()]
const fmtDateTime = dt =>
  `${dt.getMonth() + 1}月${dt.getDate()}日 ${String(dt.getHours()).padStart(2, '0')}:${String(dt.getMinutes()).padStart(2, '0')}`

async function load() {
  const plans = await api.plans()
  plan.value = plans[0] || null
}

async function openMeal(m) {
  curMeal.value = m
  candidates.value = []
  curRecipe.value = null
  showMeal.value = true
  // 并行取替换建议 + 食谱详情（步骤/食材）
  const [cands, rec] = await Promise.all([
    api.replaceCandidates(m.id),
    api.recipe(m.recipe_id),
  ])
  candidates.value = cands.candidates
  curRecipe.value = rec
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

onMounted(() => {
  loadPrepDone()
  load()
})
</script>

<style scoped>
.prep-bar {
  background: #fff7e6;
  border: 1px solid #ffd591;
  border-radius: 10px;
  padding: 8px 12px;
  margin-bottom: 10px;
}
.prep-bar.soft {
  background: #f6ffed;
  border-color: #b7eb8f;
}
.prep-bar-title {
  font-weight: 600;
  font-size: 13px;
  margin-bottom: 4px;
  color: #ad6800;
}
.prep-bar.soft .prep-bar-title {
  color: #389e0d;
}
.prep-row {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  font-size: 13px;
  line-height: 1.5;
  padding: 2px 0;
  cursor: pointer;
}
.prep-row .ck {
  flex: 0 0 auto;
  font-weight: 700;
  color: #fa8c16;
}
.prep-row.soft .ck {
  color: #52c41a;
}
.prep-row.done .txt {
  text-decoration: line-through;
  color: #bbb;
}
.steps {
  margin: 0;
  padding-left: 18px;
  font-size: 13px;
  line-height: 1.7;
}
.ings {
  display: flex;
  flex-wrap: wrap;
}
.prep-chip {
  margin: 8px 0;
  background: #fff1f0;
  border: 1px solid #ffccc7;
  color: #cf1322;
  border-radius: 8px;
  padding: 6px 10px;
  font-size: 13px;
}
</style>
