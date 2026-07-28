<template>
  <div class="page">
    <h2 style="margin:4px 0 12px" class="no-print">🛒 采购清单</h2>

    <div class="card no-print" style="display:flex;gap:8px;padding:10px">
      <van-button size="small" plain type="primary" @click="merge">未购项合并到下次</van-button>
      <van-button size="small" plain @click="printList">🖨️ 打印/存PDF</van-button>
      <van-button size="small" plain tag="a" href="/api/shopping/calendar.ics">📅 采购日历</van-button>
    </div>

    <!-- 按建议购买日分组（长期模式分批展示） -->
    <div v-for="g in groups" :key="g.date" class="card">
      <div class="card-title">
        {{ g.date === 'none' ? '待采购' : '📆 ' + g.date }}
        <span class="muted">{{ g.items.length }} 项 · 约 ¥{{ g.total.toFixed(1) }}</span>
      </div>
      <van-checkbox-group v-model="checked">
        <van-cell v-for="it in g.items" :key="it.id" clickable @click="toggle(it)">
          <template #title>
            <span :style="it.bought ? 'text-decoration:line-through;color:#c8c9cc' : ''">
              {{ it.icon }} {{ it.ingredient_name }}
              <van-tag v-if="it.batch_no > 1" plain size="mini">第{{ it.batch_no }}批</van-tag>
            </span>
          </template>
          <template #label>
            {{ it.need_qty }}{{ it.unit }} · {{ it.storage_method }} · 约 ¥{{ it.est_price }}
          </template>
          <template #right-icon>
            <van-checkbox :name="it.id" @click.stop="toggle(it)" />
          </template>
        </van-cell>
      </van-checkbox-group>
    </div>
    <van-empty v-if="!items.length" description="清单是空的，确认菜谱计划后自动生成" />
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showSuccessToast } from 'vant'
import api from '../api'
import { useAppStore } from '../stores/app'

const items = ref([])
const checked = ref([])

const groups = computed(() => {
  const by = {}
  for (const it of items.value) {
    const k = it.suggest_date || 'none'
    ;(by[k] ||= []).push(it)
  }
  return Object.keys(by).sort().map(k => ({
    date: k, items: by[k],
    total: by[k].reduce((s, x) => s + (x.bought ? 0 : x.est_price), 0),
  }))
})

async function load() {
  items.value = await api.shopping()
  checked.value = items.value.filter(i => i.bought).map(i => i.id)
}

async function toggle(it) {
  await api.markBought({ item_ids: [it.id], bought: !it.bought })
  load()
  useAppStore().refreshBadges()
}

async function merge() {
  const res = await api.mergePending()
  showSuccessToast(`已合并 ${res.merged} 种食材`)
  load()
}

function printList() { window.print() }

onMounted(load)
</script>
