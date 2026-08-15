import { createApp } from 'vue'
import { createPinia } from 'pinia'
import Antd from 'ant-design-vue'
import 'ant-design-vue/dist/reset.css'
import App from './App.vue'
import router from './router'
import './styles/global.css'
import { useAuthStore } from '@/stores/auth'

const app = createApp(App)
const pinia = createPinia()

app.use(pinia)

// Restore auth state before mounting so all components see the user on mount
const authStore = useAuthStore()
authStore.restoreFromStorage()

app.use(router)
app.use(Antd)
app.mount('#app')
