<script setup lang="ts">
defineProps<{ title: string; subtitle: string }>()
</script>

<template>
  <header class="hdr">
    <div class="inner">
      <RouterLink to="/" class="brand">
        <span class="name">{{ title }}</span>
        <span class="eyebrow">{{ subtitle }}</span>
      </RouterLink>
      <slot />
    </div>
  </header>
</template>

<style scoped>
.hdr {
  background: var(--surface);
  border-bottom: 1px solid var(--line);
}
.inner {
  max-width: 1440px;
  margin: 0 auto;
  padding: 12px 24px;
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
}
.brand {
  display: flex;
  flex-direction: column;
  margin-right: 8px;
  color: inherit;
  text-decoration: none;
}
.name {
  font-weight: 600;
  font-size: 18px;
  line-height: 24px;
}
</style>
