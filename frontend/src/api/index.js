import axios from 'axios'
import { showFailToast } from 'vant'

const http = axios.create({ baseURL: '', timeout: 15000 })
http.interceptors.response.use(
  r => r.data,
  e => {
    showFailToast(e.response?.data?.detail || e.message || '网络错误')
    return Promise.reject(e)
  }
)

export default {
  // dashboard
  dashboard: () => http.get('/api/dashboard'),
  // prices
  latestPrices: () => http.get('/api/prices/latest'),
  priceTrend: (id, days) => http.get(`/api/prices/trend/${id}`, { params: { days } }),
  // ingredients
  ingredients: params => http.get('/api/ingredients', { params }),
  byBarcode: code => http.get(`/api/ingredients/barcode/${code}`),
  // recipes
  recipes: params => http.get('/api/recipes', { params }),
  recipe: id => http.get(`/api/recipes/${id}`),
  createRecipe: d => http.post('/api/recipes', d),
  uploadRecipeImage: (id, file) => {
    const fd = new FormData()
    fd.append('file', file)
    return http.post(`/api/recipes/${id}/image`, fd)
  },
  // settings
  templates: () => http.get('/api/settings/templates'),
  createTemplate: d => http.post('/api/settings/templates', d),
  updateTemplate: (id, d) => http.put(`/api/settings/templates/${id}`, d),
  schedule: () => http.get('/api/settings/schedule'),
  updateSchedule: d => http.put('/api/settings/schedule', d),
  family: () => http.get('/api/settings/family'),
  updateFamily: d => http.put('/api/settings/family', d),
  // plans
  generatePlan: d => http.post('/api/plans/generate', d),
  plans: () => http.get('/api/plans'),
  plan: id => http.get(`/api/plans/${id}`),
  todayMeals: () => http.get('/api/plans/today'),
  replaceCandidates: id => http.get(`/api/plans/meals/${id}/replace-candidates`),
  updateMeal: (id, params) => http.put(`/api/plans/meals/${id}`, null, { params }),
  confirmPlan: id => http.post(`/api/plans/${id}/confirm`),
  // inventory
  inventory: params => http.get('/api/inventory', { params }),
  purchaseIn: d => http.post('/api/inventory', d),
  consume: d => http.post('/api/inventory/consume', d),
  discard: id => http.post(`/api/inventory/${id}/discard`),
  toShopping: id => http.post(`/api/inventory/${id}/to-shopping`),
  // shopping
  shopping: params => http.get('/api/shopping', { params }),
  markBought: d => http.post('/api/shopping/buy', d),
  mergePending: () => http.post('/api/shopping/merge-pending'),
  removeShoppingItem: id => http.delete(`/api/shopping/${id}`),
}
