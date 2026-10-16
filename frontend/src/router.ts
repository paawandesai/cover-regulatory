import { createRouter, createWebHistory } from 'vue-router'
import AssessView from './views/AssessView.vue'

export const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', component: AssessView },
    { path: '/review', component: () => import('./views/ReviewView.vue') },
    { path: '/:pathMatch(.*)*', redirect: '/' },
  ],
})
