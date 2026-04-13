<template>
  <div class="card">
    <h2>Review Workflow List</h2>
    <span class="status-badge status-warn">Reviewer actions</span>
    <button :disabled="loading" @click="loadQueue">Load Submission Queue</button>
    <div class="table-wrap" v-if="queue.length">
      <table>
        <thead>
          <tr><th>ID</th><th>Title</th><th>Status</th><th>Add To Batch</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in queue" :key="item.registration_id">
            <td>{{ item.registration_id }}</td>
            <td>{{ item.title }}</td>
            <td>{{ item.status }}</td>
            <td><button @click="pickRegistration(item.registration_id)">Add</button></td>
          </tr>
        </tbody>
      </table>
    </div>
    <input v-model.number="registrationId" type="number" placeholder="Batch item registration ID" />
    <input v-model="toState" placeholder="To state (Approved/Rejected/Supplemented/...)" />
    <input v-model="comment" placeholder="Review comment" />
    <button :disabled="loading" @click="addBatchItem">Add Batch Item</button>
    <div class="table-wrap" v-if="batchItems.length">
      <table>
        <thead>
          <tr><th>Registration</th><th>To State</th><th>Comment</th></tr>
        </thead>
        <tbody>
          <tr v-for="(item, idx) in batchItems" :key="idx">
            <td>{{ item.registration_id }}</td>
            <td>{{ item.to_state }}</td>
            <td>{{ item.comment }}</td>
          </tr>
        </tbody>
      </table>
    </div>
    <button :disabled="loading || !batchItems.length" @click="batchReview">{{ loading ? "Submitting..." : "Submit Review Batch" }}</button>
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
const queue = ref([]);
const batchItems = ref([]);
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

const loadQueue = async () => {
  loading.value = true;
  error.value = "";
  try {
    ensureToken();
    const { data } = await api.get("/reviews/queue?page=1&page_size=20");
    queue.value = data.items || [];
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const pickRegistration = (id) => {
  registrationId.value = id;
};

const addBatchItem = () => {
  if (!registrationId.value) return;
  batchItems.value.push({
    registration_id: registrationId.value,
    to_state: toState.value,
    comment: comment.value,
  });
};

const batchReview = async () => {
  loading.value = true;
  message.value = "";
  error.value = "";
  try {
    ensureToken();
    await api.post("/reviews/batch", { items: batchItems.value.slice(0, 50) });
    message.value = `Batch review submitted (${Math.min(batchItems.value.length, 50)} items)`;
    batchItems.value = [];
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
