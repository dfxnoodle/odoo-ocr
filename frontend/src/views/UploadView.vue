<template>
  <div class="upload-page">
    <div class="upload-page__hero">
      <h1>Equipment Interchange Receipt</h1>
      <p>Upload a scanned EIR document to extract container data and push it directly to Odoo.</p>
    </div>

    <div class="card upload-card">
      <DocumentUploader />
    </div>

    <div v-if="store.state === 'error'" class="alert alert-error upload-error">
      ⚠ {{ store.error }}
    </div>
  </div>
</template>

<script setup lang="ts">
import DocumentUploader from '@/components/DocumentUploader.vue'
import { useExtractionStore } from '@/stores/extraction'

const store = useExtractionStore()
</script>

<style scoped>
.upload-page {
  max-width: 640px;
  margin: 0 auto;
  display: flex;
  flex-direction: column;
  gap: 20px;
}

.upload-page__hero {
  text-align: center;
}
.upload-page__hero h1 {
  font-size: 24px;
  font-weight: 700;
  color: var(--color-text);
  margin-bottom: 8px;
}
.upload-page__hero p {
  color: var(--color-text-subtle);
  line-height: 1.6;
}

.upload-card {
  padding: 0;
  overflow: hidden;
}

.upload-error {
  width: 100%;
}
</style>
