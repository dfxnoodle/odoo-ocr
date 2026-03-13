<template>
  <div class="app-shell">
    <header class="app-header">
      <div class="header-inner">
        <span class="logo-mark">EIR</span>
        <span class="logo-text">OCR Platform</span>
      </div>
    </header>

    <main class="app-main">
      <router-view v-slot="{ Component }">
        <transition name="fade" mode="out-in">
          <component :is="Component" />
        </transition>
      </router-view>
    </main>
  </div>
</template>

<style>
/* Global reset and CSS variables */
*,
*::before,
*::after {
  box-sizing: border-box;
  margin: 0;
  padding: 0;
}

:root {
  --color-primary: #0052cc;
  --color-primary-hover: #0041a3;
  --color-success: #006644;
  --color-warning: #ff8b00;
  --color-danger: #de350b;
  --color-surface: #ffffff;
  --color-surface-secondary: #f4f5f7;
  --color-border: #dfe1e6;
  --color-text: #172b4d;
  --color-text-subtle: #6b778c;
  --radius: 6px;
  --shadow-sm: 0 1px 3px rgba(0, 0, 0, 0.12);
  --shadow-md: 0 4px 12px rgba(0, 0, 0, 0.12);
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
  font-size: 14px;
  color: var(--color-text);
  background: var(--color-surface-secondary);
}

.app-shell {
  min-height: 100vh;
  display: flex;
  flex-direction: column;
}

.app-header {
  background: var(--color-primary);
  padding: 0 24px;
  height: 52px;
  display: flex;
  align-items: center;
  box-shadow: var(--shadow-sm);
  flex-shrink: 0;
}

.header-inner {
  display: flex;
  align-items: center;
  gap: 10px;
}

.logo-mark {
  background: white;
  color: var(--color-primary);
  font-weight: 800;
  font-size: 13px;
  padding: 2px 6px;
  border-radius: 4px;
  letter-spacing: 0.5px;
}

.logo-text {
  color: white;
  font-size: 16px;
  font-weight: 600;
}

.app-main {
  flex: 1;
  padding: 32px 24px;
  max-width: 1400px;
  width: 100%;
  margin: 0 auto;
}

/* Transition */
.fade-enter-active,
.fade-leave-active {
  transition: opacity 0.2s ease;
}
.fade-enter-from,
.fade-leave-to {
  opacity: 0;
}

/* Utility classes */
.btn {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  padding: 8px 16px;
  border: none;
  border-radius: var(--radius);
  cursor: pointer;
  font-size: 14px;
  font-weight: 500;
  transition: background 0.15s, opacity 0.15s;
}
.btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}
.btn-primary {
  background: var(--color-primary);
  color: white;
}
.btn-primary:hover:not(:disabled) {
  background: var(--color-primary-hover);
}
.btn-secondary {
  background: var(--color-surface);
  color: var(--color-text);
  border: 1px solid var(--color-border);
}
.btn-secondary:hover:not(:disabled) {
  background: var(--color-surface-secondary);
}
.btn-success {
  background: var(--color-success);
  color: white;
}
.btn-danger {
  background: var(--color-danger);
  color: white;
}

.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius);
  box-shadow: var(--shadow-sm);
}

.alert {
  padding: 12px 16px;
  border-radius: var(--radius);
  font-size: 13px;
  display: flex;
  align-items: flex-start;
  gap: 8px;
}
.alert-warning {
  background: #fff7e6;
  border: 1px solid #ffe58f;
  color: #7c4b00;
}
.alert-error {
  background: #fff1f0;
  border: 1px solid #ffa39e;
  color: #a8071a;
}
.alert-success {
  background: #f6ffed;
  border: 1px solid #b7eb8f;
  color: #135200;
}
</style>
