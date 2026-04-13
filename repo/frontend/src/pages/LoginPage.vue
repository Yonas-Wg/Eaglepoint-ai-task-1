<template>
  <div class="card">
    <h2>Login</h2>
    <input v-model="username" placeholder="Username" />
    <input v-model="password" placeholder="Password" type="password" />
    <button :disabled="loading" @click="submit">
      {{ loading ? "Logging in..." : "Login" }}
    </button>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import { useRouter } from "vue-router";
import api, { setToken } from "../api";

const router = useRouter();
const username = ref("admin");
const password = ref("admin123");
const loading = ref(false);
const error = ref("");

const submit = async () => {
  loading.value = true;
  error.value = "";
  try {
    const { data } = await api.post("/auth/login", {
      username: username.value,
      password: password.value,
    });
    setToken(data.access_token);
    localStorage.setItem("token", data.access_token);
    router.push("/dashboard");
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Login failed";
  } finally {
    loading.value = false;
  }
};
</script>
