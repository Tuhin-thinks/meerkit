<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import {
    cancelAutomationAction,
    confirmAutomationAction,
    getAutomationAction,
    getAutomationFollowingUsers,
    prepareBatchUnfollow,
} from "../services/api";
import {
    clearAutomationJob,
    recoverAutomationJobForType,
    registerAutomationJob,
    updateAutomationJob,
} from "../services/automationJobRegistry";
import type {
    AutomationAction,
    AutomationActionResult,
    FollowingUser,
} from "../types/automation";

const props = defineProps<{
    profileId: string;
}>();

const emit = defineEmits<{
    backToAutomation: [];
}>();

// ── Candidate input mode ───────────────────────────────────────────────

type CandidateMode = "paste" | "browse";
const candidateMode = ref<CandidateMode>("paste");

// Paste mode
const pasteInput = ref("");

// Browse mode
const followingList = ref<FollowingUser[]>([]);
const followingSearch = ref("");
const selectedUserIds = ref<string[]>([]);
const followingLoading = ref(false);
const followingError = ref<string | null>(null);
const followingLoaded = ref(false);
const showOnlyNotFollowingBack = ref(false);
const followingTotals = ref({ followersTotal: 0, followingTotal: 0 });
type SortMetric = "follower_count" | "following_count";
type SortOrder = "asc" | "desc";
const sortMetric = ref<SortMetric>("follower_count");
const sortOrder = ref<SortOrder>("desc");

// ── Never-unfollow list ────────────────────────────────────────────────

const protectedAccountsInput = ref("");

// ── Guardrail settings ─────────────────────────────────────────────────

const maxUnfollowCount = ref(50);
const requireMutualHistoryCheck = ref(true);
const skipRecentFollows = ref(true);

// ── Prepare / action lifecycle ─────────────────────────────────────────

type Phase =
    | "idle"
    | "preparing"
    | "staged"
    | "confirming"
    | "running"
    | "completed"
    | "error";

const phase = ref<Phase>("idle");
const stagedResult = ref<AutomationActionResult | null>(null);
const currentAction = ref<AutomationAction | null>(null);
const activeActionLock = ref<AutomationAction | null>(null);
const actionError = ref<string | null>(null);
let pollTimeout: ReturnType<typeof setTimeout> | null = null;

// ── Computed ───────────────────────────────────────────────────────────

const filteredFollowingList = computed(() => {
    const q = followingSearch.value.trim().toLowerCase();
    const filtered = followingList.value.filter(
        (u) =>
            (!showOnlyNotFollowingBack.value || !u.follows_you) &&
            (!q ||
                u.username.toLowerCase().includes(q) ||
                u.full_name.toLowerCase().includes(q)),
    );

    const metric = sortMetric.value;
    const multiplier = sortOrder.value === "asc" ? 1 : -1;

    return [...filtered].sort((a, b) => {
        const aMetric = a[metric];
        const bMetric = b[metric];
        const aVal = typeof aMetric === "number" ? aMetric : null;
        const bVal = typeof bMetric === "number" ? bMetric : null;

        if (aVal === null && bVal === null) {
            return a.username.localeCompare(b.username);
        }
        if (aVal === null) {
            return 1;
        }
        if (bVal === null) {
            return -1;
        }

        if (aVal === bVal) {
            return a.username.localeCompare(b.username);
        }
        return (aVal - bVal) * multiplier;
    });
});

const notFollowingBackCount = computed(
    () => followingList.value.filter((u) => !u.follows_you).length,
);

function parseUniqueEntries(raw: string) {
    return Array.from(
        new Set(
            raw
                .split(/[\n,]/)
                .map((t) => t.trim())
                .filter(Boolean),
        ),
    );
}

const activeCandidates = computed((): string[] => {
    if (candidateMode.value === "paste") {
        return parseUniqueEntries(pasteInput.value);
    }
    const idToUsername = new Map(
        followingList.value.map((u) => [u.user_id, u.username]),
    );
    return selectedUserIds.value
        .map((id) => idToUsername.get(id))
        .filter((u): u is string => !!u);
});

const protectedAccounts = computed(() =>
    parseUniqueEntries(protectedAccountsInput.value),
);

const hasCandidates = computed(() => activeCandidates.value.length > 0);
const hasConflictingAction = computed(
    () =>
        !!activeActionLock.value &&
        ["staged", "queued", "running"].includes(activeActionLock.value.status),
);

const prepareBlockReason = computed(() => {
    if (!activeActionLock.value || !hasConflictingAction.value) {
        return null;
    }
    return `Another batch unfollow action is already ${activeActionLock.value.status}. Action: ${activeActionLock.value.action_id}`;
});

const isAllFilteredSelected = computed(() => {
    if (!filteredFollowingList.value.length) return false;
    const sel = new Set(selectedUserIds.value);
    return filteredFollowingList.value.every((u) => sel.has(u.user_id));
});

const estimatedUnfollow = computed(() => {
    const candidateCount = Math.max(
        activeCandidates.value.length - protectedAccounts.value.length,
        0,
    );
    return Math.min(candidateCount, maxUnfollowCount.value);
});

const runningProgress = computed(() => {
    if (!currentAction.value || !currentAction.value.total_items) return 0;
    return Math.round(
        (currentAction.value.completed_items /
            currentAction.value.total_items) *
            100,
    );
});

// ── Browse mode methods ────────────────────────────────────────────────

async function loadFollowingList() {
    followingLoading.value = true;
    followingError.value = null;
    try {
        const res = await getAutomationFollowingUsers();
        followingList.value = res.users;
        followingTotals.value = {
            followersTotal: res.followers_total,
            followingTotal: res.following_total,
        };
        followingLoaded.value = true;
    } catch (err: unknown) {
        followingError.value =
            err instanceof Error
                ? err.message
                : "Failed to load following list";
    } finally {
        followingLoading.value = false;
    }
}

function openInstagramProfile(username: string) {
    window.open(`https://www.instagram.com/${username}/`, "_blank", "noopener,noreferrer");
}

function toggleSelectAll() {
    if (isAllFilteredSelected.value) {
        const filteredIds = new Set(
            filteredFollowingList.value.map((u) => u.user_id),
        );
        selectedUserIds.value = selectedUserIds.value.filter(
            (id) => !filteredIds.has(id),
        );
    } else {
        const sel = new Set(selectedUserIds.value);
        filteredFollowingList.value.forEach((u) => sel.add(u.user_id));
        selectedUserIds.value = Array.from(sel);
    }
}

// ── Prepare ────────────────────────────────────────────────────────────

async function prepare() {
    if (!hasCandidates.value || hasConflictingAction.value) return;
    phase.value = "preparing";
    actionError.value = null;
    try {
        const result = await prepareBatchUnfollow({
            candidates: activeCandidates.value,
            never_unfollow: protectedAccounts.value,
            max_unfollow_count: maxUnfollowCount.value,
            skip_mutual: requireMutualHistoryCheck.value,
            skip_recent: skipRecentFollows.value,
        });
        const action = await getAutomationAction(result.action_id);
        registerAutomationJob(action);
        activeActionLock.value = action;
        stagedResult.value = result;
        phase.value = "staged";
    } catch (err: unknown) {
        actionError.value =
            err instanceof Error
                ? err.message
                : "Failed to prepare batch unfollow";
        phase.value = "error";
    }
}

// ── Confirm ────────────────────────────────────────────────────────────

async function confirm() {
    if (!stagedResult.value) return;
    phase.value = "confirming";
    actionError.value = null;
    try {
        const action = await confirmAutomationAction(stagedResult.value.action_id);
        registerAutomationJob(action);
        activeActionLock.value = action;
        currentAction.value = action;
        phase.value = "running";
        schedulePoll(action.action_id);
    } catch (err: unknown) {
        actionError.value =
            err instanceof Error ? err.message : "Failed to confirm action";
        phase.value = "error";
    }
}

// ── Polling ────────────────────────────────────────────────────────────

function schedulePoll(actionId: string) {
    if (pollTimeout) clearTimeout(pollTimeout);
    pollTimeout = setTimeout(() => poll(actionId), 2500);
}

async function poll(actionId: string) {
    try {
        const action = await getAutomationAction(actionId);
        currentAction.value = action;

        if (["staged", "queued", "running"].includes(action.status)) {
            updateAutomationJob(action.action_id, action.status);
            activeActionLock.value = action;
        }

        if (action.status === "completed" || action.status === "partial") {
            clearAutomationJob(action.action_id);
            if (activeActionLock.value?.action_id === action.action_id) {
                activeActionLock.value = null;
            }
            phase.value = "completed";
        } else if (
            action.status === "error" ||
            action.status === "cancelled"
        ) {
            clearAutomationJob(action.action_id);
            if (activeActionLock.value?.action_id === action.action_id) {
                activeActionLock.value = null;
            }
            actionError.value =
                action.error ?? "Action ended unexpectedly";
            phase.value = "error";
        } else {
            schedulePoll(actionId);
        }
    } catch {
        schedulePoll(actionId);
    }
}

// ── Cancel ─────────────────────────────────────────────────────────────

async function cancel() {
    const actionId =
        stagedResult.value?.action_id ?? currentAction.value?.action_id;
    if (!actionId) return;
    if (pollTimeout) {
        clearTimeout(pollTimeout);
        pollTimeout = null;
    }
    try {
        await cancelAutomationAction(actionId);
    } catch {
        // best-effort
    }
    clearAutomationJob(actionId);
    if (activeActionLock.value?.action_id === actionId) {
        activeActionLock.value = null;
    }
    reset();
}

// ── Reset ──────────────────────────────────────────────────────────────

function reset() {
    if (pollTimeout) {
        clearTimeout(pollTimeout);
        pollTimeout = null;
    }
    phase.value = "idle";
    stagedResult.value = null;
    currentAction.value = null;
    actionError.value = null;
}

async function recoverExistingAction() {
    try {
        const action = await recoverAutomationJobForType(
            props.profileId,
            "batch_unfollow",
        );
        if (!action) {
            return;
        }

        activeActionLock.value = action;
        currentAction.value = action;
        if (action.status === "queued" || action.status === "running") {
            phase.value = "running";
            schedulePoll(action.action_id);
        }
    } catch {
        // Keep UI interactive on transient backend errors.
    }
}

onUnmounted(() => {
    if (pollTimeout) clearTimeout(pollTimeout);
});

onMounted(async () => {
    await recoverExistingAction();
});

function goBack() {
    emit("backToAutomation");
}

const pastePlaceholder = [
    "old_brand_collab",
    "https://www.instagram.com/archive.second/",
    "62841752014",
].join("\n");

const protectedPlaceholder = [
    "best_friend_main",
    "https://www.instagram.com/best_friend_backup/",
    "team_account",
].join("\n");
</script>

<template>
    <section class="space-y-6 fade-in">
        <!-- Header -->
        <header
            class="rounded-3xl border border-white/10 buf-header p-6 md:p-8 relative overflow-hidden"
        >
            <div
                class="absolute right-2 top-8 h-40 w-40 rounded-full bg-rose-400/20 blur-3xl pointer-events-none"
            />
            <div
                class="absolute left-10 bottom-0 h-24 w-28 rounded-full bg-amber-400/20 blur-2xl pointer-events-none"
            />

            <button
                class="btn-ghost rounded-lg px-3 py-1.5 text-xs mb-5 inline-flex items-center gap-1.5 relative z-10"
                @click="goBack"
            >
                ← Back to Automation
            </button>

            <div class="relative z-10">
                <p
                    class="text-xs uppercase tracking-[0.22em] text-rose-100/90 font-semibold"
                >
                    Automation: Batch Unfollow
                </p>
                <h2
                    class="text-2xl md:text-3xl font-display font-bold text-white mt-2"
                >
                    Clear Non-Reciprocal Accounts Without Touching Protected
                    Ones
                </h2>
                <p
                    class="text-sm text-slate-100/85 mt-3 max-w-3xl leading-relaxed"
                >
                    Prepare an unfollow queue from accounts that do not follow
                    back, then confirm before execution. Protected accounts are
                    never included even if they match the unfollow logic.
                </p>
                <p class="text-xs text-rose-100/80 mt-4">
                    Active profile: {{ props.profileId }}
                </p>
            </div>
        </header>

        <div class="grid xl:grid-cols-[1.25fr,0.75fr] gap-6">
            <!-- Left: Inputs -->
            <section class="space-y-6">
                <!-- Unfollow Candidates -->
                <div
                    class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30"
                >
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <h3 class="text-lg font-semibold text-slate-100">
                            Unfollow Candidates
                        </h3>
                        <span
                            class="text-xs px-2.5 py-1 rounded-full border border-rose-300/30 bg-rose-300/10 text-rose-200"
                        >
                            {{ activeCandidates.length }} queued
                        </span>
                    </div>

                    <!-- Mode tab switcher -->
                    <div
                        class="flex gap-1 p-1 rounded-xl bg-white/5 border border-white/10 mb-4"
                    >
                        <button
                            class="flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
                            :class="
                                candidateMode === 'paste'
                                    ? 'bg-rose-500/30 text-rose-200 border border-rose-400/30'
                                    : 'text-slate-400 hover:text-slate-200'
                            "
                            @click="candidateMode = 'paste'"
                        >
                            Paste List
                        </button>
                        <button
                            class="flex-1 rounded-lg px-3 py-1.5 text-xs font-medium transition-all"
                            :class="
                                candidateMode === 'browse'
                                    ? 'bg-rose-500/30 text-rose-200 border border-rose-400/30'
                                    : 'text-slate-400 hover:text-slate-200'
                            "
                            @click="candidateMode = 'browse'"
                        >
                            Browse Following
                        </button>
                    </div>

                    <!-- Paste mode -->
                    <div v-if="candidateMode === 'paste'">
                        <p class="text-sm text-slate-400">
                            Paste usernames, links, or IDs to queue for the
                            not-following-back check.
                        </p>
                        <p class="text-xs text-slate-500 mt-2">
                            Accepted formats:
                            <strong>@username</strong>, full Instagram profile
                            link, or numeric ID.
                        </p>
                        <textarea
                            v-model="pasteInput"
                            rows="10"
                            class="input-dark mt-4"
                            :placeholder="pastePlaceholder"
                            :disabled="phase !== 'idle'"
                        />
                    </div>

                    <!-- Browse mode -->
                    <div v-else class="space-y-3">
                        <!-- Load button -->
                        <div class="flex items-center gap-3 flex-wrap">
                            <button
                                class="btn-ghost rounded-lg px-4 py-2 text-sm font-medium"
                                :disabled="followingLoading"
                                @click="loadFollowingList"
                            >
                                <span v-if="followingLoading">Loading…</span>
                                <span v-else-if="followingLoaded"
                                    >↺ Refresh</span
                                >
                                <span v-else>Load Current Following</span>
                            </button>
                            <span
                                v-if="followingLoaded"
                                class="text-xs text-slate-400"
                            >
                                {{ followingTotals.followingTotal || followingList.length }} following • {{ followingTotals.followersTotal }} followers
                            </span>
                        </div>

                        <p
                            v-if="followingError"
                            class="text-xs text-rose-300 rounded-lg bg-rose-500/10 px-3 py-2 border border-rose-400/20"
                        >
                            {{ followingError }}
                        </p>

                        <!-- Controls & list (shown after load) -->
                        <template
                            v-if="followingLoaded && followingList.length"
                        >
                            <!-- Search -->
                            <div class="grid gap-2 md:grid-cols-3">
                                <input
                                    v-model="followingSearch"
                                    type="text"
                                    class="input-dark md:col-span-2"
                                    placeholder="Search by username or name…"
                                />
                                <div class="grid grid-cols-2 gap-2">
                                    <select
                                        v-model="sortMetric"
                                        class="input-dark-select text-xs"
                                    >
                                        <option value="follower_count">Sort: Their Followers</option>
                                        <option value="following_count">Sort: Their Following</option>
                                    </select>
                                    <select
                                        v-model="sortOrder"
                                        class="input-dark-select text-xs"
                                    >
                                        <option value="desc">High → Low</option>
                                        <option value="asc">Low → High</option>
                                    </select>
                                </div>
                            </div>

                            <label
                                class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5 gap-3"
                            >
                                <div>
                                    <p class="text-sm text-slate-200">
                                        Only show accounts not in my followers
                                    </p>
                                    <p class="text-xs text-slate-500 mt-1">
                                        {{ notFollowingBackCount }} of {{ followingList.length }} accounts do not follow you back.
                                    </p>
                                </div>
                                <input
                                    v-model="showOnlyNotFollowingBack"
                                    type="checkbox"
                                    class="h-4 w-4 rounded accent-rose-400"
                                />
                            </label>

                            <!-- Select all / deselect all row -->
                            <div
                                class="flex items-center justify-between gap-2"
                            >
                                <button
                                    class="rounded-lg px-3 py-1.5 text-xs font-medium border transition-colors"
                                    :class="
                                        isAllFilteredSelected
                                            ? 'border-rose-400/40 bg-rose-400/15 text-rose-200 hover:bg-rose-400/25'
                                            : 'border-white/10 bg-white/5 text-slate-300 hover:bg-white/10'
                                    "
                                    @click="toggleSelectAll"
                                >
                                    {{
                                        isAllFilteredSelected
                                            ? "Deselect All"
                                            : `Select All (${filteredFollowingList.length})`
                                    }}
                                </button>
                                <span class="text-xs text-slate-400">
                                    {{ selectedUserIds.length }} /
                                    {{ followingList.length }} selected
                                </span>
                            </div>

                            <!-- Scrollable user list -->
                            <div
                                class="max-h-[560px] overflow-y-auto rounded-xl border border-white/10 divide-y divide-white/5"
                            >
                                <label
                                    v-for="user in filteredFollowingList"
                                    :key="user.user_id"
                                    class="flex items-start gap-3 px-3 py-2.5 cursor-pointer hover:bg-white/5 transition-colors"
                                >
                                    <input
                                        type="checkbox"
                                        :value="user.user_id"
                                        v-model="selectedUserIds"
                                        class="h-4 w-4 rounded accent-rose-400 flex-shrink-0"
                                    />
                                    <div class="min-w-0 flex-1">
                                        <div
                                            class="flex items-center gap-1.5"
                                        >
                                            <span
                                                class="text-sm font-medium text-slate-100 truncate"
                                                >@{{ user.username }}</span
                                            >
                                            <span
                                                v-if="user.is_private"
                                                class="text-[10px] px-1.5 py-0.5 rounded-full bg-slate-600/50 text-slate-300 border border-slate-500/30 flex-shrink-0"
                                                >Private</span
                                            >
                                        </div>
                                        <p
                                            v-if="user.full_name"
                                            class="text-xs text-slate-500 truncate mt-0.5"
                                        >
                                            {{ user.full_name }}
                                        </p>
                                        <div
                                            class="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-300"
                                        >
                                            <span
                                                class="rounded-full border border-white/10 bg-white/5 px-2 py-1"
                                            >
                                                Followers: {{ user.follower_count ?? "--" }}
                                            </span>
                                            <span
                                                class="rounded-full border border-white/10 bg-white/5 px-2 py-1"
                                            >
                                                Following: {{ user.following_count ?? "--" }}
                                            </span>
                                            <span
                                                :class="user.follows_you ? 'border-emerald-400/30 bg-emerald-400/10 text-emerald-200' : 'border-amber-400/30 bg-amber-400/10 text-amber-200'"
                                                class="rounded-full border px-2 py-1"
                                            >
                                                {{ user.follows_you ? "Follows you" : "Not in followers" }}
                                            </span>
                                        </div>
                                    </div>
                                    <button
                                        type="button"
                                        class="btn-ghost rounded-lg px-3 py-1.5 text-xs font-medium self-center"
                                        @click.prevent="openInstagramProfile(user.username)"
                                    >
                                        View
                                    </button>
                                </label>

                                <p
                                    v-if="!filteredFollowingList.length"
                                    class="text-sm text-slate-500 text-center py-6"
                                >
                                    No accounts match your search.
                                </p>
                            </div>
                        </template>

                        <p
                            v-else-if="!followingLoaded && !followingLoading"
                            class="text-sm text-slate-500"
                        >
                            Click
                            <strong class="text-slate-300"
                                >Load Current Following</strong
                            >
                            to fetch your following list from Instagram.
                        </p>
                    </div>
                </div>

                <!-- Never Unfollow List -->
                <div
                    class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30"
                >
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <h3 class="text-lg font-semibold text-slate-100">
                            Never Unfollow List
                        </h3>
                        <span
                            class="text-xs px-2.5 py-1 rounded-full border border-amber-300/30 bg-amber-300/10 text-amber-200"
                        >
                            {{ protectedAccounts.length }} protected
                        </span>
                    </div>
                    <p class="text-sm text-slate-400">
                        Accounts listed here are always excluded, even if they
                        appear in your unfollow candidates.
                    </p>
                    <p class="text-xs text-slate-500 mt-2">
                        Accepted formats: <strong>@username</strong>, full
                        Instagram profile link, or numeric ID.
                    </p>
                    <textarea
                        v-model="protectedAccountsInput"
                        rows="6"
                        class="input-dark mt-4"
                        :placeholder="protectedPlaceholder"
                        :disabled="phase !== 'idle'"
                    />
                </div>
            </section>

            <!-- Right: Controls + Status -->
            <section
                class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30 self-start"
            >
                <h3 class="text-lg font-semibold text-slate-100">
                    Guardrails & Execution
                </h3>
                <p class="text-sm text-slate-400 mt-1">
                    Tune the queue, then confirm before execution starts in the
                    background.
                </p>

                <div class="space-y-5 mt-5">
                    <label class="block">
                        <span class="text-sm font-medium text-slate-200"
                            >Max Users Per Batch</span
                        >
                        <input
                            v-model.number="maxUnfollowCount"
                            type="number"
                            min="1"
                            max="500"
                            class="input-dark mt-2"
                            :disabled="phase !== 'idle'"
                        />
                    </label>

                    <label
                        class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5"
                    >
                        <span class="text-sm text-slate-200"
                            >Require mutual-history check</span
                        >
                        <input
                            v-model="requireMutualHistoryCheck"
                            type="checkbox"
                            class="h-4 w-4 accent-rose-400"
                            :disabled="phase !== 'idle'"
                        />
                    </label>

                    <label
                        class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5"
                    >
                        <span class="text-sm text-slate-200"
                            >Skip recently followed accounts</span
                        >
                        <input
                            v-model="skipRecentFollows"
                            type="checkbox"
                            class="h-4 w-4 accent-rose-400"
                            :disabled="phase !== 'idle'"
                        />
                    </label>
                </div>

                <!-- Status / Preview panel -->
                <div
                    class="mt-6 rounded-xl buf-summary border border-rose-300/25 p-4"
                >
                    <!-- Idle -->
                    <template v-if="phase === 'idle'">
                        <p
                            v-if="prepareBlockReason"
                            class="text-xs text-amber-200 rounded-lg bg-amber-500/10 border border-amber-300/25 px-3 py-2 mb-3"
                        >
                            {{ prepareBlockReason }}
                        </p>
                        <p
                            class="text-xs uppercase tracking-wide text-rose-100/85"
                        >
                            Preview
                        </p>
                        <p class="text-sm text-slate-100 mt-1">
                            Accounts detected as
                            <strong>not following back</strong> will be staged
                            for confirmation.
                        </p>
                        <p class="text-sm text-slate-300 mt-1">
                            Protected accounts:
                            <strong class="text-amber-200">{{
                                protectedAccounts.length
                            }}</strong>
                        </p>
                        <p class="text-sm text-slate-300 mt-1">
                            Estimated ready to unfollow:
                            <strong class="text-rose-200">{{
                                estimatedUnfollow
                            }}</strong>
                            of {{ activeCandidates.length }} candidates
                        </p>
                    </template>

                    <!-- Preparing -->
                    <template v-else-if="phase === 'preparing'">
                        <p
                            class="text-xs uppercase tracking-wide text-slate-300/80"
                        >
                            Preparing…
                        </p>
                        <p
                            class="text-sm text-slate-300 mt-2 animate-pulse"
                        >
                            Normalising candidates and applying exclusion
                            rules…
                        </p>
                    </template>

                    <!-- Staged -->
                    <template v-else-if="phase === 'staged' && stagedResult">
                        <p
                            class="text-xs uppercase tracking-wide text-emerald-300/85"
                        >
                            ✓ Ready to Execute
                        </p>
                        <p class="text-sm text-slate-100 mt-2">
                            <strong class="text-rose-200">{{
                                stagedResult.selected_count
                            }}</strong>
                            accounts queued for unfollow
                        </p>
                        <p class="text-xs text-slate-400 mt-1">
                            {{ stagedResult.excluded_count }} excluded by
                            safelist rules
                        </p>
                        <div
                            v-if="stagedResult.selected_items.length"
                            class="mt-3 max-h-32 overflow-y-auto space-y-1"
                        >
                            <p
                                v-for="item in stagedResult.selected_items.slice(
                                    0,
                                    10,
                                )"
                                :key="item.raw_input"
                                class="text-xs text-slate-300"
                            >
                                @{{
                                    item.display_username ?? item.raw_input
                                }}
                            </p>
                            <p
                                v-if="stagedResult.selected_items.length > 10"
                                class="text-xs text-slate-500"
                            >
                                …and
                                {{
                                    stagedResult.selected_items.length - 10
                                }}
                                more
                            </p>
                        </div>
                    </template>

                    <!-- Confirming -->
                    <template v-else-if="phase === 'confirming'">
                        <p
                            class="text-xs uppercase tracking-wide text-slate-300/80"
                        >
                            Queueing…
                        </p>
                        <p
                            class="text-sm text-slate-300 mt-2 animate-pulse"
                        >
                            Sending action to background worker…
                        </p>
                    </template>

                    <!-- Running -->
                    <template v-else-if="phase === 'running'">
                        <p
                            class="text-xs uppercase tracking-wide text-cyan-300/85"
                        >
                            Running
                        </p>
                        <template v-if="currentAction">
                            <p class="text-sm text-slate-100 mt-2">
                                <strong class="text-rose-200">{{
                                    currentAction.completed_items
                                }}</strong>
                                / {{ currentAction.total_items }} unfollowed
                            </p>
                            <p
                                v-if="currentAction.failed_items"
                                class="text-xs text-amber-300 mt-1"
                            >
                                {{ currentAction.failed_items }} failed
                            </p>
                            <div
                                class="mt-3 h-1.5 rounded-full bg-white/10 overflow-hidden"
                            >
                                <div
                                    class="h-full bg-rose-500 transition-all duration-700"
                                    :style="{
                                        width: `${runningProgress}%`,
                                    }"
                                />
                            </div>
                        </template>
                        <p
                            v-else
                            class="text-sm text-slate-300 mt-2 animate-pulse"
                        >
                            Waiting for worker…
                        </p>
                    </template>

                    <!-- Completed -->
                    <template
                        v-else-if="phase === 'completed' && currentAction"
                    >
                        <p
                            class="text-xs uppercase tracking-wide text-emerald-300/85"
                        >
                            ✓ Completed
                        </p>
                        <p class="text-sm text-slate-100 mt-2">
                            <strong class="text-emerald-300">{{
                                currentAction.completed_items
                            }}</strong>
                            accounts unfollowed
                        </p>
                        <p
                            v-if="currentAction.failed_items"
                            class="text-xs text-amber-300 mt-1"
                        >
                            {{ currentAction.failed_items }} could not be
                            unfollowed
                        </p>
                        <p
                            v-if="currentAction.skipped_items"
                            class="text-xs text-slate-400 mt-1"
                        >
                            {{ currentAction.skipped_items }} skipped
                        </p>
                    </template>

                    <!-- Error -->
                    <template v-else-if="phase === 'error'">
                        <p
                            class="text-xs uppercase tracking-wide text-rose-300/85"
                        >
                            Error
                        </p>
                        <p class="text-sm text-rose-200 mt-2">
                            {{
                                actionError ?? "An unexpected error occurred."
                            }}
                        </p>
                    </template>
                </div>

                <!-- Action buttons -->
                <div class="mt-6 grid sm:grid-cols-2 gap-3">
                    <!-- Idle -->
                    <template v-if="phase === 'idle'">
                        <button
                            class="btn-danger rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2"
                            :class="{
                                'opacity-50 cursor-not-allowed': !hasCandidates || hasConflictingAction,
                            }"
                            :disabled="!hasCandidates || hasConflictingAction"
                            @click="prepare"
                        >
                            Prepare Batch Unfollow
                        </button>
                    </template>

                    <!-- Preparing -->
                    <template v-else-if="phase === 'preparing'">
                        <button
                            class="btn-danger rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2 opacity-60 cursor-not-allowed"
                            disabled
                        >
                            Preparing…
                        </button>
                    </template>

                    <!-- Staged -->
                    <template v-else-if="phase === 'staged'">
                        <button
                            class="btn-danger rounded-xl px-4 py-2.5 text-sm font-semibold"
                            :class="{
                                'opacity-50 cursor-not-allowed':
                                    !stagedResult?.selected_count,
                            }"
                            :disabled="!stagedResult?.selected_count"
                            @click="confirm"
                        >
                            Confirm &amp; Execute
                        </button>
                        <button
                            class="btn-ghost rounded-xl px-4 py-2.5 text-sm font-semibold"
                            @click="reset"
                        >
                            Start Over
                        </button>
                    </template>

                    <!-- Confirming -->
                    <template v-else-if="phase === 'confirming'">
                        <button
                            class="btn-danger rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2 opacity-60 cursor-not-allowed"
                            disabled
                        >
                            Queueing…
                        </button>
                    </template>

                    <!-- Running -->
                    <template v-else-if="phase === 'running'">
                        <button
                            class="btn-ghost rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2"
                            @click="cancel"
                        >
                            Cancel
                        </button>
                    </template>

                    <!-- Completed or Error -->
                    <template v-else>
                        <button
                            class="btn-ghost rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2"
                            @click="reset"
                        >
                            Start Over
                        </button>
                    </template>
                </div>
            </section>
        </div>
    </section>
</template>

<style scoped>
.buf-header {
    background:
        linear-gradient(
            125deg,
            rgba(68, 24, 41, 0.95) 0%,
            rgba(98, 31, 63, 0.9) 52%,
            rgba(102, 49, 20, 0.84) 100%
        ),
        radial-gradient(
            circle at 20% 22%,
            rgba(251, 113, 133, 0.24),
            transparent 36%
        ),
        radial-gradient(
            circle at 82% 68%,
            rgba(251, 191, 36, 0.18),
            transparent 38%
        );
}

.buf-summary {
    background: linear-gradient(
        135deg,
        rgba(95, 29, 55, 0.55) 0%,
        rgba(120, 53, 15, 0.28) 100%
    );
    box-shadow: inset 0 0 0 1px rgba(253, 164, 175, 0.12);
}
</style>
