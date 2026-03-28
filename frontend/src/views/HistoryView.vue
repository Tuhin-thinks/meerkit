<script setup lang="ts">
import { computed, ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import FollowerCard from '../components/FollowerCard.vue'
import AnalyticsChart from '../components/AnalyticsChart.vue'
import { HISTORY_REQUEST_DAYS } from '../constants/history'
import * as api from '../services/api'
import type { DiffResult, ScanMeta } from '../types/follower'

const props = defineProps<{
  profileId: string
}>()

const activeTab = ref<'history' | 'analytics'>('history')
const UNKNOWN_DATE_KEY = 'unknown-date'

const { data: history, isLoading } = useQuery({
  queryKey: ['history', props.profileId, HISTORY_REQUEST_DAYS],
  queryFn: () => api.getHistory(HISTORY_REQUEST_DAYS),
  staleTime: Infinity,
  refetchOnWindowFocus: false,
})

interface ScanDateGroup {
  key: string
  label: string
  scans: ScanMeta[]
  totalFollowers: number
  totalUnfollowers: number
  sortValue: number
}

function getDatePartsKey(iso: string) {
  const parsed = new Date(iso)
  if (Number.isNaN(parsed.getTime())) {
    return null
  }
  const year = parsed.getFullYear()
  const month = String(parsed.getMonth() + 1).padStart(2, '0')
  const day = String(parsed.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

function getDateLabelFromKey(key: string) {
  if (key === UNKNOWN_DATE_KEY) {
    return 'Unknown date'
  }
  const [year, month, day] = key.split('-').map((value) => Number(value))
  if (!year || !month || !day) {
    return key
  }
  return new Date(year, month - 1, day).toLocaleDateString(undefined, {
    weekday: 'short',
    month: 'short',
    day: 'numeric',
    year: 'numeric',
  })
}

function parseTimestamp(value: string) {
  const timestamp = Date.parse(value)
  return Number.isNaN(timestamp) ? 0 : timestamp
}

const groupedHistory = computed<ScanDateGroup[]>(() => {
  const scans = (history.value || []).slice().sort((a, b) => parseTimestamp(b.timestamp) - parseTimestamp(a.timestamp))
  const grouped = new Map<string, ScanMeta[]>()

  for (const scan of scans) {
    const dateKey = getDatePartsKey(scan.timestamp) || UNKNOWN_DATE_KEY
    const bucket = grouped.get(dateKey)
    if (bucket) {
      bucket.push(scan)
      continue
    }
    grouped.set(dateKey, [scan])
  }

  return Array.from(grouped.entries())
    .map(([key, groupedScans]) => {
      const firstScan = groupedScans[0]
      const totals = groupedScans.reduce(
        (acc, scan) => {
          acc.totalFollowers += typeof scan.follower_count === 'number' ? scan.follower_count : 0
          acc.totalUnfollowers += typeof scan.unfollower_count === 'number' ? scan.unfollower_count : 0
          return acc
        },
        { totalFollowers: 0, totalUnfollowers: 0 },
      )
      return {
        key,
        label: getDateLabelFromKey(key),
        scans: groupedScans,
        totalFollowers: totals.totalFollowers,
        totalUnfollowers: totals.totalUnfollowers,
        sortValue: key === UNKNOWN_DATE_KEY ? -1 : parseTimestamp(firstScan.timestamp),
      }
    })
    .sort((a, b) => b.sortValue - a.sortValue)
})

const selectedDiff = ref<DiffResult | null>(null)
const loadingDiffId = ref<string | null>(null)
const modalExportMessage = ref('')
const activeModalTab = ref<'new_followers' | 'unfollowers'>('new_followers')

async function viewDiff(diffId: string) {
  loadingDiffId.value = diffId
  try {
    selectedDiff.value = await api.getDiff(diffId)
    activeModalTab.value = 'new_followers'
    modalExportMessage.value = ''
  } finally {
    loadingDiffId.value = null
  }
}

function closeDiffModal() {
  selectedDiff.value = null
  activeModalTab.value = 'new_followers'
  modalExportMessage.value = ''
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}

function safeCount(value: number | null | undefined) {
  return typeof value === 'number' ? value : 0
}

function currentUnfollowerUsernames() {
  return (selectedDiff.value?.unfollowers || [])
    .map((item) => item.username?.trim())
    .filter((name): name is string => Boolean(name))
}

function usernamesToText(usernames: string[]) {
  return `${usernames.join('\n')}\n`
}

async function copyUnfollowersFromModal() {
  const usernames = currentUnfollowerUsernames()
  if (!usernames.length) {
    modalExportMessage.value = 'No unfollower usernames available to copy.'
    return
  }
  try {
    await navigator.clipboard.writeText(usernamesToText(usernames))
    modalExportMessage.value = `Copied ${usernames.length} usernames.`
  } catch {
    modalExportMessage.value = 'Clipboard copy failed. Please check browser permissions.'
  }
}

function downloadUnfollowersFromModal() {
  const usernames = currentUnfollowerUsernames()
  if (!usernames.length) {
    modalExportMessage.value = 'No unfollower usernames available to export.'
    return
  }
  const blob = new Blob([usernamesToText(usernames)], {
    type: 'text/plain;charset=utf-8',
  })
  const url = URL.createObjectURL(blob)
  const anchor = document.createElement('a')
  anchor.href = url
  anchor.download = `unfollowers_${new Date().toISOString().slice(0, 10)}.txt`
  document.body.appendChild(anchor)
  anchor.click()
  document.body.removeChild(anchor)
  URL.revokeObjectURL(url)
  modalExportMessage.value = `Downloaded ${usernames.length} usernames.`
}

async function handleLinkedAccountsSaved() {
  const diffId = selectedDiff.value?.diff_id
  if (!diffId) {
    return
  }
  selectedDiff.value = await api.getDiff(diffId)
}
</script>

<template>
  <div class="fade-in">
    <h2 class="text-xl font-bold font-display text-gradient mb-5">Scan History</h2>

    <!-- Tab buttons -->
    <div class="flex gap-2 mb-6 border-b border-white/[0.1]">
      <button
        @click="activeTab = 'history'"
        :class="[
          'px-4 py-2 font-medium text-sm transition-colors border-b-2',
          activeTab === 'history'
            ? 'text-violet-400 border-violet-400'
            : 'text-slate-400 border-transparent hover:text-slate-300'
        ]"
      >
        History List
      </button>
      <button
        @click="activeTab = 'analytics'"
        :class="[
          'px-4 py-2 font-medium text-sm transition-colors border-b-2',
          activeTab === 'analytics'
            ? 'text-violet-400 border-violet-400'
            : 'text-slate-400 border-transparent hover:text-slate-300'
        ]"
      >
        Analytics
      </button>
    </div>

    <!-- History tab -->
    <div v-if="activeTab === 'history'">
      <!-- Loading -->
      <div v-if="isLoading" class="space-y-3">
        <div v-for="i in 4" :key="i" class="h-16 bg-[#16213a] rounded-xl border border-white/[0.06] shimmer" />
      </div>

      <!-- Empty -->
      <div v-else-if="!history?.length" class="text-center py-16 text-slate-500">
        <p class="text-2xl mb-2">📋</p>
        <p class="font-medium text-slate-400">No scans yet</p>
        <p class="text-sm mt-1">Completed scans will appear here.</p>
      </div>

      <!-- Scan list -->
      <div v-else class="space-y-3">
        <details
          v-for="(group, index) in groupedHistory"
          :key="group.key"
          :open="index === 0"
          class="rounded-xl border border-white/[0.07] bg-[#101b30]/70"
        >
          <summary class="cursor-pointer list-none px-4 py-3 flex items-center justify-between gap-3 border-b border-white/[0.06]">
            <span class="text-sm font-semibold text-slate-200">{{ group.label }}</span>
            <div class="flex flex-wrap items-center justify-end gap-1.5 text-[11px]">
              <span class="text-slate-400">{{ group.scans.length }} scans</span>
              <span class="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300 font-semibold">
                +{{ group.totalFollowers.toLocaleString() }}
              </span>
              <span class="inline-flex items-center rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-300 font-semibold">
                -{{ group.totalUnfollowers.toLocaleString() }}
              </span>
            </div>
          </summary>

          <div class="grid gap-3 p-3">
            <div
              v-for="scan in group.scans"
              :key="scan.scan_id"
              class="bg-[#16213a] rounded-xl border border-white/[0.07] px-5 py-4 flex items-center justify-between gap-4 card-hover transition-all"
            >
              <div class="min-w-0">
                <p class="text-sm font-semibold text-slate-200">
                  {{ formatDate(scan.timestamp) }}
                </p>
                <div class="mt-1 flex flex-wrap items-center gap-1.5 text-[11px]">
                  <span class="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300 font-semibold">
                    +{{ safeCount(scan.follower_count).toLocaleString() }} followers
                  </span>
                  <span class="inline-flex items-center rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-300 font-semibold">
                    -{{ safeCount(scan.unfollower_count).toLocaleString() }} unfollowers
                  </span>
                  <span class="text-slate-500">· {{ scan.scan_id }}</span>
                </div>
              </div>

              <button
                v-if="scan.diff_id"
                :disabled="loadingDiffId === scan.diff_id"
                class="shrink-0 text-sm text-violet-400 hover:text-violet-300 font-medium px-3 py-1.5 rounded-lg hover:bg-violet-500/10 disabled:opacity-50 transition-colors"
                @click="viewDiff(scan.diff_id!)"
              >
                <span
                  v-if="loadingDiffId === scan.diff_id"
                  class="inline-block w-3.5 h-3.5 border-2 border-indigo-600 border-t-transparent rounded-full animate-spin mr-1"
                />
                View diff
              </button>
              <span v-else class="shrink-0 text-xs text-slate-600 italic">No previous scan</span>
            </div>

            <div class="rounded-xl border border-white/[0.07] bg-[#0f182b] px-5 py-3 flex flex-wrap items-center gap-2 text-[11px]">
              <span class="text-slate-400 font-semibold">Day total</span>
              <span class="inline-flex items-center rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-emerald-300 font-semibold">
                +{{ group.totalFollowers.toLocaleString() }} followers
              </span>
              <span class="inline-flex items-center rounded-full border border-rose-500/30 bg-rose-500/10 px-2 py-0.5 text-rose-300 font-semibold">
                -{{ group.totalUnfollowers.toLocaleString() }} unfollowers
              </span>
            </div>
          </div>
        </details>
      </div>
    </div>

    <!-- Analytics tab -->
    <div v-if="activeTab === 'analytics'">
      <AnalyticsChart :profile-id="profileId" />
    </div>

    <!-- Diff detail modal -->
    <Teleport to="body">
      <div
        v-if="selectedDiff"
        class="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
        @click.self="closeDiffModal"
      >
        <div
          class="bg-[#16213a] border border-white/[0.08] rounded-2xl w-full max-w-3xl max-h-[85vh] overflow-y-auto shadow-2xl shadow-black/60"
        >
          <!-- Modal header -->
          <div
            class="sticky top-0 bg-[#16213a]/95 backdrop-blur border-b border-white/[0.07] px-6 py-4 flex items-center justify-between"
          >
            <h3 class="font-bold text-slate-100">
              {{ formatDate(selectedDiff.timestamp) }}
            </h3>
            <button
              class="text-slate-500 hover:text-slate-300 w-8 h-8 flex items-center justify-center rounded-full hover:bg-white/[0.07] transition-colors"
              @click="closeDiffModal"
            >
              ✕
            </button>
          </div>

          <div class="p-6">
            <!-- Stats row -->
            <div class="grid grid-cols-2 gap-4 mb-6" role="tablist" aria-label="Diff lists">
              <button
                type="button"
                role="tab"
                :aria-selected="activeModalTab === 'new_followers'"
                :class="[
                  'rounded-xl p-4 text-center transition-all border',
                  activeModalTab === 'new_followers'
                    ? 'bg-emerald-500/15 border-emerald-400/50 ring-2 ring-emerald-400/35'
                    : 'bg-emerald-500/10 border-emerald-500/20 hover:bg-emerald-500/14 hover:border-emerald-400/35'
                ]"
                @click="activeModalTab = 'new_followers'"
              >
                <p class="text-3xl font-bold text-emerald-400">
                  +{{ selectedDiff.new_count }}
                </p>
                <p class="text-xs text-emerald-400/70 mt-1 font-medium">New Followers</p>
              </button>
              <button
                type="button"
                role="tab"
                :aria-selected="activeModalTab === 'unfollowers'"
                :class="[
                  'rounded-xl p-4 text-center transition-all border',
                  activeModalTab === 'unfollowers'
                    ? 'bg-rose-500/15 border-rose-400/50 ring-2 ring-rose-400/35'
                    : 'bg-rose-500/10 border-rose-500/20 hover:bg-rose-500/14 hover:border-rose-400/35'
                ]"
                @click="activeModalTab = 'unfollowers'"
              >
                <p class="text-3xl font-bold text-rose-400">
                  −{{ selectedDiff.unfollow_count }}
                </p>
                <p class="text-xs text-rose-400/70 mt-1 font-medium">Unfollowers</p>
              </button>
            </div>

            <!-- New followers list -->
            <template v-if="activeModalTab === 'new_followers' && selectedDiff.new_followers.length">
              <h4 class="text-sm font-semibold text-slate-300 mb-3">New Followers</h4>
              <div class="grid gap-2 mb-6">
                <FollowerCard
                  v-for="f in selectedDiff.new_followers"
                  :key="f.pk_id"
                  :follower="f"
                  :profile-id="props.profileId"
                  compact
                />
              </div>
            </template>

            <!-- Unfollowers list -->
            <template v-if="activeModalTab === 'unfollowers' && selectedDiff.unfollowers.length">
              <div class="mb-3 flex flex-wrap items-center justify-between gap-2">
                <h4 class="text-sm font-semibold text-slate-300">Unfollowers</h4>
                <div class="flex flex-wrap items-center gap-2">
                  <button
                    class="btn-ghost rounded-lg px-3 py-1.5 text-xs font-semibold"
                    @click="copyUnfollowersFromModal"
                  >
                    Copy Usernames
                  </button>
                  <button
                    class="btn-ghost rounded-lg px-3 py-1.5 text-xs font-semibold"
                    @click="downloadUnfollowersFromModal"
                  >
                    Download TXT
                  </button>
                </div>
              </div>
              <p v-if="modalExportMessage" class="text-xs text-slate-400 mb-3">{{ modalExportMessage }}</p>
              <div class="grid gap-2">
                <FollowerCard
                  v-for="f in selectedDiff.unfollowers"
                  :key="f.pk_id"
                  :follower="f"
                  :profile-id="props.profileId"
                  compact
                  show-linked-accounts-action
                  @linked-accounts-saved="handleLinkedAccountsSaved"
                />
              </div>
            </template>

            <!-- Nothing in diff -->
            <p
              v-if="
                (activeModalTab === 'new_followers' && !selectedDiff.new_followers.length) ||
                (activeModalTab === 'unfollowers' && !selectedDiff.unfollowers.length)
              "
              class="text-center text-slate-500 py-6 text-sm"
            >
              {{
                activeModalTab === 'new_followers'
                  ? 'No new followers recorded for this scan.'
                  : 'No unfollowers recorded for this scan.'
              }}
            </p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
