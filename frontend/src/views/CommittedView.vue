<template>
  <div class="committed-page">
    <div class="committed-card card">
      <div v-if="result">
        <div v-if="result.dry_run" class="status-icon status-icon--warning">⚡</div>
        <div v-else class="status-icon status-icon--success">✓</div>

        <h1 v-if="result.dry_run">Dry Run Complete</h1>
        <h1 v-else>Committed to Odoo</h1>

        <p v-if="result.record_id && !result.dry_run">
          Record created in <strong>{{ result.odoo_model }}</strong> with ID
          <strong>#{{ result.record_id }}</strong>.
        </p>
        <p v-else-if="result.dry_run">
          Validation passed. No records were written to Odoo.
        </p>

        <div v-if="result.warnings.length" class="alert alert-warning">
          <div>
            <strong>Warnings:</strong>
            <ul>
              <li v-for="w in result.warnings" :key="w">{{ w }}</li>
            </ul>
          </div>
        </div>

        <div v-if="Object.keys(result.unresolved_refs).length" class="alert alert-warning">
          <div>
            <strong>Unresolved references (require manual lookup in Odoo):</strong>
            <ul>
              <li v-for="(val, key) in result.unresolved_refs" :key="key">
                <code>{{ key }}</code>: {{ val }}
              </li>
            </ul>
          </div>
        </div>

        <div class="committed-actions">
          <button class="btn btn-primary" @click="onNewDocument">Process another document</button>
        </div>
      </div>

      <div v-else>
        <p>No commit result available.</p>
        <button class="btn btn-secondary" @click="router.push('/')">Go to upload</button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { useExtractionStore } from '@/stores/extraction'

const router = useRouter()
const store = useExtractionStore()

const result = computed(() => store.commitResult)

function onNewDocument() {
  store.reset()
  router.push('/')
}
</script>

<style scoped>
.committed-page {
  display: flex;
  justify-content: center;
  align-items: flex-start;
  padding-top: 40px;
}

.committed-card {
  max-width: 560px;
  width: 100%;
  padding: 40px 36px;
  text-align: center;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 16px;
}

.status-icon {
  width: 72px;
  height: 72px;
  border-radius: 50%;
  display: flex;
  align-items: center;
  justify-content: center;
  font-size: 36px;
  margin-bottom: 8px;
}
.status-icon--success { background: #f6ffed; color: #52c41a; }
.status-icon--warning { background: #fff7e6; color: #fa8c16; }

.committed-card h1 {
  font-size: 22px;
  font-weight: 700;
}

.committed-card p {
  color: var(--color-text-subtle);
  line-height: 1.6;
}

.alert {
  text-align: left;
  width: 100%;
}
.alert ul {
  margin: 4px 0 0 18px;
}

.committed-actions {
  margin-top: 8px;
}
</style>
