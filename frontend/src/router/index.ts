import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory('/'),
  routes: [
    {
      path: '/',
      name: 'upload',
      component: () => import('@/views/UploadView.vue'),
    },
    {
      path: '/validate',
      name: 'validate',
      component: () => import('@/views/ValidateView.vue'),
    },
    {
      path: '/committed',
      name: 'committed',
      component: () => import('@/views/CommittedView.vue'),
    },
  ],
})

export default router
