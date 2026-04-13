import { createApp } from "vue";
import { createRouter, createWebHistory } from "vue-router";
import App from "./App.vue";
import "./style.css";
import LoginPage from "./pages/LoginPage.vue";
import DashboardPage from "./pages/DashboardPage.vue";
import RegistrationPage from "./pages/RegistrationPage.vue";
import FinancePage from "./pages/FinancePage.vue";
import ReviewPage from "./pages/ReviewPage.vue";
import SystemPage from "./pages/SystemPage.vue";

const routes = [
  { path: "/", component: LoginPage },
  { path: "/dashboard", component: DashboardPage, meta: { requiresAuth: true } },
  { path: "/registration", component: RegistrationPage, meta: { requiresAuth: true } },
  { path: "/review", component: ReviewPage, meta: { requiresAuth: true } },
  { path: "/finance", component: FinancePage, meta: { requiresAuth: true } },
  { path: "/system", component: SystemPage, meta: { requiresAuth: true } },
];

const router = createRouter({
  history: createWebHistory(),
  routes,
});

router.beforeEach((to) => {
  const token = localStorage.getItem("token");
  if (to.meta.requiresAuth && !token) return "/";
  if (to.path === "/" && token) return "/dashboard";
  return true;
});

createApp(App).use(router).mount("#app");
