<template>
  <div class="page">
    <h2 style="margin:4px 0 12px">📦 库存
      <van-button size="small" type="primary" style="float:right" to="/purchase-in">+ 采购入库</van-button>
    </h2>

    <!-- 筛选 -->
    <van-dropdown-menu style="margin-bottom:10px;border-radius:10px;overflow:hidden">
      <van-dropdown-item v-model="fStatus" :options="statusOpts" @change="load" />
      <van-dropdown-item v-model="fStorage" :options="storageOpts" @change="load" />
    </van-dropdown-menu>

    <!-- 卡片式库存：一屏看完临期提醒 -->
    <div v-for="b in batches" :key="b.id" class="card" style="padding:12px">
      <div style="display:flex;justify-content:space-between;align-items:center">
        <div>
          <b style="font-size:15px">{{ b.icon }} {{ b.ingredient_name }}</b>
          <van-tag style="margin-left:6px"
            :type="b.status === '过期' ? 'danger' : b.status === '临期' ? 'warning' : 'success'">
            {{ b.status }}</van-tag>
        </div>
        <b>{{ b.remaining_qty }}{{ b.unit }}</b>
      </div>
      <div class="muted" style="margin:6px 0">
        {{ b.storage_method }}{{ b.location ? ' · ' + b.location : '' }}
        · {{ b.days_left < 0 ? `已过期 ${-b.days_left} 天` : `剩 ${b.days_left} 天（${b.expire_date}）` }}
        · 购于 {{ b.purchase_date }}
      </div>
      <div style="display:flex;gap:8px">
        <van-button size="mini" plain type="primary" @click="consumeDialog(b)">记录消耗</van-button>
        <van-button size="mini" plain @click="toShopping(b)">加入购物清单</van-button>
        <van-button size="mini" plain type="danger" @click="discard(b)">标记丢弃</van-button>
      </div>
    </div>
    <van-empty v-if="!batches.length" description="没有匹配的库存" />
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { showSuccessToast, showConfirmDialog, showDialog } from 'vant'
import api from '../api'
import { useAppStore } from '../stores/app'

const batches = ref([])
const fStatus = ref('')
const fStorage = ref('')
const statusOpts = [
  { text: '全部状态', value: '' }, { text: '🟢 新鲜', value: '新鲜' },
  { text: '🟡 临期', value: '临期' }, { text: '🔴 过期', value: '过期' }]
const storageOpts = [
  { text: '全部存放', value: '' }, { text: '常温', value: '常温' },
  { text: '冷藏', value: '冷藏' }, { text: '冷冻', value: '冷冻' }]

async function load() {
  batches.value = await api.inventory({
    status: fStatus.value || undefined, storage: fStorage.value || undefined })
  useAppStore().refreshBadges()
}

async function consumeDialog(b) {
  const qty = window.prompt(`消耗多少${b.unit}？（剩余 ${b.remaining_qty}${b.unit}）`, '100')
  if (!qty) return
  await api.consume({ batch_id: b.id, qty: +qty })
  showSuccessToast('已记录')
  load()
}

async function toShopping(b) {
  await api.toShopping(b.id)
  showSuccessToast('已加入购物清单')
  useAppStore().refreshBadges()
}

async function discard(b) {
  await showConfirmDialog({ title: '确认丢弃', message: `${b.ingredient_name} 剩余 ${b.remaining_qty}${b.unit} 将标记为丢弃` })
  await api.discard(b.id)
  showSuccessToast('已丢弃')
  load()
}

onMounted(load)
</script>
