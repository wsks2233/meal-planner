<template>
  <!-- 底部 Tab 导航：移动端优先；临期食材红色角标 -->
  <van-tabbar route fixed placeholder safe-area-inset-bottom class="no-print">
    <van-tabbar-item replace to="/" icon="wap-home-o">仪表盘</van-tabbar-item>
    <van-tabbar-item replace to="/plan" icon="calendar-o">菜谱</van-tabbar-item>
    <van-tabbar-item replace to="/inventory" icon="shop-o"
      :badge="expiringCount || ''">库存</van-tabbar-item>
    <van-tabbar-item replace to="/shopping" icon="cart-o"
      :dot="shoppingPending">采购</van-tabbar-item>
    <van-tabbar-item replace to="/settings" icon="setting-o">设置</van-tabbar-item>
  </van-tabbar>
</template>

<script setup>
import { storeToRefs } from 'pinia'
import { useAppStore } from '../stores/app'

const { expiringCount, shoppingPending } = storeToRefs(useAppStore())
useAppStore().refreshBadges()
</script>
