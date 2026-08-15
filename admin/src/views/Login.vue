<template>
  <div class="login-container">
    <div class="login-card">
      <div class="login-header">
        <div class="logo-icon">
          <RobotOutlined />
        </div>
        <h1 class="login-title">AI Agent Platform</h1>
        <p class="login-subtitle">企业级 AI Agent 管理后台</p>
      </div>

      <a-form
        :model="form"
        @finish="handleLogin"
        layout="vertical"
        class="login-form"
      >
        <a-form-item
          name="username"
          :rules="[{ required: true, message: '请输入用户名' }]"
        >
          <a-input
            v-model:value="form.username"
            size="large"
            placeholder="用户名"
            @pressEnter="handleLogin"
          >
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>

        <a-form-item
          name="password"
          :rules="[{ required: true, message: '请输入密码' }]"
        >
          <a-input-password
            v-model:value="form.password"
            size="large"
            placeholder="密码"
            @pressEnter="handleLogin"
          >
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>

        <a-form-item>
          <a-button
            type="primary"
            html-type="submit"
            size="large"
            :loading="authStore.loading"
            block
          >
            登 录
          </a-button>
        </a-form-item>
      </a-form>

      <div class="demo-accounts">
        <p class="demo-title">演示账号</p>
        <div class="demo-row" @click="fillAdmin">
          <a-tag color="red">管理员</a-tag>
          <span>admin / admin123456</span>
        </div>
        <div class="demo-row" @click="fillCS">
          <a-tag color="blue">客服</a-tag>
          <span>cs_agent / cs123456</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive } from 'vue'
import { useRouter } from 'vue-router'
import { message } from 'ant-design-vue'
import { UserOutlined, LockOutlined, RobotOutlined } from '@ant-design/icons-vue'
import { useAuthStore } from '@/stores/auth'

const router = useRouter()
const authStore = useAuthStore()

const form = reactive({
  username: '',
  password: ''
})

function fillAdmin() {
  form.username = 'admin'
  form.password = 'admin123456'
}

function fillCS() {
  form.username = 'cs_agent'
  form.password = 'cs123456'
}

async function handleLogin() {
  if (!form.username || !form.password) return
  try {
    await authStore.login(form.username, form.password)
    message.success(`欢迎回来，${authStore.user?.full_name || authStore.user?.username}`)
    router.push('/dashboard')
  } catch {
    // error already handled by axios interceptor
  }
}
</script>

<style scoped>
.login-container {
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
  padding: 20px;
}

.login-card {
  background: #fff;
  border-radius: 16px;
  padding: 48px 40px;
  width: 100%;
  max-width: 420px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.15);
}

.login-header {
  text-align: center;
  margin-bottom: 32px;
}

.logo-icon {
  font-size: 48px;
  color: #1677ff;
  margin-bottom: 16px;
}

.login-title {
  font-size: 24px;
  font-weight: 700;
  color: #1a1a2e;
  margin: 0 0 8px;
}

.login-subtitle {
  font-size: 14px;
  color: #888;
  margin: 0;
}

.login-form {
  margin-bottom: 24px;
}

.demo-accounts {
  border-top: 1px solid #f0f0f0;
  padding-top: 20px;
}

.demo-title {
  font-size: 12px;
  color: #aaa;
  margin-bottom: 12px;
}

.demo-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
  cursor: pointer;
  font-size: 13px;
  color: #666;
  border-radius: 6px;
  transition: background 0.2s;
}

.demo-row:hover {
  background: #f5f5f5;
  color: #333;
}
</style>
