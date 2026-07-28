<template>
  <van-nav-bar v-if="!$route.meta.tab" :title="$route.meta.title" left-arrow fixed placeholder
    @click-left="$router.back()" class="no-print" />
  <router-view />
  <TabBar v-if="$route.meta.tab" />
</template>

<script setup>
import TabBar from './components/TabBar.vue'
</script>
