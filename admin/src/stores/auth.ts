import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { authApi } from '@/api/client'

export interface UserInfo {
  id: number
  username: string
  email: string
  full_name: string | null
  department: string | null
  is_active: boolean
  is_superuser: boolean
  roles: string[]
  permissions: string[]
}

export const useAuthStore = defineStore('auth', () => {
  const user = ref<UserInfo | null>(null)
  const loading = ref(false)

  const isLoggedIn = computed(() => !!localStorage.getItem('access_token'))
  const roles = computed(() => user.value?.roles || [])
  const permissions = computed(() => user.value?.permissions || [])
  const isSuperuser = computed(() => user.value?.is_superuser || false)

  function hasPermission(code: string): boolean {
    if (isSuperuser.value) return true
    return permissions.value.includes(code)
  }

  function hasAnyPermission(codes: string[]): boolean {
    if (isSuperuser.value) return true
    return codes.some((c) => permissions.value.includes(c))
  }

  async function login(username: string, password: string) {
    loading.value = true
    try {
      const res = await authApi.login(username, password)
      localStorage.setItem('access_token', res.data.access_token)
      localStorage.setItem('refresh_token', res.data.refresh_token)
      await fetchUser()
    } finally {
      loading.value = false
    }
  }

  async function fetchUser() {
    const res = await authApi.me()
    user.value = res.data
    localStorage.setItem('user_info', JSON.stringify(res.data))
    return res.data
  }

  function restoreFromStorage() {
    const stored = localStorage.getItem('user_info')
    if (stored) {
      try {
        user.value = JSON.parse(stored)
      } catch {
        // ignore parse errors
      }
    }
  }

  async function logout() {
    try {
      await authApi.logout()
    } catch {
      // ignore — we're logging out anyway
    }
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    localStorage.removeItem('user_info')
    user.value = null
  }

  return {
    user,
    loading,
    isLoggedIn,
    roles,
    permissions,
    isSuperuser,
    hasPermission,
    hasAnyPermission,
    login,
    fetchUser,
    restoreFromStorage,
    logout
  }
})
