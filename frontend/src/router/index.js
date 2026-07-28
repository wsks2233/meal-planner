import { createRouter, createWebHistory } from 'vue-router'

const routes = [
  { path: '/', name: 'dashboard', component: () => import('../views/Dashboard.vue'), meta: { tab: true, title: '仪表盘' } },
  { path: '/plan', name: 'plan', component: () => import('../views/Plan.vue'), meta: { tab: true, title: '菜谱' } },
  { path: '/inventory', name: 'inventory', component: () => import('../views/Inventory.vue'), meta: { tab: true, title: '库存' } },
  { path: '/shopping', name: 'shopping', component: () => import('../views/Shopping.vue'), meta: { tab: true, title: '采购' } },
  { path: '/settings', name: 'settings', component: () => import('../views/Settings.vue'), meta: { tab: true, title: '设置' } },
  { path: '/plan/generate', component: () => import('../views/PlanGenerate.vue'), meta: { title: '生成菜谱' } },
  { path: '/long-term', component: () => import('../views/LongTerm.vue'), meta: { title: '长期采购模式' } },
  { path: '/purchase-in', component: () => import('../views/PurchaseIn.vue'), meta: { title: '采购入库' } },
  { path: '/prices', component: () => import('../views/Prices.vue'), meta: { title: '菜价行情' } },
  { path: '/recipes', component: () => import('../views/Recipes.vue'), meta: { title: '食谱库' } },
  { path: '/recipes/new', component: () => import('../views/RecipeEdit.vue'), meta: { title: '新建食谱' } },
  { path: '/recipes/:id', component: () => import('../views/RecipeDetail.vue'), meta: { title: '食谱详情' } },
]

export default createRouter({ history: createWebHistory(), routes })
