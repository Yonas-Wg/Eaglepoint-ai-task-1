<template>
  <div class="card">
    <h2>Finance</h2>
    <input v-model.number="registrationId" placeholder="Registration ID" type="number" />
    <input v-model.number="budget" placeholder="Budget" type="number" />
    <button :disabled="loading" @click="setBudget">
      {{ loading ? "Saving..." : "Set / Update Budget" }}
    </button>
    <select v-model="txType">
      <option value="expense">expense</option>
      <option value="income">income</option>
    </select>
    <input v-model="category" placeholder="Category" />
    <input v-model.number="amount" placeholder="Amount" type="number" />
    <button :disabled="loading" @click="save">
      {{ loading ? "Saving..." : "Save Transaction" }}
    </button>
    <input type="file" @change="onInvoiceFileChange" />
    <button :disabled="loading || !transactionId || !invoiceFile" @click="uploadInvoice">
      Upload Invoice Attachment
    </button>
    <button :disabled="loading" @click="loadStats">Load Category/Time Stats</button>
    <div class="table-wrap" v-if="stats.length">
      <table>
        <thead>
          <tr><th>Category</th><th>Total Amount</th><th>Count</th></tr>
        </thead>
        <tbody>
          <tr v-for="row in stats" :key="row.category">
            <td>{{ row.category }}</td>
            <td>{{ row.total_amount }}</td>
            <td>{{ row.count }}</td>
          </tr>
        </tbody>
      </table>
    </div>
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
const budget = ref(1000);
const loading = ref(false);
const error = ref("");
const message = ref("");
const transactionId = ref(null);
const invoiceFile = ref(null);
const stats = ref([]);

const ensureToken = () => {
  const token = localStorage.getItem("token");
  if (token) setToken(token);
};

const createTransaction = async (secondaryConfirmation) => {
  const { data } = await api.post("/transactions", {
    registration_id: registrationId.value,
    tx_type: txType.value,
    category: category.value,
    amount: amount.value,
    secondary_confirmation: secondaryConfirmation,
  });
  transactionId.value = data.id;
  return data;
};

const setBudget = async () => {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    ensureToken();
    await api.post(`/funding/${registrationId.value}/budget`, {
      budget: budget.value,
    });
    message.value = `Budget set to ${budget.value}`;
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const save = async () => {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    ensureToken();
    const { data } = await createTransaction(false);
    message.value = `Transaction #${data.id} created`;
  } catch (e) {
    const msg = e?.response?.data?.detail?.msg || "Failed";
    if (
      msg.includes("secondary confirmation required") &&
      window.confirm("Expenses exceed budget by 10%. Confirm to continue?")
    ) {
      try {
        const { data } = await createTransaction(true);
        message.value = `Transaction #${data.id} created with secondary confirmation`;
        error.value = "";
      } catch (retryErr) {
        error.value = retryErr?.response?.data?.detail?.msg || "Failed";
      }
    } else {
      error.value = msg;
    }
  } finally {
    loading.value = false;
  }
};

const onInvoiceFileChange = (event) => {
  invoiceFile.value = event.target.files?.[0] || null;
};

const uploadInvoice = async () => {
  loading.value = true;
  error.value = "";
  message.value = "";
  try {
    ensureToken();
    const form = new FormData();
    form.append("upload", invoiceFile.value);
    await api.post(`/transactions/${transactionId.value}/invoice`, form);
    message.value = "Invoice attachment uploaded";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};

const loadStats = async () => {
  loading.value = true;
  error.value = "";
  try {
    ensureToken();
    const endIso = new Date().toISOString();
    const startIso = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();
    const { data } = await api.get(
      `/transactions/stats?registration_id=${registrationId.value}&start_iso=${encodeURIComponent(startIso)}&end_iso=${encodeURIComponent(endIso)}`
    );
    stats.value = Array.isArray(data?.stats) ? data.stats : [];
    message.value = "Loaded transaction statistics";
  } catch (e) {
    error.value = e?.response?.data?.detail?.msg || "Failed";
  } finally {
    loading.value = false;
  }
};
</script>
