<script setup lang="ts">
import { ref, computed, watch } from "vue";
import { useQuery, useMutation, useQueryClient } from "@tanstack/vue-query";
import FollowerCard from "../components/FollowerCard.vue";
import SkeletonCard from "../components/SkeletonCard.vue";
import * as api from "../services/api";
import type {
    ScanStatus,
    FollowerRecord,
    InstagramApiUsageCategorySummary,
} from "../types/follower";

const props = defineProps<{
    profileId: string;
}>();

const queryClient = useQueryClient();

// ── Scan status ────────────────────────────────────────────────────────────
// Polls every 2 s while a scan is running, otherwise stays quiet.
const { data: scanStatus } = useQuery({
    queryKey: ["scan", "status", props.profileId],
    queryFn: api.getScanStatus,
    refetchInterval: (query) => {
        const s = (query.state.data as ScanStatus | undefined)?.status;
        return s === "running" ? 2000 : false;
    },
    refetchOnWindowFocus: false,
});

// ── Summary (header stats) ─────────────────────────────────────────────────
const { data: summary } = useQuery({
    queryKey: ["summary", props.profileId],
    queryFn: api.getSummary,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
});

// ── Latest diff (tabs content) ─────────────────────────────────────────────
// staleTime: Infinity means it will never auto-refetch; only invalidated when
// a new scan completes or the user manually triggers one.
const { data: diff, isLoading: diffLoading } = useQuery({
    queryKey: ["diff", "latest", props.profileId],
    queryFn: api.getLatestDiff,
    staleTime: Infinity,
    refetchOnWindowFocus: false,
});

const { data: apiUsageSummary } = useQuery({
    queryKey: ["api", "usage", props.profileId],
    queryFn: () => api.getInstagramApiUsageSummary(props.profileId),
    staleTime: 30_000,
    refetchOnWindowFocus: false,
});

// ── Scan trigger ───────────────────────────────────────────────────────────
const scanError409 = ref(false);
const { mutate: triggerScan, isPending: triggerPending } = useMutation({
    mutationFn: api.triggerScan,
    onSuccess: () => {
        scanError409.value = false;
        // Make status polling kick in immediately
        queryClient.invalidateQueries({ queryKey: ["scan", "status", props.profileId] });
    },
    onError: (err: unknown) => {
        const status = (err as { response?: { status?: number } })?.response
            ?.status;
        scanError409.value = status === 409;
    },
});

// When a scan transitions running → idle, refresh all derived queries
watch(
    () => scanStatus.value?.status,
    (newStatus, oldStatus) => {
        if (oldStatus === "running" && newStatus === "idle") {
            queryClient.invalidateQueries({ queryKey: ["diff", "latest", props.profileId] });
            queryClient.invalidateQueries({ queryKey: ["summary", props.profileId] });
            queryClient.invalidateQueries({ queryKey: ["history", props.profileId] });
        }
    },
);

const isScanning = computed(
    () => scanStatus.value?.status === "running" || triggerPending.value,
);
const scanFailed = computed(() => scanStatus.value?.status === "error");
const scanCancelled = computed(() => scanStatus.value?.status === "cancelled");

// ── Tab state ──────────────────────────────────────────────────────────────
const activeTab = ref<"new_followers" | "unfollowers">("new_followers");

const tabItems = computed<FollowerRecord[]>(() => {
    if (!diff.value) return [];
    return activeTab.value === "new_followers"
        ? diff.value.new_followers
        : diff.value.unfollowers;
});

const tabs = computed(() => [
    {
        key: "new_followers" as const,
        label: "New Followers",
        count: diff.value?.new_count ?? 0,
        activeClass: "bg-emerald-500/20 text-emerald-300",
    },
    {
        key: "unfollowers" as const,
        label: "Unfollowers",
        count: diff.value?.unfollow_count ?? 0,
        activeClass: "bg-rose-500/20 text-rose-300",
    },
]);

const activeAccountUsage = computed(() =>
    apiUsageSummary.value?.accounts?.find(
        (item) => item.instagram_user_id === props.profileId,
    ) || null,
);

const topUsageCategories = computed<InstagramApiUsageCategorySummary[]>(() =>
    (activeAccountUsage.value?.categories || []).slice(0, 4),
);

function formatDate(iso: string | null | undefined) {
    if (!iso) return "Never";
    return new Date(iso).toLocaleString();
}
</script>

<template>
    <!-- ── Scan header card ──────────────────────────────────────────────── -->
    <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6 mb-6 fade-in">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
            <div>
                <p class="text-xs text-slate-500 uppercase tracking-wide font-medium mb-0.5">
                    Last scanned
                </p>
                <p class="text-base font-semibold text-slate-100">
                    {{ formatDate(scanStatus?.last_scan_at) }}
                </p>
                <p v-if="summary" class="text-sm text-slate-400 mt-1">
                    {{ (summary.follower_count ?? 0).toLocaleString() }} followers
                    <template v-if="summary.new_count !== undefined">
                        ·
                        <span class="text-emerald-400 font-medium">+{{ summary.new_count }}</span>
                        ·
                        <span class="text-rose-400 font-medium">−{{ summary.unfollow_count }}</span>
                    </template>
                </p>
            </div>

            <button :disabled="isScanning"
                class="btn-violet inline-flex items-center gap-2 px-5 py-2.5 text-sm font-semibold rounded-xl disabled:opacity-50 disabled:cursor-not-allowed"
                @click="triggerScan()">
                <span v-if="isScanning"
                    class="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin scan-dot" />
                {{ isScanning ? "Scanning…" : "Scan Now" }}
            </button>
        </div>

        <!-- Error banners -->
        <div v-if="scanFailed && scanStatus?.error"
            class="mt-4 p-3 bg-rose-500/10 border border-rose-500/20 rounded-xl text-sm text-rose-400">
            <strong>Scan failed:</strong> {{ scanStatus.error }}
        </div>
        <div v-if="scanCancelled && scanStatus?.error"
            class="mt-4 p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-400">
            <strong>Scan cancelled:</strong> {{ scanStatus.error }}
        </div>
        <div v-if="scanError409" class="mt-4 p-3 bg-amber-500/10 border border-amber-500/20 rounded-xl text-sm text-amber-400">
            A scan is already in progress — please wait for it to finish.
        </div>
    </div>

    <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6 mb-6">
        <div class="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
                <p class="text-xs text-slate-500 uppercase tracking-wide font-medium mb-0.5">
                    Instagram API usage (active account)
                </p>
                <p class="text-base font-semibold text-slate-100">
                    {{ (activeAccountUsage?.all_time_count ?? 0).toLocaleString() }} calls total
                </p>
                <p class="text-sm text-slate-400 mt-1">
                    {{ (activeAccountUsage?.last_24h_count ?? 0).toLocaleString() }} calls in last 24h
                </p>
            </div>
            <p class="text-xs text-slate-500" v-if="apiUsageSummary?.generated_at">
                Updated {{ formatDate(apiUsageSummary.generated_at) }}
            </p>
        </div>

        <div v-if="topUsageCategories.length" class="mt-4 grid sm:grid-cols-2 gap-3">
            <div
                v-for="category in topUsageCategories"
                :key="category.category"
                class="rounded-xl border border-white/[0.06] bg-white/[0.02] px-3 py-2"
            >
                <p class="text-xs uppercase tracking-wide text-slate-500">{{ category.category }}</p>
                <p class="text-sm font-semibold text-slate-200 mt-0.5">
                    {{ category.all_time_count.toLocaleString() }} total
                </p>
                <p class="text-xs text-slate-500">{{ category.last_24h_count.toLocaleString() }} in 24h</p>
            </div>
        </div>
    </div>

    <!-- ── No data yet ───────────────────────────────────────────────────── -->
    <div v-if="!diff && !diffLoading" class="text-center py-20 text-slate-500">
        <p class="text-2xl mb-2">🔍</p>
        <p class="text-base font-medium text-slate-400">No scan data yet</p>
        <p class="text-sm mt-1">
            Run your first scan to see new followers and unfollowers.
            <br />
            <span class="text-xs text-slate-600">
                (A diff requires at least two scans — the first scan establishes
                a baseline.)
            </span>
        </p>
    </div>

    <!-- ── Loading skeleton ──────────────────────────────────────────────── -->
    <div v-else-if="diffLoading" class="grid gap-3">
        <SkeletonCard v-for="i in 6" :key="i" />
    </div>

    <!-- ── Diff tabs ─────────────────────────────────────────────────────── -->
    <div v-else-if="diff">
        <p class="text-xs text-slate-500 mb-4">
            Results from scan on {{ formatDate(diff.timestamp) }}
        </p>

        <!-- Tab bar -->
        <div class="flex gap-0.5 bg-white/[0.04] border border-white/[0.06] p-1 rounded-xl mb-5 w-fit">
            <button v-for="tab in tabs" :key="tab.key" :class="activeTab === tab.key
                ? 'bg-slate-700/70 shadow text-white'
                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'
                " class="px-4 py-2 rounded-lg text-sm font-medium transition-all flex items-center gap-1.5"
                @click="activeTab = tab.key">
                {{ tab.label }}
                <span :class="activeTab === tab.key
                    ? tab.activeClass
                    : 'bg-white/[0.08] text-slate-400'
                    " class="px-2 py-0.5 rounded-full text-xs font-bold tabular-nums">
                    {{ tab.count }}
                </span>
            </button>
        </div>

        <!-- Empty tab state -->
        <div v-if="tabItems.length === 0" class="text-center py-14 text-slate-500">
            <p class="text-xl mb-2">
                {{ activeTab === "new_followers" ? "🎉" : "✅" }}
            </p>
            <p class="font-medium text-slate-400">Nothing here</p>
            <p class="text-sm mt-1">
                {{
                    activeTab === "new_followers"
                        ? "No new followers since the last scan."
                        : "Nobody unfollowed you since the last scan."
                }}
            </p>
        </div>

        <!-- Follower grid -->
        <div v-else class="grid gap-3">
            <FollowerCard
                v-for="follower in tabItems"
                :key="follower.pk_id"
                :follower="follower"
                :profile-id="props.profileId"
            />
        </div>
    </div>
</template>
