<template>
  <div class="page">
    <!-- 模拟扫码：输入条形码即可带出食材（真实场景可接摄像头扫码库如 html5-qrcode） -->
    <div class="card">
      <div class="card-title">📷 扫码/条码添加</div>
      <van-field v-model="barcode" placeholder="输入条形码（演示码 69100000000 起）" clearable>
        <template #button>
          <van-button size="small" type="primary" @click="scan">识别</van-button>
        </template>
      </van-field>
      <div class="muted">演示环境用手动输码模拟扫码；每个内置食材都有条码，可在食材列表查看。</div>
    </div>

    <div class="card">
      <div class="card-title">✍️ 采购明细</div>
      <van-form @submit="submit">
        <van-field :model-value="ingName" label="食材" readonly is-link required
          placeholder="点击选择" @click="showPicker = true" />
        <van-field v-model.number="form.qty" label="数量" type="number" required
          :placeholder="`单位：${ing?.unit || 'g'}`" />
        <van-field v-model.number="form.unit_price" label="单价" type="number"
          placeholder="元/500g，可留空" />
        <van-field v-model="form.purchase_date" label="购买日期" type="date" required />
        <van-field v-model="form.expire_date" label="保质期至" type="date"
          :placeholder="ing ? `留空按默认 ${ing.default_shelf_life_days} 天` : '留空自动计算'" />
        <van-field label="保存方式">
          <template #input>
            <van-radio-group v-model="form.storage_method" direction="horizontal">
              <van-radio name="常温">常温</van-radio>
              <van-radio name="冷藏">冷藏</van-radio>
              <van-radio name="冷冻">冷冻</van-radio>
            </van-radio-group>
          </template>
        </van-field>
        <van-field v-model="form.location" label="存放位置" placeholder="如：冷冻第二层" />
        <div style="margin:16px 0">
          <van-button round block type="primary" native-type="submit">入库</van-button>
        </div>
      </van-form>
    </div>

    <van-popup v-model:show="showPicker" round position="bottom">
      <van-picker :columns="columns" @confirm="pick" @cancel="showPicker = false" />
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { showSuccessToast } from 'vant'
import { useRouter } from 'vue-router'
import api from '../api'

const router = useRouter()
const ingredients = ref([])
const barcode = ref('')
const showPicker = ref(false)
const ing = ref(null)
const form = ref({
  qty: null, unit_price: null,
  purchase_date: new Date().toISOString().slice(0, 10),
  expire_date: '', storage_method: '冷藏', location: '',
})

const ingName = computed(() => (ing.value ? `${ing.value.icon} ${ing.value.name}` : ''))
const columns = computed(() => ingredients.value.map(i =>
  ({ text: `${i.icon} ${i.name}（${i.category}）`, value: i.id })))

function pick({ selectedOptions }) {
  setIng(ingredients.value.find(i => i.id === selectedOptions[0].value))
  showPicker.value = false
}

function setIng(i) {
  ing.value = i
  form.value.storage_method = i.storage_method
}

async function scan() {
  const found = await api.byBarcode(barcode.value.trim())
  setIng(found)
  showSuccessToast(`已识别：${found.name}`)
}

async function submit() {
  const payload = { ...form.value, ingredient_id: ing.value.id, unit: ing.value.unit }
  if (!payload.expire_date) delete payload.expire_date
  if (!payload.unit_price) payload.unit_price = 0
  await api.purchaseIn(payload)
  showSuccessToast('入库成功')
  router.replace('/inventory')
}

onMounted(async () => { ingredients.value = await api.ingredients() })
</script>
