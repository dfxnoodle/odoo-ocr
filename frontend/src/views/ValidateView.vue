<template>
  <div class="validate-page">
    <div v-if="store.state === 'error'" class="alert alert-error page-error">
      ⚠ {{ store.error }}
      <button class="btn btn-secondary" style="margin-left:auto" @click="router.push('/')">
        Start over
      </button>
    </div>
    <ValidationView v-else />
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router'
import ValidationView from '@/components/ValidationView.vue'
import { useExtractionStore } from '@/stores/extraction'

const store = useExtractionStore()
const router = useRouter()
</script>

<style scoped>
.validate-page {
  height: 100%;
  display: flex;
  flex-direction: column;
  gap: 16px;
}
.page-error {
  width: 100%;
}
</style>
