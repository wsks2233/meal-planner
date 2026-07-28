import { defineStore } from 'pinia'
import api from '../api'

export const useAppStore = defineStore('app', {
  state: () => ({
    expiringCount: 0,
    shoppingPending: false,
    dashboard: null,
  }),
  actions: {
    async refreshBadges() {
      try {
        const d = await api.dashboard()
        this.dashboard = d
        this.expiringCount = d.expiring_count
        this.shoppingPending = d.shopping_pending
      } catch { /* 忽略离线错误 */ }
    },
  },
})
