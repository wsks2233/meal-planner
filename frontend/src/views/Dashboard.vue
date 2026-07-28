<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">🏠 膳食管家</h2>

    <!-- 预算使用 -->
    <div class="card">
      <div class="card-title">💰 预算使用
        <span class="muted" v-if="d?.budget">{{ d.budget.mode === 'long_term' ? '长期计划' : '周计划' }}</span>
      </div>
      <template v-if="d?.budget">
        <van-progress :percentage="Math.min(d.budget.usage_pct, 100)"
          :pivot-text="`¥${d.budget.total_cost}`"
          :color="d.budget.usage_pct > 95 ? '#ee0a24' : '#07c160'" stroke-width="10" />
        <div class="muted" style="margin-top:8px">
          预算 ¥{{ d.budget.budget.toFixed(0) }} ·
          已发生 ¥{{ d.budget.spent_so_far }} ·
          {{ d.budget.status === 'confirmed' ? '已确认' : '草稿' }}
        </div>
      </template>
      <van-button v-else block size="small" type="primary" to="/plan/generate">
        还没有菜谱计划，去生成 →</van-button>
    </div>

    <!-- 营养达标率 -->
    <div class="card" v-if="d?.nutrition_rate">
      <div class="card-title">🥗 近7天营养达标率
        <span class="muted" v-if="d.adherence !== null">依从度 {{ d.adherence }}%</span>
      </div>
      <van-row gutter="8">
        <van-col span="8" v-for="(v, k) in d.nutrition_rate" :key="k" style="text-align:center">
          <van-circle :current-rate="Math.min(v, 100)" :rate="Math.min(v, 100)"
            :speed="60" size="64px" :stroke-width="70"
            :color="v >= 85 && v <= 130 ? '#07c160' : '#ff976a'"
            :text="v + '%'" />
          <div class="muted" style="margin-top:4px">{{ labels[k] }}</div>
        </van-col>
      </van-row>
    </div>

    <!-- 临期提醒 -->
    <div class="card">
      <div class="card-title">⏰ 即将过期
        <van-badge v-if="d?.expiring_count" :content="d.expiring_count" />
      </div>
      <template v-if="d?.expiring?.length">
        <van-cell v-for="e in d.expiring" :key="e.batch_id"
          :title="`${e.icon} ${e.name}`"
          :label="`剩 ${e.remaining_qty}${e.unit}${e.location ? ' · ' + e.location : ''}`">
          <template #value>
            <span :style="{ color: e.days_left <= 1 ? '#ee0a24' : '#ff976a' }">
              {{ e.days_left <= 0 ? '今天到期' : e.days_left + ' 天后过期' }}</span>
          </template>
        </van-cell>
        <van-button block size="small" plain type="danger" to="/inventory"
          style="margin-top:8px">去处理 →</van-button>
      </template>
      <div v-else class="muted">暂无临期食材 🎉</div>
    </div>

    <!-- 今日菜谱 -->
    <div class="card">
      <div class="card-title">🍳 今日菜谱
        <van-button size="mini" plain @click="askNotify">开启每日8点提醒</van-button>
      </div>
      <template v-if="today.length">
        <van-cell v-for="m in today" :key="m.meal_type"
          :title="`${mealNames[m.meal_type]} · ${m.recipe}`"
          :label="m.ingredients.map(i => `${i.name}${i.amount}${i.unit}`).join(' / ')">
          <template #value>
            <van-tag :type="m.done_status === 'done' ? 'success' : 'default'"
              @click="markDone(m)">
              {{ m.done_status === 'done' ? '已完成' : '标记完成' }}</van-tag>
          </template>
        </van-cell>
      </template>
      <div v-else class="muted">今天没有安排，去「菜谱」生成吧</div>
    </div>

    <!-- 菜价波动 -->
    <div class="card">
      <div class="card-title">📈 菜价异动（近7天）
        <router-link to="/prices" class="muted">全部行情 →</router-link>
      </div>
      <van-row gutter="8">
        <van-col span="12" v-for="p in d?.price_movers || []" :key="p.ingredient_id">
          <div style="border:1px solid #f2f3f5;border-radius:8px;padding:8px;margin-bottom:8px">
            <div style="font-size:13px">{{ p.icon }} {{ p.name }}</div>
            <div style="display:flex;justify-content:space-between;align-items:center">
              <b>¥{{ p.price }}</b>
              <span :class="p.change >= 0 ? 'up' : 'down'" style="font-size:12px">
                {{ p.change >= 0 ? '↑' : '↓' }}{{ Math.abs(p.change) }}%</span>
            </div>
            <svg :viewBox="`0 0 100 24`" style="width:100%;height:24px">
              <polyline :points="spark(p.spark)" fill="none"
                :stroke="p.change >= 0 ? '#ee0a24' : '#07c160'" stroke-width="1.5" />
            </svg>
          </div>
        </van-col>
      </van-row>
      <div class="muted">数据来源：模拟数据(演示)</div>
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showToast } from 'vant'
import api from '../api'
import { useAppStore } from '../stores/app'

const store = useAppStore()
const d = ref(null)
const today = ref([])
const labels = { protein: '蛋白质', carb: '碳水', fat: '脂肪' }
const mealNames = { breakfast: '早餐', lunch: '午餐', dinner: '晚餐' }

function spark(arr) {
  if (!arr?.length) return ''
  const min = Math.min(...arr), max = Math.max(...arr), r = max - min || 1
  return arr.map((v, i) =>
    `${(i / (arr.length - 1)) * 100},${22 - ((v - min) / r) * 20}`).join(' ')
}

async function load() {
  d.value = await api.dashboard()
  today.value = await api.todayMeals()
  store.refreshBadges()
}

async function markDone(m) {
  await api.updateMeal(m.plan_meal_id, { done_status: m.done_status === 'done' ? 'pending' : 'done' })
  load()
}

async function askNotify() {
  if (!('Notification' in window)) return showToast('当前浏览器不支持通知')
  const perm = await Notification.requestPermission()
  showToast(perm === 'granted' ? '已开启：每日8点推送今日菜谱' : '未授权，可随时在这里手动查看')
}

onMounted(load)
</script>
