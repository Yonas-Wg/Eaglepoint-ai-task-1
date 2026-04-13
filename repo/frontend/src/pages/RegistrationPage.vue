<template>
  <div class="card">
    <h2>Registration Wizard</h2>
    <p>Step {{ step }} / 3</p>
    <input v-if="step === 1" v-model="title" placeholder="Activity title" />
    <input v-if="step === 2" v-model="idNumber" placeholder="ID number" />
    <input v-if="step === 2" v-model="contact" placeholder="Contact" />
    <button v-if="step < 3" @click="nextStep">Next</button>
    <button v-if="step > 1" @click="prevStep">Back</button>
    <button v-if="step === 3" :disabled="loading" @click="submit">
      {{ loading ? "Submitting..." : "Submit Registration" }}
    </button>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
  <div class="card">
    <h2>Checklist Material Upload</h2>
    <input v-model.number="registrationId" type="number" placeholder="Registration ID" />
    <button :disabled="uploading || !registrationId" @click="loadChecklist">Load Checklist</button>
    <select v-model="materialType">
      <option disabled value="">Select checklist item</option>
      <option
        v-for="item in checklistItems"
        :key="item.material_type"
        :value="item.material_type"
      >
        {{ item.material_type }} ({{ item.status_label }})
      </option>
    </select>
    <label>
      <input type="checkbox" v-model="isFinalSubmit" />
      Final submit this checklist item
    </label>
    <input type="file" @change="onFileChange" />
    <button :disabled="uploading" @click="uploadMaterial">
      {{ uploading ? "Uploading..." : "Upload Material" }}
    </button>
    <p v-if="uploadMsg" class="success">{{ uploadMsg }}</p>
    <p v-if="uploadErr" class="error">{{ uploadErr }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import api, { setToken } from "../api";

const title = ref("");
const idNumber = ref("");
const contact = ref("");
const loading = ref(false);
const message = ref("");
const error = ref("");
const step = ref(1);
const registrationId = ref(1);
const materialType = ref("");
const isFinalSubmit = ref(false);
const fileRef = ref(null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadErr = ref("");
const checklistItems = ref([]);
const allowedFileExt = new Set(["pdf", "jpg", "jpeg", "png"]);
const maxSingleFileSize = 20 * 1024 * 1024;
const maxTotalFileSize = 200 * 1024 * 1024;

const nextStep = () => {
  step.value = Math.min(step.value + 1, 3);
};

const prevStep = () => {
  step.value = Math.max(step.value - 1, 1);
};

const submit = async () => {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const { data } = await api.post("/registrations", {
      title: title.value,
      id_number: idNumber.value,
      contact: contact.value,
    });
    registrationId.value = data.id;
    await loadChecklist();
    message.value = `Created registration #${data.id}`;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const loadChecklist = async () => {
  uploadErr.value = "";
  uploadMsg.value = "";
  const token = localStorage.getItem("token");
  if (token) setToken(token);
  const { data } = await api.get(`/materials/checklist/${registrationId.value}`);
  checklistItems.value = Array.isArray(data?.items) ? data.items : [];
  if (!materialType.value && checklistItems.value.length) {
    materialType.value = checklistItems.value[0].material_type;
  }
};

const onFileChange = (event) => {
  uploadErr.value = "";
  fileRef.value = event.target.files?.[0] || null;
  if (!fileRef.value) return;
  const name = fileRef.value.name || "";
  const ext = name.includes(".") ? name.split(".").pop().toLowerCase() : "";
  if (!allowedFileExt.has(ext)) {
    uploadErr.value = "Only PDF/JPG/PNG files are allowed";
    fileRef.value = null;
    return;
  }
  if (fileRef.value.size > maxSingleFileSize) {
    uploadErr.value = "Single file exceeds 20MB";
    fileRef.value = null;
  }
};

const uploadMaterial = async () => {
  uploading.value = true;
  uploadMsg.value = "";
  uploadErr.value = "";
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    if (!fileRef.value) throw new Error("Please choose a file first");
    if (!materialType.value) throw new Error("Please select a checklist item first");
    const usage = await api.get(`/materials/usage/${registrationId.value}`);
    const currentTotal = Number(usage?.data?.total_size_bytes || 0);
    if (currentTotal + fileRef.value.size > maxTotalFileSize) {
      throw new Error("Total files exceed 200MB");
    }
    const form = new FormData();
    form.append("upload", fileRef.value);
    const { data } = await api.post(
      `/materials/upload?registration_id=${registrationId.value}&material_type=${encodeURIComponent(materialType.value)}`,
      form
    );
    uploadMsg.value = isFinalSubmit.value
      ? `Submitted checklist item as version ${data.version_no}`
      : `Saved checklist draft as version ${data.version_no}`;
    await loadChecklist();
  } catch (e) {
    uploadErr.value = e?.response?.data?.detail?.msg || e.message || "Upload failed";
  } finally {
    uploading.value = false;
  }
};
</script>
