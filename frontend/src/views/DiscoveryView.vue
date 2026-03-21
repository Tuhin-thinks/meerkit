<script setup lang="ts">
import { computed, onBeforeUnmount, ref, watch } from "vue";
import { useRoute, useRouter } from "vue-router";
import PredictionStatePanel from "../components/prediction/PredictionStatePanel.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import type {
    PredictionDetailResponse,
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
            statusMessage.value = "Prediction is ready.";
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
</script>

<template>
    <section class="space-y-5">
        <div class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
            <h2 class="text-lg font-bold text-gray-900">Discovery</h2>
            <p class="text-sm text-gray-500 mt-1">
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
                    class="flex-1 border border-gray-200 rounded-lg px-3 py-2 text-sm"
                />
                <button
                    :disabled="isLoading"
                    class="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
                >
                    {{ isLoading ? "Loading..." : "Open Discovery" }}
                </button>
            </form>
            <p class="text-xs text-gray-500 mt-2">
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
            class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6 space-y-4"
        >
            <div class="flex flex-wrap items-center justify-between gap-4">
                <div>
                    <p class="text-xs uppercase tracking-wide text-gray-500">
                        Target
                    </p>
                    <p class="text-lg font-bold text-gray-900">
                        @{{ prediction.target_username || "unknown" }}
                    </p>
                </div>
                <div class="text-right">
                    <p class="text-xs uppercase tracking-wide text-gray-500">
                        Status
                    </p>
                    <PredictionStatusBadge :status="prediction.status" />
                </div>
            </div>

            <div class="grid lg:grid-cols-[1.1fr,0.9fr] gap-4 items-start">
                <div class="rounded-2xl border border-gray-100 p-4">
                    <p class="text-xs uppercase tracking-wide text-gray-500">
                        Prediction snapshot
                    </p>
                    <div class="mt-3">
                        <ProbabilityChip
                            :probability="prediction.probability"
                            :confidence="prediction.confidence"
                            size="lg"
                        />
                    </div>
                    <div class="mt-4 flex flex-wrap gap-2">
                        <button
                            :disabled="isLoading"
                            class="px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-sm font-medium hover:bg-indigo-700 disabled:opacity-50"
                            @click="refreshPrediction"
                        >
                            Refresh data
                        </button>
                        <p class="text-xs text-gray-500 self-center">
                            Current:
                            {{ prediction.outcome_status || "pending" }}
                        </p>
                    </div>
                    <div class="mt-3">
                        <TaskProgressBar :task="currentTask" />
                    </div>
                </div>

                <div class="rounded-2xl border border-gray-100 p-4 space-y-3">
                    <p class="text-xs uppercase tracking-wide text-gray-500">
                        Target details
                    </p>
                    <div
                        v-if="targetProfile"
                        class="grid sm:grid-cols-2 gap-3 text-sm text-gray-700"
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
                    <p v-else class="text-sm text-gray-500">
                        Detailed target metadata is still loading. If this user
                        has not been refreshed yet, wait for the task to finish.
                    </p>

                    <div
                        v-if="relationshipCache"
                        class="space-y-3 pt-2 border-t border-gray-100"
                    >
                        <p class="text-xs uppercase tracking-wide text-gray-500">
                            Relationship list cache
                        </p>

                        <div class="grid sm:grid-cols-2 gap-3 text-sm">
                            <div class="rounded-xl border border-gray-200 p-3 bg-gray-50/70">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="font-semibold text-gray-800">Followers list</p>
                                    <span
                                        v-if="relationshipCache.followers.is_outdated"
                                        class="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800"
                                    >
                                        Outdated
                                    </span>
                                </div>
                                <p class="text-gray-600 mt-1">
                                    {{ formatDaysSince(relationshipCache.followers.days_since_fetch) }}
                                </p>
                                <p class="text-xs text-gray-500 mt-1">
                                    Last fetched: {{ formatFetchedAt(relationshipCache.followers.fetched_at) }}
                                </p>
                                <p class="text-xs text-gray-500">
                                    Count snapshot: {{ relationshipCache.followers.last_known_count ?? "--" }}
                                    · Current known: {{ relationshipCache.followers.current_count ?? "--" }}
                                </p>
                                <button
                                    :disabled="isLoading || listRefreshPending.followers"
                                    class="mt-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                                    @click="refreshRelationshipList('followers')"
                                >
                                    {{ listRefreshPending.followers ? "Refreshing..." : "Refresh followers" }}
                                </button>
                                <p
                                    v-if="listRefreshError.followers"
                                    class="text-xs text-rose-600 mt-1"
                                >
                                    {{ listRefreshError.followers }}
                                </p>
                            </div>

                            <div class="rounded-xl border border-gray-200 p-3 bg-gray-50/70">
                                <div class="flex items-center justify-between gap-2">
                                    <p class="font-semibold text-gray-800">Following list</p>
                                    <span
                                        v-if="relationshipCache.following.is_outdated"
                                        class="px-2 py-0.5 rounded-full text-xs font-semibold bg-amber-100 text-amber-800"
                                    >
                                        Outdated
                                    </span>
                                </div>
                                <p class="text-gray-600 mt-1">
                                    {{ formatDaysSince(relationshipCache.following.days_since_fetch) }}
                                </p>
                                <p class="text-xs text-gray-500 mt-1">
                                    Last fetched: {{ formatFetchedAt(relationshipCache.following.fetched_at) }}
                                </p>
                                <p class="text-xs text-gray-500">
                                    Count snapshot: {{ relationshipCache.following.last_known_count ?? "--" }}
                                    · Current known: {{ relationshipCache.following.current_count ?? "--" }}
                                </p>
                                <button
                                    :disabled="isLoading || listRefreshPending.following"
                                    class="mt-2 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs font-semibold hover:bg-indigo-700 disabled:opacity-50"
                                    @click="refreshRelationshipList('following')"
                                >
                                    {{ listRefreshPending.following ? "Refreshing..." : "Refresh following" }}
                                </button>
                                <p
                                    v-if="listRefreshError.following"
                                    class="text-xs text-rose-600 mt-1"
                                >
                                    {{ listRefreshError.following }}
                                </p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>

            <div>
                <h3 class="text-sm font-semibold text-gray-800 mb-2">
                    Reasons
                </h3>
                <ul
                    v-if="reasons.length"
                    class="space-y-1 text-sm text-gray-700 list-disc ml-5"
                >
                    <li v-for="reason in reasons" :key="reason">
                        {{ reason }}
                    </li>
                </ul>
                <p v-else class="text-sm text-gray-500">
                    No reasons are available yet. This can happen while refresh
                    is still running.
                </p>
            </div>

            <div
                class="pt-2 border-t border-gray-100 flex flex-wrap gap-2 items-center"
            >
                <p class="text-sm text-gray-600">Mark outcome:</p>
                <button
                    class="px-3 py-1.5 rounded-lg bg-emerald-100 text-emerald-800 text-sm font-medium hover:bg-emerald-200"
                    @click="markFeedback('correct')"
                >
                    Correct
                </button>
                <button
                    class="px-3 py-1.5 rounded-lg bg-rose-100 text-rose-800 text-sm font-medium hover:bg-rose-200"
                    @click="markFeedback('wrong')"
                >
                    Wrong
                </button>
                <p class="text-xs text-gray-500">
                    Current: {{ prediction.outcome_status || "pending" }}
                </p>
            </div>
        </div>
    </section>
</template>
