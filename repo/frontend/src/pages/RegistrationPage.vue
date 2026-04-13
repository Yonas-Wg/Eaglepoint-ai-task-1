<template>
  <div class="card">
    <h2>Registration</h2>
    <input v-model="title" placeholder="Activity title" />
    <input v-model="idNumber" placeholder="ID number" />
    <input v-model="contact" placeholder="Contact" />
    <button :disabled="loading" @click="submit">
      {{ loading ? "Submitting..." : "Submit" }}
    </button>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
  <div class="card">
    <h2>Material Upload (Checklist Item)</h2>
    <input v-model.number="registrationId" type="number" placeholder="Registration ID" />
    <input v-model="materialType" placeholder="Material type (e.g. proposal)" />
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
const registrationId = ref(1);
const materialType = ref("proposal");
const fileRef = ref(null);
const uploading = ref(false);
const uploadMsg = ref("");
const uploadErr = ref("");

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
    message.value = `Created registration #${data.id}`;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const onFileChange = (event) => {
  fileRef.value = event.target.files?.[0] || null;
};

const uploadMaterial = async () => {
  uploading.value = true;
  uploadMsg.value = "";
  uploadErr.value = "";
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    if (!fileRef.value) throw new Error("Please choose a file first");
    const form = new FormData();
    form.append("upload", fileRef.value);
    const { data } = await api.post(
      `/materials/upload?registration_id=${registrationId.value}&material_type=${encodeURIComponent(materialType.value)}`,
      form
    );
    uploadMsg.value = `Uploaded as version ${data.version_no}`;
  } catch (e) {
    uploadErr.value = e?.response?.data?.detail?.msg || e.message || "Upload failed";
  } finally {
    uploading.value = false;
  }
};
</script>
