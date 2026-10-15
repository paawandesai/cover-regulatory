<script setup lang="ts">
defineProps<{ eyebrow: string; title: string; body: string; detail?: string }>()
</script>

<template>
  <section class="card stop" role="status">
    <span class="eyebrow">{{ eyebrow }}</span>
    <h2>{{ title }}</h2>
    <p>{{ body }}</p>
    <p v-if="detail" class="small muted">{{ detail }}</p>
    <slot />
  </section>
</template>

<style scoped>
.stop {
  max-width: 640px;
  padding: 24px;
  display: flex;
  flex-direction: column;
  gap: 12px;
}
h2 {
  margin: 0;
  font-size: 18px;
  line-height: 24px;
  font-weight: 600;
}
p {
  margin: 0;
}
</style>
