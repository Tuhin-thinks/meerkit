import { createRouter, createWebHistory } from 'vue-router'
import RoutePlaceholder from '../views/RoutePlaceholder.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: RoutePlaceholder },
    { path: '/history', name: 'history', component: RoutePlaceholder },
    { path: '/predictions', name: 'predictions', component: RoutePlaceholder },
    { path: '/discovery/:username?', name: 'discovery', component: RoutePlaceholder },
    { path: '/tasks', name: 'tasks', component: RoutePlaceholder },
    { path: '/admin', name: 'admin', component: RoutePlaceholder },
    {
      path: '/admin/accounts/:instagramUserId',
      name: 'details',
      component: RoutePlaceholder,
    },
    { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
  ],
})

export default router
