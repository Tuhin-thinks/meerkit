<script setup lang="ts">
import { ref } from 'vue'
import { useQuery } from '@tanstack/vue-query'
import FollowerCard from '../components/FollowerCard.vue'
import * as api from '../services/api'
import type { DiffResult } from '../types/follower'

const props = defineProps<{
  profileId: string
}>()

const { data: history, isLoading } = useQuery({
  queryKey: ['history', props.profileId],
  queryFn: api.getHistory,
  staleTime: Infinity,
  refetchOnWindowFocus: false,
})

const selectedDiff = ref<DiffResult | null>(null)
const loadingDiffId = ref<string | null>(null)

async function viewDiff(diffId: string) {
  loadingDiffId.value = diffId
  try {
    selectedDiff.value = await api.getDiff(diffId)
  } finally {
    loadingDiffId.value = null
  }
}

function formatDate(iso: string) {
  return new Date(iso).toLocaleString()
}
</script>

<template>
  <div class="fade-in">
    <h2 class="text-xl font-bold font-display text-gradient mb-5">Scan History</h2>

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
    <div v-else class="grid gap-3">
      <div
        v-for="scan in history"
        :key="scan.scan_id"
        class="bg-[#16213a] rounded-xl border border-white/[0.07] px-5 py-4 flex items-center justify-between gap-4 card-hover transition-all"
      >
        <div class="min-w-0">
          <p class="text-sm font-semibold text-slate-200">
            {{ formatDate(scan.timestamp) }}
          </p>
          <p class="text-xs text-slate-500 mt-0.5">
            {{ scan.follower_count.toLocaleString() }} followers · {{ scan.scan_id }}
          </p>
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
    </div>

    <!-- Diff detail modal -->
    <Teleport to="body">
      <div
        v-if="selectedDiff"
        class="fixed inset-0 z-50 bg-black/70 backdrop-blur-sm flex items-end sm:items-center justify-center p-4"
        @click.self="selectedDiff = null"
      >
        <div
          class="bg-[#16213a] border border-white/[0.08] rounded-2xl w-full max-w-lg max-h-[85vh] overflow-y-auto shadow-2xl shadow-black/60"
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
              @click="selectedDiff = null"
            >
              ✕
            </button>
          </div>

          <div class="p-6">
            <!-- Stats row -->
            <div class="grid grid-cols-2 gap-4 mb-6">
              <div class="bg-emerald-500/10 border border-emerald-500/20 rounded-xl p-4 text-center">
                <p class="text-3xl font-bold text-emerald-400">
                  +{{ selectedDiff.new_count }}
                </p>
                <p class="text-xs text-emerald-400/70 mt-1 font-medium">New Followers</p>
              </div>
              <div class="bg-rose-500/10 border border-rose-500/20 rounded-xl p-4 text-center">
                <p class="text-3xl font-bold text-rose-400">
                  −{{ selectedDiff.unfollow_count }}
                </p>
                <p class="text-xs text-rose-400/70 mt-1 font-medium">Unfollowers</p>
              </div>
            </div>

            <!-- New followers list -->
            <template v-if="selectedDiff.new_followers.length">
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
            <template v-if="selectedDiff.unfollowers.length">
              <h4 class="text-sm font-semibold text-slate-300 mb-3">Unfollowers</h4>
              <div class="grid gap-2">
                <FollowerCard
                  v-for="f in selectedDiff.unfollowers"
                  :key="f.pk_id"
                  :follower="f"
                  :profile-id="props.profileId"
                  compact
                />
              </div>
            </template>

            <!-- Nothing in diff -->
            <p
              v-if="!selectedDiff.new_followers.length && !selectedDiff.unfollowers.length"
              class="text-center text-slate-500 py-6 text-sm"
            >
              No changes recorded for this scan.
            </p>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>
