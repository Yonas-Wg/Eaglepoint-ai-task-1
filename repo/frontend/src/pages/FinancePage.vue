<template>
  <div class="card">
    <h2>Finance</h2>
    <input v-model.number="registrationId" placeholder="Registration ID" type="number" />
    <select v-model="txType">
      <option value="expense">expense</option>
      <option value="income">income</option>
    </select>
    <input v-model="category" placeholder="Category" />
    <input v-model.number="amount" placeholder="Amount" type="number" />
    <label><input v-model="secondary" type="checkbox" /> Secondary confirmation</label>
    <button :disabled="loading" @click="save">
      {{ loading ? "Saving..." : "Save Transaction" }}
    </button>
    <p v-if="message" class="success">{{ message }}</p>
    <p v-if="error" class="error">{{ error }}</p>
  </div>
</template>

<script setup>
import { ref } from "vue";
import api, { setToken } from "../api";

const registrationId = ref(1);
const txType = ref("expense");
const category = ref("Operations");
const amount = ref(0);
const secondary = ref(false);
const loading = ref(false);
const error = ref("");
const message = ref("");

const save = async () => {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    const token = localStorage.getItem("token");
    if (token) setToken(token);
    const { data } = await api.post("/transactions", {
      registration_id: registrationId.value,
      tx_type: txType.value,
      category: category.value,
      amount: amount.value,
      secondary_confirmation: secondary.value,
    });
    message.value = `Transaction #${data.id} created`;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};
</script>
