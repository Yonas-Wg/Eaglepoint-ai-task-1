<template>
  <div class="layout">
    <header>
      <div class="header-row">
        <h1>Activity Registration and Funding Audit Platform</h1>
        <div class="header-actions">
          <button class="theme-btn" @click="toggleTheme">{{ darkMode ? "Light" : "Dark" }} mode</button>
          <button v-if="isAuthenticated" class="theme-btn" @click="logout">Logout</button>
        </div>
      </div>
      <p class="subtitle">Offline-first workflow for application, review, and financial audit operations</p>
      <nav>
        <router-link v-if="!isAuthenticated" to="/">[AUTH] Login</router-link>
        <template v-else>
          <router-link to="/dashboard">[INSIGHT] Dashboard</router-link>
          <router-link to="/registration">[FORM] Registration</router-link>
          <router-link to="/review">[REVIEW] Review</router-link>
          <router-link to="/finance">[FIN] Finance</router-link>
          <router-link to="/system">[SYS] System</router-link>
        </template>
      </nav>
    </header>
    <main>
      <router-view />
    </main>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from "vue";
import { useRoute, useRouter } from "vue-router";

const darkMode = ref(false);
const route = useRoute();
const router = useRouter();
const isAuthenticated = computed(() => {
  route.fullPath;
  return Boolean(localStorage.getItem("token"));
});

const applyTheme = () => {
  document.documentElement.setAttribute("data-theme", darkMode.value ? "dark" : "light");
};

const toggleTheme = () => {
  darkMode.value = !darkMode.value;
  localStorage.setItem("ui_theme", darkMode.value ? "dark" : "light");
  applyTheme();
};

const logout = () => {
  localStorage.removeItem("token");
  router.push("/");
};

onMounted(() => {
  darkMode.value = localStorage.getItem("ui_theme") === "dark";
  applyTheme();
});
</script>
