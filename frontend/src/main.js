import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Vant from 'vant'
import 'vant/lib/index.css'
import App from './App.vue'
import router from './router'
import './styles.css'

const app = createApp(App)
app.use(createPinia()).use(router).use(Vant)
app.mount('#app')

// 每日 8 点"今日菜谱"浏览器通知（页面打开状态下检查；
// 真正的离线推送需 Web Push + HTTPS 服务端，见 README 说明）
async function scheduleDailyNotify() {
  if (!('Notification' in window)) return
  const check = async () => {
    const now = new Date()
    const key = 'notified-' + now.toISOString().slice(0, 10)
    if (now.getHours() >= 8 && !localStorage.getItem(key)) {
      if (Notification.permission === 'granted') {
        try {
          const res = await fetch('/api/plans/today')
          const meals = await res.json()
          if (meals.length) {
            const names = meals.map(m => m.recipe).join('、')
            new Notification('今日菜谱 🍳', { body: names, icon: '/icon-192.png' })
          }
          localStorage.setItem(key, '1')
        } catch { /* 离线时静默 */ }
      }
    }
  }
  check()
  setInterval(check, 10 * 60 * 1000)
}
scheduleDailyNotify()
