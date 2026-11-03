<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div class="card budget-card">
      <div class="budget-row">
        <label for="budget-slider" class="stat-label budget-label">{{ t('restocking.budget') }}</label>
        <output class="budget-readout" for="budget-slider">{{ money(budget) }}</output>
      </div>
      <input
        id="budget-slider"
        v-model.number="budget"
        type="range"
        class="budget-slider"
        :min="BUDGET_MIN"
        :max="BUDGET_MAX"
        :step="BUDGET_STEP"
        :aria-label="t('restocking.budgetSlider')"
      />
      <div class="budget-scale">
        <span>{{ money(BUDGET_MIN) }}</span>
        <span>{{ money(BUDGET_MAX) }}</span>
      </div>
    </div>

    <div v-if="error" class="error">{{ error }}</div>

    <div v-if="loading && !recommendation" class="loading">{{ t('common.loading') }}</div>
    <template v-else-if="recommendation">
      <div class="stats-grid" :class="{ refreshing: loading }">
        <div class="stat-card info">
          <div class="stat-label">{{ t('restocking.totalCost') }}</div>
          <div class="stat-value">{{ money(recommendation.total_cost) }}</div>
        </div>
        <div class="stat-card success">
          <div class="stat-label">{{ t('restocking.remainingBudget') }}</div>
          <div class="stat-value">{{ money(recommendation.remaining_budget) }}</div>
        </div>
        <div class="stat-card warning">
          <div class="stat-label">{{ t('restocking.leadTime') }}</div>
          <div class="stat-value">{{ days(recommendation.lead_time_days) }}</div>
        </div>
      </div>

      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations') }} ({{ items.length }})</h3>
          <button
            type="button"
            class="btn-primary"
            :disabled="items.length === 0 || submitting || loading || stale"
            @click="showConfirm = true"
          >
            {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
          </button>
        </div>

        <div v-if="submitError" class="error">{{ submitError }}</div>

        <div v-if="items.length === 0" class="empty-state">{{ t('restocking.empty') }}</div>
        <div v-else class="table-container" :class="{ refreshing: loading }">
          <table>
            <thead>
              <tr>
                <th>{{ t('restocking.table.sku') }}</th>
                <th>{{ t('restocking.table.name') }}</th>
                <th>{{ t('restocking.table.trend') }}</th>
                <th class="num">{{ t('restocking.table.shortfall') }}</th>
                <th class="num">{{ t('restocking.table.quantity') }}</th>
                <th class="num">{{ t('restocking.table.unitCost') }}</th>
                <th class="num">{{ t('restocking.table.lineCost') }}</th>
                <th class="num">{{ t('restocking.table.leadTime') }}</th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="item in items" :key="item.item_sku">
                <td><strong>{{ item.item_sku }}</strong></td>
                <td>{{ item.item_name }}</td>
                <td>
                  <span :class="['badge', item.trend]">{{ t(`trends.${item.trend}`) }}</span>
                </td>
                <td class="num">{{ item.shortfall.toLocaleString() }}</td>
                <td class="num">
                  <strong>{{ item.recommended_quantity.toLocaleString() }}</strong>
                  <span
                    v-if="item.recommended_quantity < item.shortfall"
                    class="badge warning partial-badge"
                    :title="t('restocking.partialTitle', { covered: item.recommended_quantity, shortfall: item.shortfall })"
                  >{{ t('restocking.partial') }}</span>
                </td>
                <td class="num">{{ money(item.unit_cost, 2) }}</td>
                <td class="num"><strong>{{ money(item.line_cost) }}</strong></td>
                <td class="num">{{ days(item.lead_time_days) }}</td>
              </tr>
            </tbody>
          </table>
        </div>
      </div>
    </template>

    <!-- Confirmation modal (styling mirrors components/TasksModal.vue) -->
    <Teleport to="body">
      <Transition name="modal">
        <div v-if="showConfirm && recommendation" class="modal-overlay" @click="closeConfirm">
          <div class="modal-container" role="dialog" aria-modal="true" @click.stop>
            <div class="modal-header">
              <h3 class="modal-title">{{ t('restocking.confirm.title') }}</h3>
              <button type="button" class="close-button" :aria-label="t('common.close')" @click="closeConfirm">
                <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
                  <path d="M15 5L5 15M5 5L15 15" stroke="currentColor" stroke-width="2" stroke-linecap="round" />
                </svg>
              </button>
            </div>
            <div class="modal-body">
              <p class="confirm-message">{{ t('restocking.confirm.message', { count: items.length }) }}</p>
              <dl class="confirm-summary">
                <div class="confirm-row">
                  <dt>{{ t('restocking.confirm.total') }}</dt>
                  <dd>{{ money(recommendation.total_cost) }}</dd>
                </div>
                <div class="confirm-row">
                  <dt>{{ t('restocking.confirm.leadTime') }}</dt>
                  <dd>{{ days(recommendation.lead_time_days) }}</dd>
                </div>
              </dl>
            </div>
            <div class="modal-footer">
              <button type="button" class="btn-secondary" :disabled="submitting" @click="closeConfirm">
                {{ t('common.cancel') }}
              </button>
              <button type="button" class="btn-primary" :disabled="submitting" @click="placeOrder">
                {{ submitting ? t('restocking.submitting') : t('restocking.placeOrder') }}
              </button>
            </div>
          </div>
        </div>
      </Transition>
    </Teleport>
  </div>
</template>

<script setup>
import { ref, computed, watch, onMounted, onBeforeUnmount } from 'vue'
import { useRouter } from 'vue-router'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency, formatCurrencyWithDecimals } from '../utils/currency'

const BUDGET_MIN = 0
const BUDGET_MAX = 500000
const BUDGET_STEP = 5000
const DEBOUNCE_MS = 300

const router = useRouter()
const { t, currentCurrency } = useI18n()

// The slider value is always USD; only display formatting follows the locale currency.
const budget = ref(100000)
const recommendation = ref(null)
const loading = ref(true)
const error = ref(null)
const showConfirm = ref(false)
const submitting = ref(false)
const submitError = ref(null)
// True from a slider change until the debounced reload starts: the list on screen no
// longer matches the budget shown, so ordering must be blocked during that window.
const stale = ref(false)

const items = computed(() => recommendation.value?.items ?? [])

const money = (amount, decimals = 0) =>
  decimals > 0
    ? formatCurrencyWithDecimals(amount, currentCurrency.value, decimals)
    : formatCurrency(amount, currentCurrency.value)

const days = (count) => t(count === 1 ? 'restocking.day' : 'restocking.days', { count })

// Monotonic request id: when the slider moves quickly, responses can arrive out of
// order, so only the latest request is allowed to update state.
let requestId = 0

const loadRecommendations = async () => {
  const id = ++requestId
  stale.value = false
  loading.value = true
  error.value = null
  try {
    const result = await api.getRestockingRecommendations(budget.value)
    if (id !== requestId) return
    recommendation.value = result
  } catch (err) {
    if (id !== requestId) return
    error.value = t('restocking.loadFailed') + ': ' + (err.response?.data?.detail || err.message)
    console.error('Failed to load recommendations:', err)
  } finally {
    if (id === requestId) loading.value = false
  }
}

// Debounce so dragging the slider doesn't fire a request for every step.
let debounceTimer = null
watch(budget, () => {
  stale.value = true
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(loadRecommendations, DEBOUNCE_MS)
})

const closeConfirm = () => {
  if (!submitting.value) showConfirm.value = false
}

const placeOrder = async () => {
  if (!recommendation.value || items.value.length === 0 || submitting.value || stale.value) return
  submitting.value = true
  submitError.value = null
  try {
    // Quantities are the server's recommendation; the server re-prices the lines itself.
    await api.createRestockingOrder({
      budget: recommendation.value.budget,
      items: items.value.map(i => ({ item_sku: i.item_sku, quantity: i.recommended_quantity }))
    })
    router.push('/orders')
  } catch (err) {
    submitError.value = err.response?.data?.detail || t('restocking.orderFailed')
    showConfirm.value = false
    console.error('Failed to place order:', err)
  } finally {
    submitting.value = false
  }
}

onMounted(loadRecommendations)
onBeforeUnmount(() => clearTimeout(debounceTimer))
</script>

<style scoped>
.budget-card {
  padding: 1.5rem;
}

.budget-row {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  margin-bottom: 1rem;
}

.budget-label {
  margin-bottom: 0;
}

.budget-readout {
  font-size: 2rem;
  font-weight: 700;
  color: #0f172a;
  letter-spacing: -0.025em;
}

.budget-slider {
  width: 100%;
  accent-color: #2563eb;
  cursor: pointer;
}

.budget-scale {
  display: flex;
  justify-content: space-between;
  margin-top: 0.25rem;
  font-size: 0.813rem;
  color: #64748b;
}

.refreshing {
  opacity: 0.6;
  transition: opacity 0.15s ease;
}

.num {
  text-align: right;
  white-space: nowrap;
}

.partial-badge {
  margin-left: 0.5rem;
  padding: 0.125rem 0.5rem;
}

.empty-state {
  padding: 2rem;
  text-align: center;
  color: #64748b;
  font-size: 0.938rem;
}

.btn-primary,
.btn-secondary {
  padding: 0.625rem 1.25rem;
  border: none;
  border-radius: 8px;
  font-weight: 600;
  font-size: 0.875rem;
  cursor: pointer;
  transition: all 0.2s ease;
}

.btn-primary {
  background: #2563eb;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-secondary {
  background: #f1f5f9;
  color: #475569;
}

.btn-secondary:hover:not(:disabled) {
  background: #e2e8f0;
}

.btn-primary:disabled,
.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Modal (same look as TasksModal) */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  background: white;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0, 0, 0, 0.3);
  width: 90%;
  max-width: 480px;
  max-height: 85vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 1.5rem 2rem;
  border-bottom: 2px solid #e2e8f0;
}

.modal-title {
  font-size: 1.5rem;
  font-weight: 600;
  color: #0f172a;
  margin: 0;
}

.close-button {
  background: none;
  border: none;
  color: #64748b;
  cursor: pointer;
  padding: 0.5rem;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  transition: all 0.2s ease;
}

.close-button:hover {
  background: #f1f5f9;
  color: #0f172a;
}

.modal-body {
  padding: 2rem;
  overflow-y: auto;
  flex: 1;
}

.modal-footer {
  padding: 1.5rem 2rem;
  border-top: 2px solid #e2e8f0;
  display: flex;
  justify-content: flex-end;
  gap: 1rem;
}

.confirm-message {
  color: #475569;
  margin-bottom: 1.25rem;
}

.confirm-summary {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.confirm-row {
  display: flex;
  justify-content: space-between;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid #f1f5f9;
}

.confirm-row dt {
  color: #64748b;
  font-weight: 600;
}

.confirm-row dd {
  color: #0f172a;
  font-weight: 700;
}

.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.3s ease;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.3s ease;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.9);
}
</style>
