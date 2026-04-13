<template>
  <div class="card">
    <h2>System Administration</h2>
    <input v-model.number="registrationId" type="number" placeholder="Registration ID" />
    <input v-model="deadlineIso" placeholder="Deadline ISO (e.g. 2026-04-14T18:00:00Z)" />
    <button :disabled="loading" @click="setDeadline">Set Deadline</button>
  </div>

  <div class="card">
    <h2>Data Collection Batch</h2>
    <input v-model="batchName" placeholder="Batch name" />
    <input v-model="scope" placeholder="Whitelist scope" />
    <button :disabled="loading" @click="createBatch">Create Batch</button>
  </div>

  <div class="card">
    <h2>Backup and Recovery</h2>
    <button :disabled="loading" @click="backupNow">Create Backup</button>
    <button :disabled="loading" @click="recoverNow">One-click Recovery</button>
    <div class="table-wrap" v-if="resultRows.length">
      <table>
        <thead>
          <tr><th>Field</th><th>Value</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in resultRows" :key="row.key">
            <td>{{ row.label }}</td>
            <td>{{ row.value }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { computed, ref } from "vue";
import api, { setToken } from "../api";

const registrationId = ref(1);
const deadlineIso = ref(new Date(Date.now() + 24 * 60 * 60 * 1000).toISOString());
const batchName = ref("Initial collection batch");
const scope = ref("activity-approved-template");
const loading = ref(false);
const message = ref("");
const error = ref("");
const result = ref({});
const resultRows = computed(() =>
  Object.entries(result.value || {}).map(([key, value]) => ({
    key,
    label: key.replaceAll("_", " ").replace(/^\w/, (c) => c.toUpperCase()),
    value: String(value),
  }))
);

const ensureToken = () => {
  const token = localStorage.getItem("token");
  if (token) setToken(token);
};

const setDeadline = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.post(`/registrations/${registrationId.value}/deadline`, { deadline_iso: deadlineIso.value });
    result.value = data;
    message.value = "Deadline updated";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const createBatch = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.post("/batches", {
      registration_id: registrationId.value,
      batch_name: batchName.value,
      whitelist_scope: scope.value,
    });
    result.value = data;
    message.value = "Batch created";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const backupNow = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.post("/system/backup");
    result.value = data;
    message.value = "Backup created";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const recoverNow = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.post("/system/recovery");
    result.value = data;
    message.value = "Recovery completed";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};
</script>
