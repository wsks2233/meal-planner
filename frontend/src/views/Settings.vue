<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">⚙️ 设置</h2>

    <!-- 家庭设置 -->
    <div class="card">
      <div class="card-title">👨‍👩‍👧 家庭设置</div>
      <van-cell title="家庭成员数">
        <template #value>
          <van-stepper v-model="family.people" min="1" max="12" integer />
        </template>
      </van-cell>
      <van-cell title="周预算（元）">
        <template #value>
          <van-stepper v-model="family.weekly_budget" min="50" max="5000" step="10" integer />
        </template>
      </van-cell>
      <van-cell title="每日 8:00 推送今日菜谱">
        <template #value>
          <van-switch v-model="family.notify_enabled" @change="saveFamily" />
        </template>
      </van-cell>
      <van-cell title="忌口 / 过敏食材" is-link @click="allergyShow = true"
        :label="allergyNames || '点击选择（推荐时自动避开）'" />
      <van-button block size="small" type="primary" @click="saveFamily">保存家庭设置</van-button>
    </div>

    <!-- 营养目标模板 -->
    <div class="card">
      <div class="card-title">🎯 营养目标模板
        <van-button size="mini" type="primary" plain @click="openTpl()">+ 新增</van-button>
      </div>
      <van-cell v-for="t in templates" :key="t.id" :title="t.name"
        :label="`${t.scope === 'daily' ? '每日' : '每周'} · 蛋白${t.protein_g}g 碳水${t.carb_g}g 脂肪${t.fat_g}g`">
        <template #value>
          <van-tag v-if="t.is_active" type="success">使用中</van-tag>
          <van-button size="mini" plain @click="openTpl(t)">编辑</van-button>
          <van-button size="mini" plain type="danger" @click="delTpl(t)">删</van-button>
        </template>
      </van-cell>
    </div>

    <!-- 每周餐次 -->
    <div class="card">
      <div class="card-title">📅 每周餐次开关
        <span class="muted">自由组合，如周末只吃两顿</span>
      </div>
      <van-cell v-for="(s, i) in schedule" :key="i" :title="weekdayNames[s.weekday]">
        <template #value>
          <van-tag plain :type="s.breakfast ? 'success' : 'default'">早</van-tag>
          <van-switch v-model="s.breakfast" size="16px" style="margin:0 8px" />
          <van-tag plain :type="s.lunch ? 'success' : 'default'">午</van-tag>
          <van-switch v-model="s.lunch" size="16px" style="margin:0 8px" />
          <van-tag plain :type="s.dinner ? 'success' : 'default'">晚</van-tag>
          <van-switch v-model="s.dinner" size="16px" />
        </template>
      </van-cell>
      <van-button block size="small" type="primary" @click="saveSchedule">保存餐次配置</van-button>
    </div>

    <!-- 忌口选择弹窗 -->
    <van-popup v-model:show="allergyShow" round position="bottom" style="height:70%">
      <div style="padding:14px">
        <div class="card-title">选择忌口 / 过敏食材</div>
        <van-checkbox-group v-model="family.allergies">
          <van-cell v-for="ing in ingredients" :key="ing.id" :title="`${ing.icon} ${ing.name}`" clickable
            @click="toggleAllergy(ing.id)">
            <template #right-icon>
              <van-checkbox :name="ing.id" @click.stop />
            </template>
          </van-cell>
        </van-checkbox-group>
        <van-button block type="primary" @click="allergyShow = false; saveFamily()">确定</van-button>
      </div>
    </van-popup>

    <!-- 模板编辑弹窗 -->
    <van-popup v-model:show="tplShow" round position="bottom" style="height:80%">
      <div style="padding:14px">
        <div class="card-title">{{ editing.id ? '编辑模板' : '新增模板' }}</div>
        <van-field v-model="editing.name" label="名称" placeholder="如：减脂期" />
        <van-cell title="周期">
          <template #value>
            <van-radio-group v-model="editing.scope" direction="horizontal">
              <van-radio name="daily">每日</van-radio>
              <van-radio name="weekly">每周</van-radio>
            </van-radio-group>
          </template>
        </van-cell>
        <van-field v-model="editing.protein_g" type="number" label="蛋白质(g)" />
        <van-field v-model="editing.carb_g" type="number" label="碳水(g)" />
        <van-field v-model="editing.fat_g" type="number" label="脂肪(g)" />
        <van-field v-model="editing.fiber_g" type="number" label="膳食纤维(g)" placeholder="可选" />
        <van-cell title="设为默认启用">
          <template #value><van-switch v-model="editing.is_active" /></template>
        </van-cell>
        <van-button block type="primary" @click="saveTpl">保存模板</van-button>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showToast, showSuccessToast } from 'vant'
import api from '../api'

const weekdayNames = ['周一', '周二', '周三', '周四', '周五', '周六', '周日']
const family = ref({ people: 3, weekly_budget: 500, allergies: [], notify_enabled: false })
const templates = ref([])
const schedule = ref([])
const ingredients = ref([])
const allergyShow = ref(false)
const tplShow = ref(false)
const editing = ref(blankTpl())

const allergyNames = computed(() => {
  const set = new Set(family.value.allergies || [])
  return ingredients.value.filter(i => set.has(i.id)).map(i => i.name).join('、')
})

function blankTpl() {
  return { id: null, name: '', scope: 'daily', protein_g: 65, carb_g: 250, fat_g: 60, fiber_g: null, is_active: false }
}
function toggleAllergy(id) {
  const arr = family.value.allergies || []
  const i = arr.indexOf(id)
  if (i >= 0) arr.splice(i, 1); else arr.push(id)
}

async function load() {
  const [f, t, s, ings] = await Promise.all([
    api.family(), api.templates(), api.schedule(), api.ingredients(),
  ])
  family.value = f
  templates.value = t
  schedule.value = s
  ingredients.value = ings
}
async function saveFamily() {
  await api.updateFamily({
    people: family.value.people,
    weekly_budget: family.value.weekly_budget,
    allergies: family.value.allergies || [],
    notify_enabled: family.value.notify_enabled,
  })
  showSuccessToast('已保存')
}
async function saveSchedule() {
  await api.updateSchedule(schedule.value.map(s => ({
    weekday: s.weekday, breakfast: s.breakfast, lunch: s.lunch, dinner: s.dinner,
  })))
  showSuccessToast('已保存')
}
function openTpl(t) {
  editing.value = t ? { ...t } : blankTpl()
  tplShow.value = true
}
async function saveTpl() {
  const d = { ...editing.value, protein_g: +editing.value.protein_g || 0,
    carb_g: +editing.value.carb_g || 0, fat_g: +editing.value.fat_g || 0,
    fiber_g: editing.value.fiber_g ? +editing.value.fiber_g : null }
  if (editing.value.id) await api.updateTemplate(editing.value.id, d)
  else await api.createTemplate(d)
  tplShow.value = false
  templates.value = await api.templates()
  showSuccessToast('已保存')
}
async function delTpl(t) {
  await api.deleteTemplate(t.id)
  templates.value = await api.templates()
}

onMounted(load)
</script>
