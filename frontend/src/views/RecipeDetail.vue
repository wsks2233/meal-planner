<template>
  <div class="page" v-if="r">
    <div class="card" style="padding:0;overflow:hidden">
      <div style="height:140px;background:#e8f7ef;display:flex;align-items:center;justify-content:center;font-size:56px">
        <img v-if="r.image_url && !r.image_url.startsWith('/placeholder')"
          :src="r.image_url" style="width:100%;height:100%;object-fit:cover" />
        <span v-else>🍽️</span>
      </div>
      <div style="padding:14px">
        <h2 style="margin:0">{{ r.name }}</h2>
        <div class="muted" style="margin:6px 0">
          {{ r.category }} · ⏱ {{ r.cook_minutes }} 分钟
          <van-tag v-if="r.cook_minutes > 45" type="warning" plain>周末大菜</van-tag>
          <van-tag v-if="!r.is_builtin" type="primary" plain>自定义</van-tag>
        </div>
        <van-row style="text-align:center;margin:10px 0">
          <van-col span="6"><b>{{ r.kcal }}</b><div class="muted">千卡</div></van-col>
          <van-col span="6"><b>{{ r.protein_g }}g</b><div class="muted">蛋白质</div></van-col>
          <van-col span="6"><b>{{ r.carb_g }}g</b><div class="muted">碳水</div></van-col>
          <van-col span="6"><b>{{ r.fat_g }}g</b><div class="muted">脂肪</div></van-col>
        </van-row>
        <div v-if="r.note" class="muted">备注：{{ r.note }}</div>
      </div>
    </div>

    <div class="card">
      <div class="card-title">🧺 食材（单人份）</div>
      <van-cell v-for="it in r.items" :key="it.ingredient_id"
        :title="`${it.icon} ${it.ingredient_name}`" :value="`${it.amount}${it.unit}`" />
    </div>

    <div class="card">
      <div class="card-title">👨‍🍳 烹饪步骤</div>
      <van-steps direction="vertical" :active="99">
        <van-step v-for="(s, i) in r.steps" :key="i">{{ s }}</van-step>
      </van-steps>
    </div>

    <div class="card" v-if="!r.is_builtin || true">
      <div class="card-title">📷 上传成品图</div>
      <van-uploader :after-read="upload" max-count="1" />
    </div>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import { showSuccessToast } from 'vant'
import api from '../api'

const route = useRoute()
const r = ref(null)

async function load() { r.value = await api.recipe(route.params.id) }
async function upload(file) {
  await api.uploadRecipeImage(route.params.id, file.file)
  showSuccessToast('上传成功')
  load()
}
onMounted(load)
</script>
