<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import ProfilePicture from "../components/ProfilePicture.vue";
import PredictionStatePanel from "../components/prediction/PredictionStatePanel.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import type {
    PredictionDetailResponse,
    PredictionFeedbackPayload,
    PredictionRecord,
    PredictionTask,
    RelationshipCacheStatusResponse,
} from "../types/prediction";

const props = defineProps<{
    profileId: string;
    initialUsername?: string;
}>();

const route = useRoute();
const router = useRouter();

const usernameInput = ref(props.initialUsername ?? "");
const prediction = ref<PredictionRecord | null>(null);
const currentTask = ref<PredictionTask | null>(null);
const relationshipCache = ref<RelationshipCacheStatusResponse | null>(null);
const statusMessage = ref("");
const isLoading = ref(false);
const errorMessage = ref("");
const listRefreshPending = ref({
    followers: false,
    following: false,
});
const listRefreshError = ref({
    followers: "",
    following: "",
});

const feedbackMode = ref<"correct" | "wrong" | null>(null);
const feedbackDirection = ref<"higher" | "lower" | null>(null);
const feedbackExpectedPct = ref("");
const feedbackNotes = ref("");
const feedbackSubmitting = ref(false);
const feedbackReassessing = ref(false);

let disposed = false;

onBeforeUnmount(() => {
    disposed = true;
});

watch(
    () => props.initialUsername,
    (value) => {
        usernameInput.value = value ?? "";
        if (value) {
            void loadPrediction(value);
        }
    },
    { immediate: true },
);

const probabilityLabel = computed(() => {
    if (!prediction.value?.probability && prediction.value?.probability !== 0) {
        return "--";
    }
    return `${Math.round(prediction.value.probability * 100)}%`;
});

const confidenceLabel = computed(() => {
    if (!prediction.value?.confidence && prediction.value?.confidence !== 0) {
        return "--";
    }
    return `${Math.round(prediction.value.confidence * 100)}%`;
});

const reasons = computed(() => {
    const payload = prediction.value?.result_payload as {
        reasons?: string[];
    } | null;
    return payload?.reasons ?? [];
});

const targetProfile = computed(() => {
    const payload = prediction.value?.result_payload as {
        target_profile?: Record<string, unknown>;
    } | null;
    return payload?.target_profile ?? null;
});

const ambiguousProbability = computed(() => {
    const payload = prediction.value?.result_payload as {
        ambiguous_probability?: boolean;
    } | null;
    return payload?.ambiguous_probability ?? false;
});

const canFetchOverlap = computed(() => {
    const payload = prediction.value?.result_payload as {
        can_fetch_overlap?: boolean;
    } | null;
    return payload?.can_fetch_overlap ?? false;
});

const showNeedsOverlapData = computed(() => {
    return ambiguousProbability.value && canFetchOverlap.value;
});

const instagramProfileUrl = computed(() => {
    const username = prediction.value?.target_username?.trim();
    if (!username) {
        return "";
    }
    return `https://www.instagram.com/${username}`;
});

async function pollTask(taskId: string, predictionId: string) {
    const maxPolls = 40;
    for (let i = 0; i < maxPolls && !disposed; i += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const task = await api.getPredictionTaskStatus(taskId);
        currentTask.value = task;
        if (task.status === "completed") {
            const details: PredictionDetailResponse =
                await api.getPrediction(predictionId);
            prediction.value = details.prediction;
            currentTask.value = details.task;
            await loadRelationshipCacheStatus(false);
            statusMessage.value = "Prediction refreshed successfully.";
            return;
        }
        if (task.status === "error") {
            errorMessage.value = task.error || "Prediction task failed.";
            return;
        }
        statusMessage.value = "Refreshing data for this user. Please wait...";
    }
    if (!disposed) {
        errorMessage.value =
            "Timed out while waiting for refresh. Please try again.";
    }
}

async function loadRelationshipCacheStatus(syncCounts = false) {
    if (!prediction.value?.target_profile_id) {
        relationshipCache.value = null;
        return;
    }
    relationshipCache.value = await api.getTargetRelationshipCacheStatus(
        prediction.value.target_profile_id,
        { sync_counts: syncCounts },
    );
}

async function loadPrediction(username: string) {
    if (!username.trim()) {
        return;
    }

    isLoading.value = true;
    errorMessage.value = "";
    statusMessage.value = "";
    currentTask.value = null;

    try {
        const response = await api.createFollowBackPrediction({
            username: username.trim(),
            refresh: false,
            force_background: false,
        });

        prediction.value = response.prediction;
        currentTask.value = response.task;
        await loadRelationshipCacheStatus(false);

        if (!response.task) {
            if (showNeedsOverlapData.value) {
                statusMessage.value = "Prediction is ambiguous (45-65%). Fetch followers/following overlap for clarity.";
            } else {
                statusMessage.value = "Prediction is ready.";
            }
            return;
        }

        statusMessage.value =
            "Prediction queued. Waiting for background refresh...";
        await pollTask(
            response.task.task_id,
            response.prediction.prediction_id,
        );
    } catch (error: unknown) {
        errorMessage.value =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error || "Could not load prediction for this username.";
    } finally {
        if (!disposed) {
            isLoading.value = false;
        }
    }
}

async function refreshPrediction() {
    const username = (
        prediction.value?.target_username || usernameInput.value
    ).trim();
    if (!username) {
        return;
    }

    isLoading.value = true;
    errorMessage.value = "";
    statusMessage.value = "Refreshing this target with fresh backend data...";

    try {
        const response = await api.createFollowBackPrediction({
            username,
            refresh: true,
            force_background: true,
        });
        prediction.value = response.prediction;
        currentTask.value = response.task;
        await loadRelationshipCacheStatus(false);

        if (response.task) {
            await pollTask(
                response.task.task_id,
                response.prediction.prediction_id,
            );
        }
    } catch (error: unknown) {
        errorMessage.value =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error || "Could not refresh this target right now.";
    } finally {
        if (!disposed) {
            isLoading.value = false;
        }
    }
}

async function refreshRelationshipList(relationshipType: "followers" | "following") {
    if (!prediction.value?.target_profile_id) {
        return;
    }

    listRefreshPending.value[relationshipType] = true;
    listRefreshError.value[relationshipType] = "";
    statusMessage.value = `Refreshing ${relationshipType} list...`;

    try {
        const response = await api.refreshTargetRelationshipCache(
            prediction.value.target_profile_id,
            relationshipType,
        );
        prediction.value = response.prediction;
        currentTask.value = response.task;

        if (response.task) {
            await pollTask(
                response.task.task_id,
                response.prediction.prediction_id,
            );
        }
        await loadRelationshipCacheStatus(false);
    } catch (error: unknown) {
        listRefreshError.value[relationshipType] =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error || `Could not refresh ${relationshipType} right now.`;
    } finally {
        listRefreshPending.value[relationshipType] = false;
    }
}

function formatFetchedAt(value: string | null | undefined) {
    if (!value) {
        return "Not fetched yet";
    }
    return new Date(value).toLocaleString();
}

function formatDaysSince(value: number | null | undefined) {
    if (value === null || value === undefined) {
        return "Not fetched yet";
    }
    if (value === 0) {
        return "Fetched today";
    }
    if (value === 1) {
        return "Fetched 1 day ago";
    }
    return `Fetched ${value} days ago`;
}

function submitLookup() {
    const next = usernameInput.value.trim();
    if (!next) {
        return;
    }
    router.push({
        name: "discovery",
        params: { username: next },
        query: route.query,
    });
}

async function markFeedback(status: "correct" | "wrong") {
    if (!prediction.value) {
        return;
    }
    await api.setPredictionFeedback(prediction.value.prediction_id, {
        assessment_status: status,
    });
    prediction.value = {
        ...prediction.value,
        outcome_status: status,
    };
}

function openFeedback(mode: "correct" | "wrong") {
    feedbackMode.value = mode;
    feedbackReassessing.value = false;
    feedbackDirection.value = null;
    feedbackExpectedPct.value = "";
    feedbackNotes.value = "";
}

function cancelFeedback() {
    feedbackMode.value = null;
    feedbackReassessing.value = false;
}

async function submitFeedback() {
    if (!prediction.value || !feedbackMode.value) {
        return;
    }
    feedbackSubmitting.value = true;
    try {
        const expectedPct = parseFloat(feedbackExpectedPct.value);
        const payload: PredictionFeedbackPayload = {
            assessment_status: feedbackMode.value,
            ...(feedbackNotes.value.trim() ? { notes: feedbackNotes.value.trim() } : {}),
            ...(feedbackDirection.value ? { expected_direction: feedbackDirection.value } : {}),
            ...(!isNaN(expectedPct) && expectedPct >= 0 && expectedPct <= 100
                ? { expected_value: expectedPct / 100 }
                : {}),
        };
        await api.setPredictionFeedback(prediction.value.prediction_id, payload);
        prediction.value = {
            ...prediction.value,
            outcome_status: feedbackMode.value,
        };
        feedbackMode.value = null;
    } finally {
        feedbackSubmitting.value = false;
    }
}
</script>

<template>
    <section class="space-y-5 fade-in">
        <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6">
            <h2 class="text-xl font-bold font-display text-gradient">Discovery</h2>
            <p class="text-sm text-slate-400 mt-1">
                Look up a user and inspect their current follow-back prediction
                details.
            </p>

            <form
                class="mt-4 flex flex-col sm:flex-row gap-2"
                @submit.prevent="submitLookup"
            >
                <input
                    v-model="usernameInput"
                    placeholder="instagram username"
                    class="input-dark"
                />
                <button
                    :disabled="isLoading"
                    class="btn-violet px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
                >
                    {{ isLoading ? "Loading..." : "Open Discovery" }}
                </button>
            </form>
            <p class="text-xs text-slate-500 mt-2">
                Active profile: {{ props.profileId }}
            </p>
        </div>

        <div v-if="!prediction && !isLoading">
            <PredictionStatePanel
                title="No discovery data yet"
                message="If a target has never been checked before, the first request may need to queue a refresh before profile details become available."
                tone="warning"
            />
        </div>

        <PredictionStatePanel
            v-if="statusMessage"
            title="Background status"
            :message="statusMessage"
            tone="info"
        >
            <TaskProgressBar :task="currentTask" />
        </PredictionStatePanel>

        <PredictionStatePanel
            v-if="errorMessage"
            title="Could not load this target"
            :message="errorMessage"
            tone="error"
        />

        <div
            v-if="prediction"
            class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6 space-y-4"
        >
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div class="flex items-center gap-3 min-w-0">
                    <ProfilePicture
                        v-if="prediction.target_profile_id"
                        :pk-id="prediction.target_profile_id"
                        :profile-id="props.profileId"
                        :alt="prediction.target_username || 'target profile'"
                        class="w-14 h-14"
                    />
                    <div class="min-w-0">
                        <p class="text-xs uppercase tracking-wide text-slate-500">
                            Target
                        </p>
                        <a
                            v-if="instagramProfileUrl"
                            :href="instagramProfileUrl"
                            target="_blank"
                            rel="noopener noreferrer"
                            class="text-lg font-bold text-violet-400 hover:text-violet-300 hover:underline truncate inline-block max-w-full"
                        >
                            @{{ prediction.target_username || "unknown" }} ↗
                        </a>
                        <p v-else class="text-lg font-bold text-slate-100">
                            @{{ prediction.target_username || "unknown" }}
                        </p>
                        <p class="text-[10px] text-slate-500 mt-0.5">
                            user id: {{ prediction.target_profile_id || "--" }}
                        </p>
                    </div>
                </div>
                <div class="text-right">
                    <p class="text-xs uppercase tracking-wide text-slate-500">
                        Status
                    </p>
                    <PredictionStatusBadge :status="prediction.status" />
                </div>
            </div>

            <div class="grid lg:grid-cols-[1.1fr,0.9fr] gap-4 items-start">
                <div class="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4">
                    <p class="text-xs uppercase tracking-wide text-slate-500">
                        Prediction snapshot
                    </p>
                    <div class="mt-3">
                        <ProbabilityChip
                            :probability="prediction.probability"
                            :confidence="prediction.confidence"
                            size="lg"
                        />
                        <span
                            v-if="showNeedsOverlapData"
                            class="inline-block mt-2 px-3 py-1 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/25"
                        >
                            Ambiguous — needs overlap data
                        </span>
                    </div>
                    <div class="mt-4 flex flex-wrap gap-2">
                        <button
                            :disabled="isLoading"
                            class="btn-violet px-3 py-1.5 rounded-lg text-sm font-medium disabled:opacity-50"
                            @click="refreshPrediction"
                        >
                            Refresh data
                        </button>
                        <p class="text-xs text-slate-500 self-center">
                            Current:
                            {{ prediction.outcome_status || "pending" }}
                        </p>
                    </div>
                    <div class="mt-3">
                        <TaskProgressBar :task="currentTask" />
                    </div>
                </div>

                <div class="rounded-2xl border border-white/[0.07] bg-white/[0.02] p-4 space-y-3">
                    <p class="text-xs uppercase tracking-wide text-slate-500">
                        Target details
                    </p>
                    <div
                        v-if="targetProfile"
                        class="grid sm:grid-cols-2 gap-3 text-sm text-slate-300"
                    >
                        <p>
                            <span class="font-semibold">Full name:</span>
                            {{ targetProfile.full_name || "Unknown" }}
                        </p>
                        <p>
                            <span class="font-semibold">Category:</span>
                            {{ targetProfile.category || "Unknown" }}
                        </p>
                        <p>
                            <span class="font-semibold">Followers:</span>
                            {{ targetProfile.follower_count ?? "--" }}
                        </p>
                        <p>
                            <span class="font-semibold">Following:</span>
                            {{ targetProfile.following_count ?? "--" }}
                        </p>
                        <p>
                            <span class="font-semibold">Mutuals:</span>
                            {{ targetProfile.mutual_followers_count ?? "--" }}
                        </p>
                        <p>
                            <span class="font-semibold">Media count:</span>
                            {{ targetProfile.media_count ?? "--" }}
                        </p>
                    </div>
                    <p v-else class="text-sm text-slate-500">
                        Detailed target metadata is still loading. If this user
                        has not been refreshed yet, wait for the task to finish.
                    </p>

                    <div
                        v-if="showNeedsOverlapData"
                        class="rounded-xl border border-amber-500/30 bg-amber-500/10 p-4 mt-4"
                    >
                        <p class="text-sm font-semibold text-amber-300 mb-3">
                            Prediction is ambiguous (45-65% range)
                        </p>
                        <p class="text-sm text-amber-100 mb-3">
                            Fetch the followers and following lists to analyze overlap with your audience
                            for a more confident prediction.
                        </p>
                        <button
                            :disabled="isLoading || listRefreshPending.followers || listRefreshPending.following"
                            class="btn-violet px-3 py-1.5 rounded-lg text-sm font-semibold disabled:opacity-50"
                            @click="async () => { await refreshRelationshipList('followers'); await refreshRelationshipList('following'); }"
                        >
                            Fetch followers & following for details
                        </button>
                    </div>

                    <div
                        v-if="relationshipCache"
                        class="space-y-3 pt-2 border-t border-white/[0.07]"
                    >
                        <p class="text-xs uppercase tracking-wide text-slate-500">
                            Relationship list cache
                        </p>

                        <div class="grid sm:grid-cols-2 gap-3 text-sm">
                            <div class="rounded-xl border border-white/[0.07] p-3 bg-white/[0.02]">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="font-semibold text-slate-200">Followers list</p>
                                    <span
                                        v-if="relationshipCache.followers.is_outdated"
                                        class="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/25"
                                    >
                                        Outdated
                                    </span>
                                </div>
                                <p class="text-slate-400 mt-1">
                                    {{ formatDaysSince(relationshipCache.followers.days_since_fetch) }}
                                </p>
                                <p class="text-xs text-slate-500 mt-1">
                                    Last fetched: {{ formatFetchedAt(relationshipCache.followers.fetched_at) }}
                                </p>
                                <p class="text-xs text-slate-500">
                                    Count snapshot: {{ relationshipCache.followers.last_known_count ?? "--" }}
                                    · Current known: {{ relationshipCache.followers.current_count ?? "--" }}
                                </p>
                                <button
                                    :disabled="isLoading || listRefreshPending.followers"
                                    class="btn-violet mt-2 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
                                    @click="refreshRelationshipList('followers')"
                                >
                                    {{ listRefreshPending.followers ? "Refreshing..." : "Refresh followers" }}
                                </button>
                                <p
                                    v-if="listRefreshError.followers"
                                    class="text-xs text-rose-400 mt-1"
                                >
                                    {{ listRefreshError.followers }}
                                </p>
                            </div>

                            <div class="rounded-xl border border-white/[0.07] p-3 bg-white/[0.02]">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="font-semibold text-slate-200">Following list</p>
                                    <span
                                        v-if="relationshipCache.following.is_outdated"
                                        class="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-500/15 text-amber-300 border border-amber-500/25"
                                    >
                                        Outdated
                                    </span>
                                </div>
                                <p class="text-slate-400 mt-1">
                                    {{ formatDaysSince(relationshipCache.following.days_since_fetch) }}
                                </p>
                                <p class="text-xs text-slate-500 mt-1">
                                    Last fetched: {{ formatFetchedAt(relationshipCache.following.fetched_at) }}
                                </p>
                                <p class="text-xs text-slate-500">
                                    Count snapshot: {{ relationshipCache.following.last_known_count ?? "--" }}
                                    · Current known: {{ relationshipCache.following.current_count ?? "--" }}
                                </p>
                                <button
                                    :disabled="isLoading || listRefreshPending.following"
                                    class="btn-violet mt-2 px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
                                    @click="refreshRelationshipList('following')"
                                >
                                    {{ listRefreshPending.following ? "Refreshing..." : "Refresh following" }}
                                </button>
                                <p
                                    v-if="listRefreshError.following"
                                    class="text-xs text-rose-400 mt-1"
                                >
                                    {{ listRefreshError.following }}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <h3 class="text-sm font-semibold text-slate-200 mb-2">
                    Reasons
                </h3>
                <ul
                    v-if="reasons.length"
                    class="space-y-1 text-sm text-slate-300 list-disc ml-5"
                >
                    <li v-for="reason in reasons" :key="reason">
                        {{ reason }}
                    </li>
                </ul>
                <p v-else class="text-sm text-slate-500">
                    No reasons are available yet. This can happen while refresh
                    is still running.
                </p>
            </div>

            <!-- Outcome feedback section -->
            <div class="pt-3 border-t border-white/[0.07]">
                <!-- Already assessed: show status badge + re-assess link -->
                <div
                    v-if="!feedbackMode && !feedbackReassessing && prediction.outcome_status && prediction.outcome_status !== 'pending'"
                    class="flex items-center gap-3 p-3 rounded-xl bg-white/[0.03] border border-white/[0.06]"
                >
                    <span class="text-2xl">{{ ['correct', 'confirmed'].includes(prediction.outcome_status) ? '✅' : '❌' }}</span>
                    <div class="flex-1">
                        <p class="text-sm font-semibold text-slate-200">
                            Outcome recorded:
                            <span :class="['correct', 'confirmed'].includes(prediction.outcome_status) ? 'text-emerald-400' : 'text-rose-400'">
                                {{ prediction.outcome_status }}
                            </span>
                        </p>
                        <p class="text-xs text-slate-500">Feedback saved · thank you!</p>
                    </div>
                    <button
                        class="text-xs text-slate-500 hover:text-violet-400 underline"
                        @click="feedbackReassessing = true"
                    >
                        Re-assess
                    </button>
                </div>

                <!-- Idle: primary action buttons -->
                <div v-else-if="!feedbackMode" class="space-y-2">
                    <p class="text-sm font-medium text-slate-300">Did this prediction come true?</p>
                    <div class="flex gap-3">
                        <button
                            class="flex-1 py-2.5 rounded-xl border-2 border-emerald-500/25 bg-emerald-500/10 text-emerald-300 text-sm font-semibold hover:bg-emerald-500/15 hover:border-emerald-400/50 transition-all"
                            @click="openFeedback('correct')"
                        >
                            ✅ Yes, it did
                        </button>
                        <button
                            class="flex-1 py-2.5 rounded-xl border-2 border-rose-500/25 bg-rose-500/10 text-rose-300 text-sm font-semibold hover:bg-rose-500/15 hover:border-rose-400/50 transition-all"
                            @click="openFeedback('wrong')"
                        >
                            ❌ No, it didn't
                        </button>
                    </div>
                </div>

                <!-- Correct feedback form -->
                <div v-else-if="feedbackMode === 'correct'" class="space-y-3">
                    <div class="flex items-center gap-2">
                        <span class="text-xl">🎯</span>
                        <p class="text-base font-bold text-slate-100">Prediction was correct!</p>
                        <button class="ml-auto text-xs text-slate-500 hover:text-slate-300" @click="cancelFeedback">✕ cancel</button>
                    </div>
                    <p class="text-sm text-slate-400">
                        Model predicted <strong>{{ probabilityLabel }}</strong>. How accurate was that estimate?
                    </p>
                    <div class="grid grid-cols-3 gap-2">
                        <button
                            :class="['py-3 rounded-xl border-2 text-xs font-semibold transition-all text-center', feedbackDirection === 'higher' ? 'bg-emerald-500/15 border-emerald-400/60 text-emerald-300' : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-emerald-400/40']"
                            @click="feedbackDirection = 'higher'"
                        >
                            📈 Underestimated<br>
                            <span class="font-normal">Should be higher</span>
                        </button>
                        <button
                            :class="['py-3 rounded-xl border-2 text-xs font-semibold transition-all text-center', feedbackDirection === null ? 'bg-violet-500/15 border-violet-400/60 text-violet-300' : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-violet-400/40']"
                            @click="feedbackDirection = null"
                        >
                            🎯 Spot on!<br>
                            <span class="font-normal">Accurate estimate</span>
                        </button>
                        <button
                            :class="['py-3 rounded-xl border-2 text-xs font-semibold transition-all text-center', feedbackDirection === 'lower' ? 'bg-amber-500/15 border-amber-400/60 text-amber-300' : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-amber-400/40']"
                            @click="feedbackDirection = 'lower'"
                        >
                            📉 Overestimated<br>
                            <span class="font-normal">Should be lower</span>
                        </button>
                    </div>
                    <div v-if="feedbackDirection" class="flex items-center gap-2">
                        <label class="text-xs text-slate-400 shrink-0">Your estimate:</label>
                        <input
                            v-model="feedbackExpectedPct"
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            placeholder="e.g. 85"
                            class="w-20 px-2 py-1 text-sm rounded-lg bg-slate-900 border border-slate-700 text-slate-200"
                        />
                        <span class="text-xs text-slate-500">% (optional)</span>
                    </div>
                    <textarea
                        v-model="feedbackNotes"
                        placeholder="Optional notes..."
                        rows="2"
                        class="w-full text-sm rounded-lg px-3 py-2 resize-none bg-slate-900 border border-slate-700 text-slate-200"
                    />
                    <div class="flex gap-2">
                        <button
                            :disabled="feedbackSubmitting"
                            class="flex-1 py-2 rounded-xl bg-emerald-500 text-white font-semibold text-sm hover:bg-emerald-600 disabled:opacity-50 transition-all"
                            @click="submitFeedback"
                        >
                            {{ feedbackSubmitting ? 'Saving...' : 'Confirm Correct ✓' }}
                        </button>
                        <button
                            class="btn-ghost px-4 py-2 rounded-xl text-sm"
                            @click="cancelFeedback"
                        >
                            Cancel
                        </button>
                    </div>
                </div>

                <!-- Wrong feedback form -->
                <div v-else-if="feedbackMode === 'wrong'" class="space-y-3">
                    <div class="flex items-center gap-2">
                        <span class="text-xl">🤔</span>
                        <p class="text-base font-bold text-slate-100">What went wrong?</p>
                        <button class="ml-auto text-xs text-slate-500 hover:text-slate-300" @click="cancelFeedback">✕ cancel</button>
                    </div>
                    <p class="text-sm text-slate-400">
                        Model predicted <strong>{{ probabilityLabel }}</strong>. What was the real outcome?
                    </p>
                    <div class="grid grid-cols-2 gap-3">
                        <button
                            :class="['py-4 rounded-xl border-2 text-sm font-semibold transition-all flex flex-col items-center gap-1', feedbackDirection === 'higher' ? 'bg-emerald-500/15 border-emerald-400/60 text-emerald-300 scale-105' : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-emerald-400/40 hover:bg-emerald-500/10']"
                            @click="feedbackDirection = 'higher'"
                        >
                            <span class="text-2xl">📈</span>
                            <span>Higher</span>
                            <span class="text-xs font-normal text-slate-500">Model underestimated</span>
                        </button>
                        <button
                            :class="['py-4 rounded-xl border-2 text-sm font-semibold transition-all flex flex-col items-center gap-1', feedbackDirection === 'lower' ? 'bg-rose-500/15 border-rose-400/60 text-rose-300 scale-105' : 'bg-white/[0.03] border-white/[0.08] text-slate-400 hover:border-rose-400/40 hover:bg-rose-500/10']"
                            @click="feedbackDirection = 'lower'"
                        >
                            <span class="text-2xl">📉</span>
                            <span>Lower</span>
                            <span class="text-xs font-normal text-slate-500">Model overestimated</span>
                        </button>
                    </div>
                    <div class="flex items-center gap-2">
                        <label class="text-xs text-slate-400 shrink-0">Your estimate:</label>
                        <input
                            v-model="feedbackExpectedPct"
                            type="number"
                            min="0"
                            max="100"
                            step="1"
                            placeholder="e.g. 20"
                            class="w-20 px-2 py-1 text-sm rounded-lg bg-slate-900 border border-slate-700 text-slate-200"
                        />
                        <span class="text-xs text-slate-500">% (optional)</span>
                    </div>
                    <textarea
                        v-model="feedbackNotes"
                        placeholder="Optional notes (e.g. 'User never follows anyone back')"
                        rows="2"
                        class="w-full text-sm rounded-lg px-3 py-2 resize-none bg-slate-900 border border-slate-700 text-slate-200"
                    />
                    <div class="flex gap-2">
                        <button
                            :disabled="feedbackSubmitting"
                            class="flex-1 py-2 rounded-xl bg-rose-500 text-white font-semibold text-sm hover:bg-rose-600 disabled:opacity-50 transition-all"
                            @click="submitFeedback"
                        >
                            {{ feedbackSubmitting ? 'Saving...' : 'Submit Feedback' }}
                        </button>
                        <button
                            class="btn-ghost px-4 py-2 rounded-xl text-sm"
                            @click="cancelFeedback"
                        >
                            Cancel
                        </button>
                    </div>
                </div>
            </div>
        </div>
    </section>
</template>
