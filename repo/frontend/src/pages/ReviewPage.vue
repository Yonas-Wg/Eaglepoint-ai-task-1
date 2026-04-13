<template>
  <div class="card">
    <h2>Review Workflow</h2>
    <span class="status-badge status-warn">Reviewer actions</span>
    <input v-model.number="registrationId" type="number" placeholder="Registration ID" />
    <input v-model="toState" placeholder="To state (Approved/Rejected/Supplemented/...)" />
    <input v-model="comment" placeholder="Review comment" />
    <button :disabled="loading" @click="batchReview">{{ loading ? "Submitting..." : "Submit Review Batch(1)" }}</button>
    <button :disabled="loading" @click="loadLogs">Load Review Logs</button>
    <div class="table-wrap" v-if="logs.length">
      <table>
        <thead>
          <tr><th>From</th><th>To</th><th>Comment</th></tr>
        </thead>
        <tbody>
          <tr v-for="(r, idx) in logs" :key="idx">
            <td>{{ r.from }}</td>
            <td>{{ r.to }}</td>
            <td>{{ r.comment }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <p v-else>No review logs loaded yet.</p>
  </div>

  <div class="card">
    <h2>Correction + Supplementary</h2>
    <input v-model.number="materialId" type="number" placeholder="Material ID" />
    <input v-model="reason" placeholder="Correction reason" />
    <button :disabled="loading" @click="markCorrection">Mark Needs Correction</button>
    <button :disabled="loading" @click="startSupplementary">Start Supplementary (72h)</button>
    <input type="file" @change="onFileChange" />
    <button :disabled="loading" @click="supplementaryUpload">Supplementary Upload</button>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import api, { setToken } from "../api";

const registrationId = ref(1);
const toState = ref("Approved");
const comment = ref("Looks good");
const logs = ref([]);
const materialId = ref(1);
const reason = ref("Please correct this material");
const uploadFile = ref(null);
const loading = ref(false);
const message = ref("");
const error = ref("");

const ensureToken = () => {
  const token = localStorage.getItem("token");
  if (token) setToken(token);
};

const batchReview = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    await api.post("/reviews/batch", {
      items: [{ registration_id: registrationId.value, to_state: toState.value, comment: comment.value }],
    });
    message.value = "Batch review submitted";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Review failed";
  } finally {
    loading.value = false;
  }
};

const loadLogs = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.get(`/reviews/logs/${registrationId.value}`);
    logs.value = data.logs || [];
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const markCorrection = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    await api.post(`/materials/${materialId.value}/mark-correction`, { reason: reason.value });
    message.value = "Material marked for correction";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const startSupplementary = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.post(`/registrations/${registrationId.value}/supplementary/start`);
    message.value = `Supplementary window opened until ${data.supplementary_deadline}`;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const onFileChange = (e) => {
  uploadFile.value = e.target.files?.[0] || null;
};

const supplementaryUpload = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    if (!uploadFile.value) throw new Error("Select a file");
    const form = new FormData();
    form.append("upload", uploadFile.value);
    await api.post(`/materials/${materialId.value}/supplementary-upload`, form);
    message.value = "Supplementary upload completed";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || e.message || "Failed";
  } finally {
    loading.value = false;
  }
};
</script>
