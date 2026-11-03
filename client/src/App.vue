<template>
  <div class="app-shell" :class="{ 'rail-layout': railLayout }">
    <aside
      id="app-sidebar"
      class="sidebar"
      :class="{ open: drawerOpen, 'is-rail': sidebarRail, 'is-overlay': overlayOpen }"
    >
      <div class="sidebar-head">
        <div class="sidebar-brand">
          <span class="brand-mark" aria-hidden="true">
            <svg viewBox="0 0 24 24"><path d="M21 8l-9-5-9 5v8l9 5 9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></svg>
          </span>
          <div class="brand-text">
            <span class="brand-name">{{ t('nav.companyName') }}</span>
            <span class="brand-sub">{{ t('nav.subtitle') }}</span>
          </div>
        </div>
        <button
          type="button"
          class="sidebar-toggle"
          aria-controls="app-sidebar"
          :aria-expanded="sidebarExpanded"
          :aria-label="sidebarExpanded ? t('nav.collapseSidebar') : t('nav.expandSidebar')"
          @click="toggleSidebar"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M11 17l-5-5 5-5M18 17l-5-5 5-5" /></svg>
        </button>
      </div>

      <nav class="sidebar-nav" :aria-label="t('nav.primary')">
        <router-link
          v-for="item in navItems"
          :key="item.to"
          :to="item.to"
          class="nav-link"
          :data-label="t(item.label)"
        >
          <svg class="nav-icon" viewBox="0 0 24 24" aria-hidden="true" v-html="item.icon" />
          <span class="nav-label">{{ t(item.label) }}</span>
        </router-link>
      </nav>
    </aside>
    <div v-if="drawerOpen" class="drawer-backdrop" aria-hidden="true" @click="drawerOpen = false"></div>

    <div class="main-column">
      <header class="content-header">
        <button
          type="button"
          class="menu-button"
          aria-controls="app-sidebar"
          :aria-expanded="drawerOpen"
          :aria-label="t('nav.menu')"
          @click="drawerOpen = !drawerOpen"
        >
          <svg viewBox="0 0 24 24" aria-hidden="true"><path d="M4 6h16M4 12h16M4 18h16" /></svg>
        </button>
        <div class="header-actions">
          <LanguageSwitcher />
          <ProfileMenu
            @show-profile-details="showProfileDetails = true"
            @show-tasks="showTasks = true"
          />
        </div>
      </header>
      <FilterBar />
      <main class="main-content">
        <router-view />
      </main>
    </div>

    <ProfileDetailsModal
      :is-open="showProfileDetails"
      @close="showProfileDetails = false"
    />

    <TasksModal
      :is-open="showTasks"
      :tasks="tasks"
      @close="showTasks = false"
      @add-task="addTask"
      @delete-task="deleteTask"
      @toggle-task="toggleTask"
    />
  </div>
</template>

<script>
import { ref, onMounted, onUnmounted, computed, watch } from 'vue'
import { useRoute } from 'vue-router'
import { api } from './api'
import { useAuth } from './composables/useAuth'
import { useI18n } from './composables/useI18n'
import FilterBar from './components/FilterBar.vue'
import ProfileMenu from './components/ProfileMenu.vue'
import ProfileDetailsModal from './components/ProfileDetailsModal.vue'
import TasksModal from './components/TasksModal.vue'
import LanguageSwitcher from './components/LanguageSwitcher.vue'

export default {
  name: 'App',
  components: {
    FilterBar,
    ProfileMenu,
    ProfileDetailsModal,
    TasksModal,
    LanguageSwitcher
  },
  setup() {
    const { currentUser } = useAuth()
    const { t } = useI18n()
    const showProfileDetails = ref(false)
    const showTasks = ref(false)
    const apiTasks = ref([])
    const route = useRoute()

    // Sidebar entries, in display order. Icons are static SVG markup (never user input),
    // so rendering them with v-html is safe.
    const navItems = [
      { to: '/', label: 'nav.overview', icon: '<rect x="3" y="3" width="7" height="7" rx="1"/><rect x="14" y="3" width="7" height="7" rx="1"/><rect x="14" y="14" width="7" height="7" rx="1"/><rect x="3" y="14" width="7" height="7" rx="1"/>' },
      { to: '/inventory', label: 'nav.inventory', icon: '<path d="M21 8l-9-5-9 5v8l9 5 9-5z"/><path d="M3 8l9 5 9-5M12 13v8"/>' },
      { to: '/orders', label: 'nav.orders', icon: '<path d="M9 4h6a1 1 0 011 1v1H8V5a1 1 0 011-1z"/><path d="M8 5H6a2 2 0 00-2 2v12a2 2 0 002 2h12a2 2 0 002-2V7a2 2 0 00-2-2h-2"/><path d="M8 12h8M8 16h5"/>' },
      { to: '/spending', label: 'nav.finance', icon: '<circle cx="12" cy="12" r="9"/><path d="M14.5 9.5c0-1-1.1-1.75-2.5-1.75S9.5 8.5 9.5 9.5 10.6 11 12 11.25s2.5.75 2.5 1.75-1.1 1.75-2.5 1.75-2.5-.75-2.5-1.75M12 6.5v1.25M12 14.75V16"/>' },
      { to: '/demand', label: 'nav.demandForecast', icon: '<path d="M3 17l6-6 4 4 8-8"/><path d="M15 7h6v6"/>' },
      { to: '/restocking', label: 'nav.restocking', icon: '<path d="M21 12a9 9 0 01-15.5 6.2M3 12A9 9 0 0118.5 5.8"/><path d="M18.5 2v4h-4M5.5 22v-4h4"/>' },
      { to: '/reports', label: 'nav.reports', icon: '<path d="M3 21h18M6 21V11M12 21V4M18 21v-7"/>' }
    ]

    // Three ranges: desktop (>=1024) collapsible sidebar, tablet (640-1023) permanent
    // rail with an overlay expand, phone (<640) off-canvas drawer.
    const STORAGE_KEY = 'sidebar-collapsed'
    const readCollapsed = () => {
      try { return localStorage.getItem(STORAGE_KEY) === 'true' } catch (e) { return false }
    }
    const collapsed = ref(readCollapsed())
    const isDesktop = ref(true)
    const isPhone = ref(false)
    // drawerOpen is the "open" state for both the phone drawer and the tablet overlay.
    const drawerOpen = ref(false)

    let mqDesktop = null
    let mqPhone = null
    const syncViewport = () => {
      isDesktop.value = mqDesktop.matches
      isPhone.value = mqPhone.matches
      drawerOpen.value = false // never carry an open overlay/drawer across a breakpoint
    }

    const toggleSidebar = () => {
      if (isDesktop.value) {
        collapsed.value = !collapsed.value
        try { localStorage.setItem(STORAGE_KEY, String(collapsed.value)) } catch (e) { /* storage unavailable */ }
      } else {
        drawerOpen.value = !drawerOpen.value
      }
    }

    // Layout rail: what the grid column reserves. Tablet always reserves the rail width,
    // regardless of the saved desktop preference.
    const railLayout = computed(() => (isDesktop.value ? collapsed.value : !isPhone.value))
    // Tablet overlay: the expanded sidebar floats (position: fixed) over the content, and
    // the grid column stays at rail width, so the page never reflows or gets squeezed.
    const overlayOpen = computed(() => !isDesktop.value && !isPhone.value && drawerOpen.value)
    // Rail visuals (icons only) apply whenever the layout is a rail and it is not overlaid.
    const sidebarRail = computed(() => railLayout.value && !overlayOpen.value)
    const sidebarExpanded = computed(() => !sidebarRail.value)

    // Closes on route change and on Escape.
    watch(() => route.path, () => { drawerOpen.value = false })
    const onKeydown = (e) => {
      if (e.key === 'Escape') drawerOpen.value = false
    }
    onMounted(() => {
      mqDesktop = window.matchMedia('(min-width: 1024px)')
      mqPhone = window.matchMedia('(max-width: 639px)')
      syncViewport()
      mqDesktop.addEventListener('change', syncViewport)
      mqPhone.addEventListener('change', syncViewport)
      window.addEventListener('keydown', onKeydown)
    })
    onUnmounted(() => {
      if (mqDesktop) mqDesktop.removeEventListener('change', syncViewport)
      if (mqPhone) mqPhone.removeEventListener('change', syncViewport)
      window.removeEventListener('keydown', onKeydown)
    })

    // Merge mock tasks from currentUser with API tasks
    const tasks = computed(() => {
      return [...currentUser.value.tasks, ...apiTasks.value]
    })

    const loadTasks = async () => {
      try {
        apiTasks.value = await api.getTasks()
      } catch (err) {
        console.error('Failed to load tasks:', err)
      }
    }

    const addTask = async (taskData) => {
      try {
        const newTask = await api.createTask(taskData)
        // Add new task to the beginning of the array
        apiTasks.value.unshift(newTask)
      } catch (err) {
        console.error('Failed to add task:', err)
      }
    }

    const deleteTask = async (taskId) => {
      try {
        // Check if it's a mock task (from currentUser)
        const isMockTask = currentUser.value.tasks.some(t => t.id === taskId)

        if (isMockTask) {
          // Remove from mock tasks
          const index = currentUser.value.tasks.findIndex(t => t.id === taskId)
          if (index !== -1) {
            currentUser.value.tasks.splice(index, 1)
          }
        } else {
          // Remove from API tasks
          await api.deleteTask(taskId)
          apiTasks.value = apiTasks.value.filter(t => t.id !== taskId)
        }
      } catch (err) {
        console.error('Failed to delete task:', err)
      }
    }

    const toggleTask = async (taskId) => {
      try {
        // Check if it's a mock task (from currentUser)
        const mockTask = currentUser.value.tasks.find(t => t.id === taskId)

        if (mockTask) {
          // Toggle mock task status
          mockTask.status = mockTask.status === 'pending' ? 'completed' : 'pending'
        } else {
          // Toggle API task
          const updatedTask = await api.toggleTask(taskId)
          const index = apiTasks.value.findIndex(t => t.id === taskId)
          if (index !== -1) {
            apiTasks.value[index] = updatedTask
          }
        }
      } catch (err) {
        console.error('Failed to toggle task:', err)
      }
    }

    onMounted(loadTasks)

    return {
      t,
      navItems,
      drawerOpen,
      railLayout,
      overlayOpen,
      sidebarRail,
      sidebarExpanded,
      toggleSidebar,
      showProfileDetails,
      showTasks,
      tasks,
      addTask,
      deleteTask,
      toggleTask
    }
  }
}
</script>

<style>
/* ---------- Design tokens ---------- */
:root {
  /* Spacing (4px base) */
  --space-1: 0.25rem;
  --space-2: 0.5rem;
  --space-3: 0.75rem;
  --space-4: 1rem;
  --space-6: 1.5rem;
  --space-8: 2rem;
  --space-12: 3rem;

  /* Radii and elevation */
  --radius-sm: 6px;
  --radius-md: 8px;
  --radius-lg: 12px;
  --shadow-sm: 0 1px 2px rgba(15, 23, 42, 0.05);
  --shadow-md: 0 4px 12px rgba(15, 23, 42, 0.08);

  /* Colours (existing slate palette) */
  --color-bg: #f8fafc;
  --color-surface: #ffffff;
  --color-border: #e2e8f0;
  --color-border-strong: #cbd5e1;
  --color-text: #1e293b;
  --color-heading: #0f172a;
  --color-text-muted: #64748b;
  --color-accent: #2563eb;
  --color-accent-soft: #eff6ff;
  --color-success: #059669;
  --color-warning: #ea580c;
  --color-danger: #dc2626;

  /* Sidebar */
  --sidebar-width: 240px;
  --sidebar-rail-width: 72px;
  --sidebar-bg: #0f172a;
  --sidebar-text: #cbd5e1;
  --sidebar-text-muted: #94a3b8;
  --sidebar-text-active: #ffffff;
  --sidebar-item-hover: rgba(255, 255, 255, 0.06);
  --sidebar-item-active: rgba(255, 255, 255, 0.12);
  --header-height: 64px;

  /* Type */
  --font-size-xs: 0.75rem;
  --font-size-sm: 0.8125rem;
  --font-size-base: 0.875rem;
  --font-size-lg: 1.125rem;
  --font-size-xl: 1.5rem;

  /* Cards */
  --card-padding: var(--space-6);
}

* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
  font-size: var(--font-size-base);
  background: var(--color-bg);
  color: var(--color-text);
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
}

:focus-visible {
  outline: 2px solid var(--color-accent);
  outline-offset: 2px;
}

/* ---------- App shell ---------- */
.app-shell {
  display: grid;
  /* The sidebar column width is a variable so the collapse can animate it */
  --sidebar-current: var(--sidebar-width);
  grid-template-columns: var(--sidebar-current) minmax(0, 1fr);
  min-height: 100vh;
  transition: grid-template-columns 0.2s ease;
}

.app-shell.rail-layout {
  --sidebar-current: var(--sidebar-rail-width);
}

.sidebar {
  position: sticky; /* stays put while the main column scrolls */
  top: 0;
  height: 100vh;
  display: flex;
  flex-direction: column;
  gap: var(--space-6);
  padding: var(--space-4) var(--space-3);
  background: var(--sidebar-bg);
  overflow-x: hidden;
  overflow-y: auto;
  z-index: 50; /* above the sticky header so rail tooltips are never covered */
}

.sidebar-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: var(--space-2);
}

.sidebar-brand {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  min-width: 0;
}

.sidebar-toggle {
  flex-shrink: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  background: transparent;
  border: 0;
  border-radius: var(--radius-md);
  color: var(--sidebar-text-muted);
  cursor: pointer;
  transition: background-color 0.15s ease, color 0.15s ease;
}

.sidebar-toggle:hover {
  background: var(--sidebar-item-hover);
  color: var(--sidebar-text-active);
}

.sidebar-toggle svg {
  width: 18px;
  height: 18px;
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
  transition: transform 0.2s ease;
}

/* Chevrons point right when the action is "expand" */
.sidebar.is-rail .sidebar-toggle svg {
  transform: rotate(180deg);
}

.brand-mark {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: var(--radius-md);
  background: var(--color-accent);
  color: #fff;
}

.brand-mark svg,
.nav-icon,
.menu-button svg {
  fill: none;
  stroke: currentColor;
  stroke-width: 1.75;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.brand-mark svg {
  width: 20px;
  height: 20px;
}

.brand-text {
  display: flex;
  flex-direction: column;
  min-width: 0;
}

.brand-name {
  color: var(--sidebar-text-active);
  font-size: var(--font-size-base);
  font-weight: 700;
  letter-spacing: -0.01em;
}

.brand-sub {
  color: var(--sidebar-text-muted);
  font-size: var(--font-size-xs);
}

.sidebar-nav {
  display: flex;
  flex-direction: column;
  gap: var(--space-1);
}

.nav-link {
  display: flex;
  align-items: center;
  gap: var(--space-3);
  padding: var(--space-2) var(--space-3);
  border-radius: var(--radius-md);
  color: var(--sidebar-text);
  font-weight: 500;
  text-decoration: none;
  white-space: nowrap;
  position: relative; /* anchors the rail tooltip and active marker */
  transition: background-color 0.15s ease, color 0.15s ease;
}

.nav-link:hover {
  background: var(--sidebar-item-hover);
  color: var(--sidebar-text-active);
}

/* All routes are leaf routes, so exact-active is right (and keeps "/" from matching everywhere) */
.nav-link.router-link-exact-active {
  background: var(--sidebar-item-active);
  color: var(--sidebar-text-active);
}

.nav-icon {
  flex-shrink: 0;
  width: 18px;
  height: 18px;
}

/* ---------- Rail (icons only) ---------- */
/* Rail needs overflow visible so tooltips can extend past the 72px column; seven items
   always fit, so the sidebar does not need its own scrolling here. */
.sidebar.is-rail {
  overflow: visible;
}

.sidebar.is-rail .sidebar-head {
  flex-direction: column;
  gap: var(--space-3);
}

.sidebar.is-rail .sidebar-brand {
  padding: var(--space-2) 0;
}

/* Visually hidden but still read by screen readers */
.sidebar.is-rail .brand-text,
.sidebar.is-rail .nav-label {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0 0 0 0);
  clip-path: inset(50%);
  white-space: nowrap;
}

.sidebar.is-rail .nav-link {
  justify-content: center;
  padding: var(--space-3) 0;
}

/* Active marker: a background tint alone is faint on 72px, so add an accent bar */
.sidebar.is-rail .nav-link.router-link-exact-active::before {
  content: '';
  position: absolute;
  left: calc(-1 * var(--space-3));
  top: 50%;
  width: 3px;
  height: 20px;
  transform: translateY(-50%);
  border-radius: 0 2px 2px 0;
  background: #60a5fa;
}

/* Tooltip from data-label; only exists in rail mode, so never shown when expanded */
.sidebar.is-rail .nav-link::after {
  content: attr(data-label);
  position: absolute;
  left: calc(100% + var(--space-3));
  top: 50%;
  transform: translateY(-50%);
  padding: var(--space-1) var(--space-3);
  border-radius: var(--radius-sm);
  background: var(--color-heading);
  color: #fff;
  font-size: var(--font-size-xs);
  font-weight: 500;
  white-space: nowrap;
  box-shadow: var(--shadow-md);
  pointer-events: none;
  opacity: 0;
  visibility: hidden;
  transition: opacity 0.15s ease, visibility 0s linear 0.15s;
}

.sidebar.is-rail .nav-link:hover::after,
.sidebar.is-rail .nav-link:focus-visible::after {
  opacity: 1;
  visibility: visible;
  transition-delay: 0s;
}

/* Tablet overlay: fixed, so it floats over the content instead of resizing the grid */
.sidebar.is-overlay {
  position: fixed;
  inset: 0 auto 0 0;
  width: var(--sidebar-width);
  overflow-x: hidden;
  overflow-y: auto;
  box-shadow: var(--shadow-md);
}

.main-column {
  min-width: 0; /* lets wide tables scroll instead of stretching the grid */
  display: flex;
  flex-direction: column;
}

.content-header {
  position: sticky;
  top: 0;
  z-index: 40;
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: var(--space-4);
  height: var(--header-height);
  padding: 0 var(--space-6);
  background: var(--color-surface);
  border-bottom: 1px solid var(--color-border);
}

.header-actions {
  display: flex;
  align-items: center;
  gap: var(--space-4);
}

.menu-button {
  display: none;
  margin-right: auto;
  padding: var(--space-2);
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-md);
  color: var(--color-heading);
  cursor: pointer;
}

.menu-button svg {
  display: block;
  width: 20px;
  height: 20px;
}

.main-content {
  flex: 1;
  width: 100%;
  max-width: 1400px;
  margin: 0 auto;
  padding: var(--space-6);
}

/* Below 1024px: tighter content padding */
@media (max-width: 1023px) {
  .drawer-backdrop {
    position: fixed;
    inset: 0;
    z-index: 45;
    background: rgba(15, 23, 42, 0.4);
  }

  .content-header,
  .main-content {
    padding-left: var(--space-4);
    padding-right: var(--space-4);
  }
}

/* Tablet (640-1023px): the sidebar stays in its grid cell as a rail. An overlay sidebar is
   position: fixed and leaves the grid, so pin the main column to column 2 or it would
   auto-place into the empty rail column and shift the content. */
@media (min-width: 640px) and (max-width: 1023px) {
  .main-column {
    grid-column: 2;
  }
}

/* Phone (<640px): the sidebar is an off-canvas drawer opened from the header menu button */
@media (max-width: 639px) {
  .app-shell {
    grid-template-columns: minmax(0, 1fr);
  }

  .sidebar {
    position: fixed;
    inset: 0 auto 0 0;
    width: var(--sidebar-width);
    transform: translateX(-100%);
    visibility: hidden; /* keeps off-screen links out of the tab order */
    transition: transform 0.2s ease, visibility 0s linear 0.2s;
  }

  .sidebar.open {
    transform: translateX(0);
    visibility: visible;
    transition-delay: 0s;
  }

  .sidebar-toggle {
    display: none; /* the header menu button handles the drawer */
  }

  .menu-button {
    display: inline-flex;
  }
}

@media (min-width: 1024px) {
  .drawer-backdrop {
    display: none;
  }
}

@media (prefers-reduced-motion: reduce) {
  .app-shell,
  .sidebar,
  .sidebar-toggle svg,
  .nav-link::after {
    transition: none !important;
  }
}

/* ---------- Shared patterns ---------- */
.page-header {
  margin-bottom: var(--space-6);
}

.page-header h2 {
  font-size: var(--font-size-xl);
  font-weight: 700;
  color: var(--color-heading);
  margin-bottom: var(--space-1);
  letter-spacing: -0.02em;
}

.page-header p {
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(240px, 1fr));
  gap: var(--space-4);
  margin-bottom: var(--space-6);
}

/* Cards: one surface treatment for stat tiles, content cards and view-specific tiles */
.stat-card,
.card {
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: var(--radius-lg);
  box-shadow: var(--shadow-sm);
  padding: var(--card-padding);
}

.stat-card {
  transition: border-color 0.2s ease, box-shadow 0.2s ease;
}

.stat-card:hover {
  border-color: var(--color-border-strong);
  box-shadow: var(--shadow-md);
}

.stat-label {
  color: var(--color-text-muted);
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  margin-bottom: var(--space-2);
}

.stat-value {
  font-size: 2rem;
  font-weight: 700;
  color: var(--color-heading);
  letter-spacing: -0.025em;
}

.stat-card.warning .stat-value {
  color: var(--color-warning);
}

.stat-card.success .stat-value {
  color: var(--color-success);
}

.stat-card.danger .stat-value {
  color: var(--color-danger);
}

.stat-card.info .stat-value {
  color: var(--color-accent);
}

.card {
  margin-bottom: var(--space-6);
}

.card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: var(--space-4);
  margin-bottom: var(--space-4);
  padding-bottom: var(--space-4);
  border-bottom: 1px solid var(--color-border);
}

.card-title {
  font-size: var(--font-size-lg);
  font-weight: 600;
  color: var(--color-heading);
  letter-spacing: -0.01em;
}

.table-container {
  overflow-x: auto;
}

table {
  width: 100%;
  border-collapse: collapse;
}

thead {
  background: var(--color-bg);
  border-top: 1px solid var(--color-border);
  border-bottom: 1px solid var(--color-border);
}

th {
  text-align: left;
  padding: var(--space-3) var(--space-4);
  font-weight: 600;
  color: #475569;
  font-size: var(--font-size-xs);
  text-transform: uppercase;
  letter-spacing: 0.05em;
}

td {
  padding: var(--space-3) var(--space-4);
  border-top: 1px solid #f1f5f9;
  color: #334155;
  font-size: var(--font-size-base);
}

tbody tr {
  transition: background-color 0.15s ease;
}

tbody tr:hover {
  background: var(--color-bg);
}

.badge {
  display: inline-block;
  padding: var(--space-1) var(--space-3);
  border-radius: 999px;
  font-size: var(--font-size-xs);
  font-weight: 600;
  text-transform: uppercase;
  letter-spacing: 0.025em;
}

.badge.success,
.badge.increasing {
  background: #d1fae5;
  color: #065f46;
}

.badge.warning,
.badge.medium {
  background: #fed7aa;
  color: #92400e;
}

.badge.danger,
.badge.decreasing,
.badge.high {
  background: #fecaca;
  color: #991b1b;
}

.badge.info,
.badge.low {
  background: #dbeafe;
  color: #1e40af;
}

.badge.stable {
  background: #e0e7ff;
  color: #3730a3;
}

.loading {
  text-align: center;
  padding: var(--space-12);
  color: var(--color-text-muted);
  font-size: var(--font-size-base);
}

.error {
  background: #fef2f2;
  border: 1px solid #fecaca;
  color: #991b1b;
  padding: var(--space-4);
  border-radius: var(--radius-md);
  margin: var(--space-4) 0;
  font-size: var(--font-size-base);
}
</style>
