<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from "vue";
import { RouterLink } from "vue-router";
import AutomationProfilePreviewCard from "../components/automation/AutomationProfilePreviewCard.vue";
import {
    cancelAutomationAction,
    confirmAutomationAction,
    getAutomationAction,
    prepareBatchFollow,
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
    AutomationPreviewItem,
} from "../types/automation";

const props = defineProps<{
    profileId: string;
    profileUsername?: string | null;
}>();

const emit = defineEmits<{
    backToAutomation: [];
}>();

const targetInput = ref("");
const doNotFollowInput = ref("");
const minProbability = ref(80);
const maxFollowCount = ref(40);
const includePrivateAccounts = ref(false);
const respectRecentInteractions = ref(true);

const placeholder = [
    "andrea.design",
    "https://www.instagram.com/sam.creates/",
    "57934512056",
].join("\n");

const doNotFollowPlaceholder = [
    "close_friend_alt",
    "https://www.instagram.com/brand_do_not_touch/",
    "client_account",
].join("\n");

function parseUniqueEntries(raw: string) {
    return Array.from(
        new Set(
            raw
                .split(/[\n,]/)
                .map((token) => token.trim())
                .filter(Boolean),
        ),
    );
}

const parsedTargets = computed(() => parseUniqueEntries(targetInput.value));
const doNotFollowAccounts = computed(() =>
    parseUniqueEntries(doNotFollowInput.value),
);

const estimatedSelected = computed(() => {
    const ratio = Math.min(
        Math.max((100 - minProbability.value) / 100, 0.08),
        0.35,
    );
    const candidateCount = Math.max(
        parsedTargets.value.length - doNotFollowAccounts.value.length,
        0,
    );
    return Math.min(maxFollowCount.value, Math.round(candidateCount * ratio));
});

// ── Action lifecycle ───────────────────────────────────────────────────

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

const hasCandidates = computed(() => parsedTargets.value.length > 0);
const hasConflictingAction = computed(
    () =>
        !!activeActionLock.value &&
        ["staged", "queued", "running"].includes(activeActionLock.value.status),
);

const prepareBlockReason = computed(() => {
    if (!activeActionLock.value || !hasConflictingAction.value) {
        return null;
    }
    return `Another batch follow action is already ${activeActionLock.value.status}. Action: ${activeActionLock.value.action_id}`;
});

const runningProgress = computed(() => {
    if (!currentAction.value || !currentAction.value.total_items) return 0;
    return Math.round(
        (currentAction.value.completed_items /
            currentAction.value.total_items) *
            100,
    );
});

const stagedPreviewItems = computed<AutomationPreviewItem[]>(() => {
    if (stagedResult.value?.selected_items?.length) {
        return stagedResult.value.selected_items;
    }
    return currentAction.value?.items_by_status?.pending ?? [];
});

const visibleStagedPreviewItems = computed(() =>
    stagedPreviewItems.value.slice(0, 10),
);

async function prepare() {
    if (!hasCandidates.value || hasConflictingAction.value) return;
    phase.value = "preparing";
    actionError.value = null;
    try {
        const result = await prepareBatchFollow({
            candidates: parsedTargets.value,
            do_not_follow: doNotFollowAccounts.value,
            max_follow_count: maxFollowCount.value,
            skip_private: !includePrivateAccounts.value,
            skip_no_recent_interaction: respectRecentInteractions.value,
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
                : "Failed to prepare batch follow";
        phase.value = "error";
    }
}

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
            actionError.value = action.error ?? "Action ended unexpectedly";
            phase.value = "error";
        } else {
            schedulePoll(actionId);
        }
    } catch {
        schedulePoll(actionId);
    }
}

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
            "batch_follow",
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

onMounted(() => {
    void recoverExistingAction();
});

onUnmounted(() => {
    if (pollTimeout) clearTimeout(pollTimeout);
});

function goBack() {
    emit("backToAutomation");
}
</script>

<template>
    <section class="space-y-6 fade-in">
        <header
            class="rounded-3xl border border-white/10 ibf-header p-6 md:p-8 relative overflow-hidden"
        >
            <div
                class="absolute right-4 top-4 h-32 w-32 rounded-full bg-cyan-400/20 blur-3xl pointer-events-none"
            />
            <div
                class="absolute left-8 bottom-0 h-24 w-24 rounded-full bg-orange-400/20 blur-2xl pointer-events-none"
            />

            <button
                class="btn-ghost rounded-lg px-3 py-1.5 text-xs mb-5 inline-flex items-center gap-1.5 relative z-10"
                @click="goBack"
            >
                ← Back to Automation
            </button>

            <div class="relative z-10">
                <p
                    class="text-xs uppercase tracking-[0.22em] text-cyan-100/90 font-semibold"
                >
                    Automation: Intelligent Batch Follow
                </p>
                <h2
                    class="text-2xl md:text-3xl font-display font-bold text-white mt-2"
                >
                    Build Your Follow Queue with Confidence
                </h2>
                <p
                    class="text-sm text-slate-100/85 mt-3 max-w-3xl leading-relaxed"
                >
                    The workflow will score each target and auto-select accounts
                    above the probability threshold. Selected users are staged
                    for a final <strong>Confirm Batch Follow</strong> action.
                </p>
                <p class="text-xs text-cyan-100/80 mt-4">
                    Active profile:
                    {{ props.profileUsername ? '@' + props.profileUsername : props.profileId }}
                </p>
            </div>
        </header>

        <!-- ⚠️ Rate-limit warning -->
        <div class="rounded-2xl border border-amber-400/40 bg-amber-400/10 p-5 shadow-lg shadow-amber-900/20">
            <div class="flex items-start gap-3">
                <span class="text-amber-300 text-xl leading-none mt-0.5 shrink-0" aria-hidden="true">⚠️</span>
                <div class="space-y-2 min-w-0">
                    <p class="text-sm font-semibold text-amber-200 leading-snug">
                        Instagram Rate Limit Warning — Read Before You Proceed
                    </p>
                    <p class="text-xs text-amber-100/90 leading-relaxed">
                        <strong>Do not bulk follow users on Instagram.</strong>
                        Doing so can trigger Instagram's spam detection and may lead to account restrictions.
                    </p>
                    <ul class="text-xs text-amber-100/80 space-y-1 list-disc list-inside">
                        <li><strong>Safe daily limit:</strong> 150 – 200 follow/unfollow actions (general accounts)</li>
                        <li><strong>New accounts:</strong> Stay under 100 actions/day for the first few weeks</li>
                        <li>Spread your actions <strong>gradually throughout the day</strong> to avoid detection</li>
                    </ul>
                    <p class="text-xs text-amber-100/80 leading-relaxed">
                        Exceeding the limit may result in a temporary action block, a shadowban, or permanent account disable.
                    </p>
                    <p class="text-[11px] text-amber-200/60 italic">
                        These limits are community-sourced and not officially confirmed by Instagram.
                    </p>
                    <RouterLink
                        to="/admin"
                        class="inline-flex items-center gap-1 text-xs font-medium text-amber-300 hover:text-amber-100 underline underline-offset-2 transition-colors"
                    >
                        📊 Monitor your API usage in Admin → Account Details → API Usage
                    </RouterLink>
                </div>
            </div>
        </div>

        <div class="grid xl:grid-cols-[1.15fr,0.85fr] gap-6">
            <section class="space-y-6">
                <div
                    class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30"
                >
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <h3 class="text-lg font-semibold text-slate-100">
                            Target Input
                        </h3>
                        <span
                            class="text-xs px-2.5 py-1 rounded-full border border-cyan-300/30 bg-cyan-300/10 text-cyan-200"
                        >
                            {{ parsedTargets.length }} unique targets
                        </span>
                    </div>

                    <p class="text-sm text-slate-400">
                        Paste usernames, profile links, or numeric user IDs. One
                        per line or comma-separated.
                    </p>
                    <p class="text-xs text-slate-500 mt-2">
                        Accepted formats: <strong>@username</strong>, full
                        Instagram profile link, or numeric ID.
                    </p>
                    <textarea
                        v-model="targetInput"
                        rows="10"
                        class="input-dark mt-4"
                        :placeholder="placeholder"
                    />
                </div>

                <div
                    class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30"
                >
                    <div class="flex items-center justify-between gap-3 mb-3">
                        <h3 class="text-lg font-semibold text-slate-100">
                            Do Not Follow List
                        </h3>
                        <span
                            class="text-xs px-2.5 py-1 rounded-full border border-amber-300/30 bg-amber-300/10 text-amber-200"
                        >
                            {{ doNotFollowAccounts.length }} excluded
                        </span>
                    </div>

                    <p class="text-sm text-slate-400">
                        Add accounts that must never be auto-selected for
                        follow, even if they pass the probability threshold. Use
                        either usernames or full Instagram profile links.
                    </p>
                    <p class="text-xs text-slate-500 mt-2">
                        Safekeeping entries can be pasted exactly as copied from
                        Instagram links.
                    </p>
                    <textarea
                        v-model="doNotFollowInput"
                        rows="7"
                        class="input-dark mt-4"
                        :placeholder="doNotFollowPlaceholder"
                    />
                </div>
            </section>

            <section
                class="rounded-2xl border border-white/10 bg-[#16213a]/95 p-5 md:p-6 shadow-2xl shadow-black/30"
            >
                <h3 class="text-lg font-semibold text-slate-100">
                    Selection Strategy
                </h3>
                <p class="text-sm text-slate-400 mt-1">
                    Configure auto-selection controls before follow execution.
                </p>

                <div class="space-y-5 mt-5">
                    <label class="block">
                        <span class="text-sm font-medium text-slate-200"
                            >Minimum Probability (%)</span
                        >
                        <div class="mt-2 flex items-center gap-3">
                            <input
                                v-model.number="minProbability"
                                type="range"
                                min="50"
                                max="95"
                                step="1"
                                class="w-full accent-cyan-400"
                            />
                            <span
                                class="w-12 text-right text-sm font-semibold text-cyan-300"
                                >{{ minProbability }}%</span
                            >
                        </div>
                    </label>

                    <label class="block">
                        <span class="text-sm font-medium text-slate-200"
                            >Max Users Per Batch</span
                        >
                        <input
                            v-model.number="maxFollowCount"
                            type="number"
                            min="1"
                            max="500"
                            class="input-dark mt-2"
                        />
                    </label>

                    <label
                        class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5"
                    >
                        <span class="text-sm text-slate-200"
                            >Include private accounts</span
                        >
                        <input
                            v-model="includePrivateAccounts"
                            type="checkbox"
                            class="h-4 w-4 accent-cyan-400"
                        />
                    </label>

                    <label
                        class="flex items-center justify-between rounded-xl border border-white/10 bg-white/[0.03] px-3 py-2.5"
                    >
                        <span class="text-sm text-slate-200"
                            >Respect recent interactions</span
                        >
                        <input
                            v-model="respectRecentInteractions"
                            type="checkbox"
                            class="h-4 w-4 accent-cyan-400"
                            :disabled="phase !== 'idle'"
                        />
                    </label>
                </div>

                <!-- Status / Preview panel -->
                <div
                    class="mt-6 rounded-xl ibf-summary border border-cyan-300/25 p-4"
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
                            class="text-xs uppercase tracking-wide text-cyan-100/80"
                        >
                            Preview
                        </p>
                        <p class="text-sm text-slate-100 mt-1">
                            Users scoring at least
                            <strong>{{ minProbability }}%</strong> will be
                            auto-selected for confirmation.
                        </p>
                        <p class="text-sm text-slate-300 mt-1">
                            Accounts excluded from follow:
                            <strong class="text-amber-200">{{
                                doNotFollowAccounts.length
                            }}</strong>
                        </p>
                        <p class="text-sm text-slate-300 mt-1">
                            Estimated selected:
                            <strong class="text-emerald-300">{{
                                estimatedSelected
                            }}</strong>
                            of {{ parsedTargets.length }} targets
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
                            <strong class="text-cyan-300">{{
                                stagedResult.selected_count
                            }}</strong>
                            accounts queued for follow
                        </p>
                        <p class="text-xs text-slate-400 mt-1">
                            {{ stagedResult.excluded_count }} excluded by
                            do-not-follow rules
                        </p>
                        <div
                            v-if="visibleStagedPreviewItems.length"
                            class="mt-3 grid gap-2"
                        >
                            <AutomationProfilePreviewCard
                                v-for="item in visibleStagedPreviewItems"
                                :key="item.raw_input"
                                :item="item"
                                :profile-id="props.profileId"
                            />
                            <p
                                v-if="stagedPreviewItems.length > 10"
                                class="text-xs text-slate-500"
                            >
                                …and
                                {{
                                    stagedPreviewItems.length - 10
                                }}
                                more
                            </p>
                        </div>
                    </template>

                    <template v-else-if="phase === 'staged' && currentAction">
                        <p
                            class="text-xs uppercase tracking-wide text-emerald-300/85"
                        >
                            ✓ Ready to Execute
                        </p>
                        <p class="text-sm text-slate-100 mt-2">
                            A previously prepared batch is staged on the server.
                        </p>
                        <p class="text-xs text-slate-400 mt-1">
                            Action ID: {{ currentAction.action_id }}
                        </p>
                        <p class="text-xs text-slate-400 mt-1">
                            Click <strong>Confirm &amp; Execute</strong> to continue,
                            or <strong>Cancel Staged Batch</strong> to unlock.
                        </p>
                        <div
                            v-if="visibleStagedPreviewItems.length"
                            class="mt-3 grid gap-2"
                        >
                            <AutomationProfilePreviewCard
                                v-for="(item, idx) in visibleStagedPreviewItems"
                                :key="`recovered-${idx}`"
                                :item="item"
                                :profile-id="props.profileId"
                            />
                            <p
                                v-if="stagedPreviewItems.length > 10"
                                class="text-xs text-slate-500"
                            >
                                …and {{ stagedPreviewItems.length - 10 }} more
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
                                <strong class="text-cyan-300">{{
                                    currentAction.completed_items
                                }}</strong>
                                / {{ currentAction.total_items }} followed
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
                                    class="h-full bg-cyan-500 transition-all duration-700"
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
                            accounts followed
                        </p>
                        <p
                            v-if="currentAction.failed_items"
                            class="text-xs text-amber-300 mt-1"
                        >
                            {{ currentAction.failed_items }} could not be
                            followed
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
                            class="btn-violet rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2"
                            :class="{
                                'opacity-50 cursor-not-allowed': !hasCandidates || hasConflictingAction,
                            }"
                            :disabled="!hasCandidates || hasConflictingAction"
                            @click="prepare"
                        >
                            Prepare Batch Follow
                        </button>
                    </template>

                    <!-- Preparing -->
                    <template v-else-if="phase === 'preparing'">
                        <button
                            class="btn-violet rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2 opacity-60 cursor-not-allowed"
                            disabled
                        >
                            Preparing…
                        </button>
                    </template>

                    <!-- Staged -->
                    <template v-else-if="phase === 'staged'">
                        <button
                            class="btn-violet rounded-xl px-4 py-2.5 text-sm font-semibold"
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
                            class="btn-violet rounded-xl px-4 py-2.5 text-sm font-semibold col-span-2 opacity-60 cursor-not-allowed"
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
.ibf-header {
    background:
        linear-gradient(
            125deg,
            rgba(12, 38, 74, 0.95) 0%,
            rgba(7, 70, 76, 0.9) 54%,
            rgba(83, 52, 22, 0.82) 100%
        ),
        radial-gradient(
            circle at 20% 22%,
            rgba(56, 189, 248, 0.24),
            transparent 36%
        ),
        radial-gradient(
            circle at 84% 66%,
            rgba(251, 191, 36, 0.2),
            transparent 40%
        );
}

.ibf-summary {
    background: linear-gradient(
        135deg,
        rgba(14, 56, 84, 0.55) 0%,
        rgba(18, 82, 77, 0.38) 100%
    );
    box-shadow: inset 0 0 0 1px rgba(125, 211, 252, 0.12);
}
</style>
