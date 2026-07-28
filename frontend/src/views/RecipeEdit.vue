<template>
  <div class="page">
    <div class="card">
      <div class="card-title">🍳 新建食谱</div>
      <van-field v-model="form.name" label="菜名" placeholder="如：番茄炒蛋" />
      <van-cell title="分类">
        <template #value>
          <van-dropdown-menu active-color="#07c160" style="width:140px">
            <van-dropdown-item v-model="form.category" :options="catOpts" />
          </van-dropdown-menu>
        </template>
      </van-cell>
      <van-cell title="适用餐次">
        <template #value>
          <van-checkbox-group v-model="form.meal_types" direction="horizontal">
            <van-checkbox name="breakfast">早</van-checkbox>
            <van-checkbox name="lunch">午</van-checkbox>
            <van-checkbox name="dinner">晚</van-checkbox>
          </van-checkbox-group>
        </template>
      </van-cell>
      <van-cell title="烹饪时长(分钟)">
        <template #value><van-stepper v-model="form.cook_minutes" min="5" max="240" step="5" integer /></template>
      </van-cell>
    </div>

    <div class="card">
      <div class="card-title">🥗 营养（单人份）</div>
      <van-row gutter="8">
        <van-col span="12"><van-field v-model="form.kcal" type="number" label="千卡" /></van-col>
        <van-col span="12"><van-field v-model="form.protein_g" type="number" label="蛋白质g" /></van-col>
        <van-col span="12"><van-field v-model="form.carb_g" type="number" label="碳水g" /></van-col>
        <van-col span="12"><van-field v-model="form.fat_g" type="number" label="脂肪g" /></van-col>
      </van-row>
    </div>

    <div class="card">
      <div class="card-title">🧺 食材
        <van-button size="mini" type="primary" plain @click="pickShow = true">+ 添加</van-button>
      </div>
      <van-cell v-for="(it, i) in form.items" :key="i"
        :title="`${it.icon} ${it.name}`"
        :value="`${it.amount}${it.unit}`">
        <template #right-icon>
          <van-button size="mini" plain type="danger" @click="form.items.splice(i, 1)">删</van-button>
        </template>
      </van-cell>
      <div v-if="!form.items.length" class="muted">还没添加食材</div>
    </div>

    <div class="card">
      <div class="card-title">👨‍🍳 步骤
        <van-button size="mini" type="primary" plain @click="form.steps.push('')">+ 步骤</van-button>
      </div>
      <div v-for="(s, i) in form.steps" :key="i" style="display:flex;gap:8px;align-items:center;margin-bottom:8px">
        <van-field v-model="form.steps[i]" :label="`${i + 1}.`" placeholder="如：鸡蛋打散加少许盐" style="flex:1" />
        <van-button size="mini" plain type="danger" @click="form.steps.splice(i, 1)">删</van-button>
      </div>
    </div>

    <div class="card">
      <van-field v-model="form.note" label="备注" type="textarea" placeholder="可选，如：少油版" rows="2" />
    </div>

    <van-button block type="primary" @click="submit">保存食谱</van-button>

    <!-- 食材选择弹窗 -->
    <van-popup v-model:show="pickShow" round position="bottom" style="height:75%">
      <div style="padding:14px">
        <div class="card-title">选择食材（单人份用量）</div>
        <van-search v-model="kw" placeholder="搜索食材" />
        <div style="max-height:60vh;overflow:auto">
          <van-cell v-for="ing in filtered" :key="ing.id" :title="`${ing.icon} ${ing.name}`"
            :label="`${ing.category} · 参考价¥${ing.base_price}/${ing.unit}`" is-link
            @click="addItem(ing)" />
        </div>
      </div>
    </van-popup>
  </div>
</template>

<script setup>
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { showToast, showSuccessToast } from 'vant'
import api from '../api'

const router = useRouter()
const catOpts = [
  { text: '主菜', value: '主菜' }, { text: '汤羹', value: '汤羹' },
  { text: '凉菜', value: '凉菜' }, { text: '主食', value: '主食' },
  { text: '早餐', value: '早餐' }, { text: '甜点', value: '甜点' },
]
const ingredients = ref([])
const kw = ref('')
const pickShow = ref(false)
const form = ref({
  name: '', category: '主菜', meal_types: ['lunch', 'dinner'],
  cook_minutes: 30, kcal: 0, protein_g: 0, carb_g: 0, fat_g: 0,
  items: [], steps: [''], note: '', tags: [],
})
const filtered = computed(() =>
  ingredients.value.filter(i => !kw.value || i.name.includes(kw.value)))

function addItem(ing) {
  if (form.value.items.some(it => it.ingredient_id === ing.id)) {
    return showToast('已添加')
  }
  form.value.items.push({ ingredient_id: ing.id, name: ing.name, icon: ing.icon,
    amount: 100, unit: ing.unit })
  pickShow.value = false
}
async function submit() {
  if (!form.value.name.trim()) return showToast('请填写菜名')
  if (!form.value.items.length) return showToast('至少添加一种食材')
  const payload = {
    name: form.value.name.trim(),
    category: form.value.category,
    meal_types: form.value.meal_types.length ? form.value.meal_types : ['lunch', 'dinner'],
    cook_minutes: form.value.cook_minutes,
    kcal: +form.value.kcal || 0,
    protein_g: +form.value.protein_g || 0,
    carb_g: +form.value.carb_g || 0,
    fat_g: +form.value.fat_g || 0,
    note: form.value.note || null,
    steps: form.value.steps.map(s => s.trim()).filter(Boolean),
    items: form.value.items.map(it => ({
      ingredient_id: it.ingredient_id, amount: +it.amount || 0, unit: it.unit,
    })),
  }
  const r = await api.createRecipe(payload)
  showSuccessToast('已保存')
  router.replace(`/recipes/${r.id}`)
}
onMounted(async () => { ingredients.value = await api.ingredients() })
</script>
