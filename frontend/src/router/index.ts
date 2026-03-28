import { createRouter, createWebHistory } from 'vue-router'
import RoutePlaceholder from '../views/RoutePlaceholder.vue'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/dashboard' },
    { path: '/dashboard', name: 'dashboard', component: RoutePlaceholder },
    { path: '/history', name: 'history', component: RoutePlaceholder },
    { path: '/predictions', name: 'predictions', component: RoutePlaceholder },
    { path: '/predictions/history', name: 'predictions-history', component: RoutePlaceholder },
    {
      path: '/predictions/history/sessions/:sessionId',
      name: 'predictions-history-session',
      component: RoutePlaceholder,
    },
    { path: '/automation', name: 'automation', component: RoutePlaceholder },
    {
      path: '/automation/intelligent-batch-follow',
      name: 'automation-intelligent-follow',
      component: RoutePlaceholder,
    },
    {
      path: '/automation/batch-unfollow',
      name: 'automation-batch-unfollow',
      component: RoutePlaceholder,
    },
    {
      path: '/automation/left-right-compare',
      name: 'automation-left-right-compare',
      component: RoutePlaceholder,
    },
    {
      path: '/automation/left-right-compare/results/:actionId?',
      name: 'automation-left-right-compare-results',
      component: RoutePlaceholder,
    },
    {
      path: '/automation/left-right-compare/history',
      name: 'automation-left-right-compare-history',
      component: RoutePlaceholder,
    },
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
