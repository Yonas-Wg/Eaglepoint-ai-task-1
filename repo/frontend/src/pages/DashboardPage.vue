<template>
  <div class="card">
    <h2>Dashboard</h2>
    <span class="status-badge status-good">System online</span>
    <button :disabled="loading" @click="load">
      {{ loading ? "Loading..." : "Load Metrics" }}
    </button>
    <div class="table-wrap" v-if="metrics && Object.keys(metrics).length">
      <table>
        <thead>
          <tr><th>Metric</th><th>Value</th></tr>
        </thead>
        <tbody>
          <tr><td>Approval rate</td><td>{{ metrics.approval_rate }}</td></tr>
          <tr><td>Correction rate</td><td>{{ metrics.correction_rate }}</td></tr>
          <tr><td>Overspending rate</td><td>{{ metrics.overspending_rate }}</td></tr>
        </tbody>
      </table>
    </div>
    <div>
      <button :disabled="loading" @click="exportReport('audit', 'csv')">Export Audit CSV</button>
      <button :disabled="loading" @click="exportReport('compliance', 'pdf')">Export Compliance PDF</button>
      <button :disabled="loading" @click="exportReport('reconciliation', 'csv')">Export Reconciliation CSV</button>
      <button :disabled="loading" @click="loadWhitelist">Load Whitelist Policies</button>
      <button :disabled="loading" @click="checkSimilarity">Check Similarity Endpoint</button>
    </div>
    <div v-if="similarityStatus" class="inline-note">{{ similarityStatus }}</div>
    <div class="table-wrap" v-if="policies.length">
      <table>
        <thead>
          <tr><th>Scope</th><th>Rule</th></tr>
        </thead>
        <tbody>
          <tr v-for="(policy, idx) in policies" :key="idx">
            <td>{{ policy.scope }}</td>
            <td>{{ policy.rule }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { onMounted, ref } from "vue";
import api, { setToken } from "../api";

const loading = ref(false);
const error = ref("");
const metrics = ref({});
const policies = ref([]);
const similarityStatus = ref("");

const load = async () => {
  loading.value = true;
  error.value = "";
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const { data } = await api.get("/reports/summary");
    metrics.value = data;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed to load";
  } finally {
    loading.value = false;
  }
};

onMounted(load);

const exportReport = async (reportType, format) => {
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const response = await api.get(`/reports/${reportType}/export?format=${format}`, { responseType: "blob" });
    const url = window.URL.createObjectURL(response.data);
    const link = document.createElement("a");
    link.href = url;
    link.download = `${reportType}.${format}`;
    link.click();
    window.URL.revokeObjectURL(url);
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Export failed";
  }
};

const loadWhitelist = async () => {
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const { data } = await api.get("/whitelist-policies/export");
    policies.value = Array.isArray(data?.policies) ? data.policies : [];
    similarityStatus.value = "";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  }
};

const checkSimilarity = async () => {
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const { data } = await api.get("/similarity-check");
    similarityStatus.value = data?.status === "enabled" ? "Similarity check is enabled." : "Similarity check response received.";
    policies.value = [];
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Feature disabled";
  }
};
</script>
