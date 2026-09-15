<template>
  <div class="restocking">
    <div class="page-header">
      <h2>{{ t('restocking.title') }}</h2>
      <p>{{ t('restocking.description') }}</p>
    </div>

    <div v-if="loading" class="loading">{{ t('common.loading') }}</div>
    <div v-else-if="error" class="error">{{ error }}</div>
    <div v-else>
      <!-- Budget card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.budget.title') }}</h3>
        </div>
        <div class="budget-slider-row">
          <label for="restocking-budget" class="budget-slider-label">{{ t('restocking.budget.label') }}</label>
          <input
            id="restocking-budget"
            type="range"
            min="0"
            max="50000"
            step="500"
            v-model.number="budget"
            @input="onBudgetInput"
            class="budget-slider"
          />
          <span class="budget-slider-value">{{ formatCurrency(budget, currentCurrency) }}</span>
        </div>

        <div class="stats-grid">
          <div class="stat-card success">
            <div class="stat-label">{{ t('restocking.budget.recommended') }}</div>
            <div class="stat-value">{{ formatCurrency(recommendations.recommended_total, currentCurrency) }}</div>
          </div>
          <div class="stat-card info">
            <div class="stat-label">{{ t('restocking.budget.remaining') }}</div>
            <div class="stat-value">{{ formatCurrency(recommendations.remaining_budget, currentCurrency) }}</div>
          </div>
          <div class="stat-card">
            <div class="stat-label">{{ t('restocking.recommendations.title') }}</div>
            <div class="stat-value stat-value-small">
              {{ t('restocking.budget.itemsSelected', { count: recommendedCount, total: totalItems }) }}
            </div>
          </div>
        </div>
      </div>

      <!-- Recommendations card -->
      <div class="card">
        <div class="card-header">
          <h3 class="card-title">{{ t('restocking.recommendations.title') }}</h3>
        </div>
        <p class="card-description">{{ t('restocking.recommendations.description') }}</p>

        <div v-if="isEmpty" class="no-data">{{ t('restocking.recommendations.empty') }}</div>
        <div v-else>
          <div v-if="noneFit" class="no-data">{{ t('restocking.recommendations.noneFit') }}</div>
          <div class="table-container">
            <table>
              <thead>
                <tr>
                  <th>{{ t('restocking.table.item') }}</th>
                  <th>{{ t('restocking.table.category') }}</th>
                  <th>{{ t('restocking.table.warehouse') }}</th>
                  <th>{{ t('restocking.table.currentDemand') }}</th>
                  <th>{{ t('restocking.table.forecastedDemand') }}</th>
                  <th>{{ t('restocking.table.quantity') }}</th>
                  <th>{{ t('restocking.table.unitCost') }}</th>
                  <th>{{ t('restocking.table.lineTotal') }}</th>
                  <th>{{ t('restocking.table.leadTime') }}</th>
                  <th>{{ t('restocking.table.status') }}</th>
                </tr>
              </thead>
              <tbody>
                <tr
                  v-for="item in items"
                  :key="item.sku"
                  :class="{ 'row-skipped': !item.recommended }"
                >
                  <td>{{ translateProductName(item.name) }}</td>
                  <td>{{ translateCategory(item.category) }}</td>
                  <td>{{ translateWarehouse(item.warehouse) }}</td>
                  <td>{{ item.current_demand }}</td>
                  <td>{{ item.forecasted_demand }}</td>
                  <td>{{ item.quantity }}</td>
                  <td>{{ formatCurrency(item.unit_cost, currentCurrency) }}</td>
                  <td><strong>{{ formatCurrency(item.line_total, currentCurrency) }}</strong></td>
                  <td>{{ t('orders.submitted.leadTimeDays', { days: item.lead_time_days }) }}</td>
                  <td>
                    <span :class="['badge', item.recommended ? 'success' : 'muted']">
                      {{ item.recommended ? t('restocking.recommendations.recommendedBadge') : t('restocking.recommendations.skippedBadge') }}
                    </span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <div class="place-order-row">
          <button
            class="btn-primary"
            :disabled="recommendedCount === 0 || submitting"
            @click="placeOrder"
          >
            {{ submitting ? t('restocking.placing') : t('restocking.placeOrder') }}
          </button>

          <div v-if="orderResult" class="order-success">
            {{ t('restocking.success', { orderNumber: orderResult.order_number, days: orderResult.lead_time_days }) }}
            <router-link to="/orders">{{ t('restocking.viewOrders') }}</router-link>
          </div>
          <div v-if="orderFailed" class="order-error">{{ t('restocking.error') }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script>
import { ref, computed, onMounted } from 'vue'
import { api } from '../api'
import { useI18n } from '../composables/useI18n'
import { formatCurrency } from '../utils/currency'

export default {
  name: 'Restocking',
  setup() {
    const { t, currentCurrency, translateProductName, translateWarehouse } = useI18n()

    const loading = ref(true)
    const error = ref(null)
    const hasLoadedOnce = ref(false)

    const budget = ref(20000)
    const recommendations = ref({ budget: 0, items: [], recommended_total: 0, remaining_budget: 0 })

    const submitting = ref(false)
    const orderResult = ref(null)
    const orderFailed = ref(false)

    const items = computed(() => recommendations.value.items || [])
    const recommendedItems = computed(() => items.value.filter(i => i.recommended))
    const recommendedCount = computed(() => recommendedItems.value.length)
    const totalItems = computed(() => items.value.length)
    const isEmpty = computed(() => items.value.length === 0)
    const noneFit = computed(() => items.value.length > 0 && recommendedCount.value === 0)

    // Category names are translated locally, matching the pattern used in
    // Inventory.vue / Dashboard.vue / Spending.vue (not exported by useI18n).
    const translateCategory = (category) => {
      const categoryMap = {
        'Circuit Boards': t('categories.circuitBoards'),
        'Sensors': t('categories.sensors'),
        'Actuators': t('categories.actuators'),
        'Controllers': t('categories.controllers'),
        'Power Supplies': t('categories.powerSupplies')
      }
      return categoryMap[category] || category
    }

    const fetchRecommendations = async () => {
      try {
        // Only show the full-page loading state on the very first fetch;
        // slider-driven refetches keep the last good result on screen.
        if (!hasLoadedOnce.value) {
          loading.value = true
        }
        error.value = null
        const data = await api.getRestockingRecommendations(budget.value)
        recommendations.value = data
        hasLoadedOnce.value = true
      } catch (err) {
        error.value = 'Failed to load restocking recommendations: ' + err.message
      } finally {
        loading.value = false
      }
    }

    let debounceTimer = null
    const onBudgetInput = () => {
      // Clear any stale order notice: it referred to the previous budget.
      orderResult.value = null
      orderFailed.value = false

      // The native range input fires an 'input' event on every pixel of drag,
      // so debounce the refetch by ~150ms to avoid spamming the API.
      if (debounceTimer) clearTimeout(debounceTimer)
      debounceTimer = setTimeout(() => {
        fetchRecommendations()
      }, 150)
    }

    const placeOrder = async () => {
      if (recommendedCount.value === 0 || submitting.value) return
      submitting.value = true
      orderFailed.value = false
      orderResult.value = null
      try {
        const orderData = {
          items: recommendedItems.value.map(i => ({ sku: i.sku, quantity: i.quantity })),
          budget: budget.value
        }
        orderResult.value = await api.placeRestockingOrder(orderData)
      } catch (err) {
        orderFailed.value = true
        console.error('Failed to place restocking order:', err)
      } finally {
        submitting.value = false
      }
    }

    onMounted(() => fetchRecommendations())

    return {
      t,
      loading,
      error,
      budget,
      recommendations,
      items,
      recommendedCount,
      totalItems,
      isEmpty,
      noneFit,
      submitting,
      orderResult,
      orderFailed,
      onBudgetInput,
      placeOrder,
      currentCurrency,
      formatCurrency,
      translateProductName,
      translateWarehouse,
      translateCategory
    }
  }
}
</script>

<style scoped>
.card-description {
  color: #64748b;
  font-size: 0.875rem;
  margin: -0.5rem 0 1rem;
}

.budget-slider-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  padding: 0.5rem 0 1.25rem;
}

.budget-slider-label {
  font-size: 0.875rem;
  font-weight: 600;
  color: #475569;
  white-space: nowrap;
}

.budget-slider {
  flex: 1;
  accent-color: #2563eb;
}

.budget-slider-value {
  min-width: 110px;
  text-align: right;
  font-size: 1.125rem;
  font-weight: 700;
  color: #0f172a;
}

.stat-value-small {
  font-size: 1.25rem;
}

.no-data {
  padding: 2rem;
  text-align: center;
  color: #94a3b8;
  font-size: 0.875rem;
}

.row-skipped {
  opacity: 0.55;
}

.badge.muted {
  background: #f1f5f9;
  color: #64748b;
}

.place-order-row {
  display: flex;
  align-items: center;
  gap: 1rem;
  margin-top: 1.25rem;
  padding-top: 1.25rem;
  border-top: 1px solid #e2e8f0;
  flex-wrap: wrap;
}

.btn-primary {
  padding: 0.625rem 1.5rem;
  background: #2563eb;
  color: white;
  border: none;
  border-radius: 8px;
  font-size: 0.938rem;
  font-weight: 600;
  cursor: pointer;
  transition: background-color 0.2s ease;
}

.btn-primary:hover:not(:disabled) {
  background: #1d4ed8;
}

.btn-primary:disabled {
  background: #cbd5e1;
  cursor: not-allowed;
}

.order-success {
  color: #065f46;
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.order-success a {
  color: #2563eb;
  font-weight: 600;
}

.order-error {
  color: #991b1b;
  font-size: 0.875rem;
}
</style>
