<template>
  <div class="page">
    <van-search v-model="kw" placeholder="搜索菜名" shape="round" @search="load" @clear="load" />
    <van-dropdown-menu style="margin-bottom:10px;border-radius:10px;overflow:hidden">
      <van-dropdown-item v-model="cat" :options="catOpts" @change="load" />
      <van-dropdown-item v-model="maxMin" :options="timeOpts" @change="load" />
    </van-dropdown-menu>

    <van-row gutter="10">
      <van-col span="12" v-for="r in recipes" :key="r.id">
        <div class="card" style="padding:0;overflow:hidden" @click="$router.push(`/recipes/${r.id}`)">
          <!-- 图片占位符 / 用户上传图 -->
          <div style="height:90px;background:#e8f7ef;display:flex;align-items:center;justify-content:center;font-size:34px">
            <img v-if="r.image_url && !r.image_url.startsWith('/placeholder')"
              :src="r.image_url" style="width:100%;height:100%;object-fit:cover" />
            <span v-else>🍽️</span>
          </div>
          <div style="padding:8px 10px">
            <b style="font-size:14px">{{ r.name }}</b>
            <div class="muted" style="margin-top:2px">
              {{ r.category }} · {{ r.cook_minutes }}min · {{ r.kcal }}kcal</div>
            <div style="margin-top:4px">
              <van-tag plain size="mini" v-for="t in r.tags.slice(0, 2)" :key="t"
                style="margin-right:4px">{{ t }}</van-tag>
            </div>
          </div>
        </div>
      </van-col>
    </van-row>

    <van-button type="primary" icon="plus" round to="/recipes/new" class="no-print"
      style="position:fixed;right:16px;bottom:80px;z-index:10">自定义食谱</van-button>
  </div>
</template>

<script setup>
import { ref, onMounted } from 'vue'
import api from '../api'

const recipes = ref([])
const kw = ref('')
const cat = ref('')
const maxMin = ref(0)
const catOpts = [
  { text: '全部分类', value: '' }, { text: '主菜', value: '主菜' },
  { text: '副菜', value: '副菜' }, { text: '主食', value: '主食' },
  { text: '汤', value: '汤' }]
const timeOpts = [
  { text: '不限时长', value: 0 }, { text: '≤15分钟(快手)', value: 15 },
  { text: '≤30分钟', value: 30 }, { text: '>30分钟(周末大菜也含)', value: 999 }]

async function load() {
  recipes.value = await api.recipes({
    q: kw.value || undefined, category: cat.value || undefined,
    max_minutes: maxMin.value || undefined })
}
onMounted(load)
</script>
