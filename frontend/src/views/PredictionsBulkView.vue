<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { RouterLink, useRouter } from "vue-router";
import PredictionStatePanel from "../components/prediction/PredictionStatePanel.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import {
    extractApiErrorMessage,
    mapTargetAccessError,
} from "../services/targetAccessErrors";
import { setBulkBatchRunning } from "../services/uiTaskState";
import type {
    FollowBackPredictionResponse,
    PredictionRecord,
    PredictionTask,
} from "../types/prediction";

const props = defineProps<{
    profileId: string;
}>();

const router = useRouter();

interface BatchRow {
    rawInput: string;
    username: string | null;
    userId: string | null;
    status: "ready" | "queued" | "running" | "completed" | "error" | "invalid";
    message: string;
    prediction: PredictionRecord | null;
    task: PredictionTask | null;
}

const input = ref("");
const isRunning = ref(false);
const rows = ref<BatchRow[]>([]);
const exportMessage = ref("");
const filterMeFollowing = ref(false);
const filterMyFollower = ref(false);
const minFollowBackProbability = ref(0);
const minConfidence = ref(0);
const followBackOperator = ref<">=" | "<=">(">=");
const confidenceOperator = ref<">=" | "<=">(">=");
const orderBy = ref<"follow_back" | "confidence">("follow_back");
const batchPlaceholder = [
    "example_user",
    "https://www.instagram.com/second.user/",
    "12345678901234567",
].join("\n");
let disposed = false;

onBeforeUnmount(() => {
    disposed = true;
});

const validUsernamePattern = /^[a-zA-Z0-9._]+$/;
const instagramProfileHosts = new Set([
    "instagram.com",
    "www.instagram.com",
    "m.instagram.com",
]);
const reservedInstagramPathPrefixes = new Set([
    "about",
    "accounts",
    "developer",
    "direct",
    "explore",
    "graphql",
    "p",
    "reel",
    "reels",
    "stories",
    "tv",
]);

const completedCount = computed(
    () => rows.value.filter((row) => row.status === "completed").length,
);

const erroredCount = computed(
    () =>
        rows.value.filter(
            (row) => row.status === "error" || row.status === "invalid",
        ).length,
);

const filteredCompletedPredictionRows = computed(() =>
    filteredRows.value.filter(
        (row) => row.status === "completed" && row.prediction !== null,
    ),
);

const canExportCompleted = computed(
    () => filteredCompletedPredictionRows.value.length > 0,
);

const filteredRows = computed(() => {
    const filtered = rows.value.filter((row) => {
        const featureBreakdown = getPredictionFeatureBreakdown(row);

        if (
            filterMeFollowing.value &&
            !coerceBoolean(featureBreakdown?.me_following_account)
        ) {
            return false;
        }

        if (
            filterMyFollower.value &&
            !coerceBoolean(featureBreakdown?.being_followed_by_account)
        ) {
            return false;
        }

        const probabilityPercent = toPercent(row.prediction?.probability ?? null);
        if (minFollowBackProbability.value > 0 || minFollowBackProbability.value < 100) {
            if (probabilityPercent === null) {
                return false;
            }
            if (followBackOperator.value === ">=" && probabilityPercent < minFollowBackProbability.value) {
                return false;
            }
            if (followBackOperator.value === "<=" && probabilityPercent > minFollowBackProbability.value) {
                return false;
            }
        }

        const confidencePercent = toPercent(row.prediction?.confidence ?? null);
        if (minConfidence.value > 0 || minConfidence.value < 100) {
            if (confidencePercent === null) {
                return false;
            }
            if (confidenceOperator.value === ">=" && confidencePercent < minConfidence.value) {
                return false;
            }
            if (confidenceOperator.value === "<=" && confidencePercent > minConfidence.value) {
                return false;
            }
        }

        return true;
    });

    return filtered.slice().sort((a, b) => {
        const firstValue =
            orderBy.value === "follow_back"
                ? a.prediction?.probability ?? null
                : a.prediction?.confidence ?? null;
        const secondValue =
            orderBy.value === "follow_back"
                ? b.prediction?.probability ?? null
                : b.prediction?.confidence ?? null;

        if (firstValue === null && secondValue === null) {
            return 0;
        }
        if (firstValue === null) {
            return 1;
        }
        if (secondValue === null) {
            return -1;
        }
        return secondValue - firstValue;
    });
});

function extractInstagramUsername(token: string): string | null {
    if (!token.toLowerCase().includes("instagram.com")) {
        return null;
    }

    let candidate = token.trim();
    if (!candidate.includes("://")) {
        candidate = `https://${candidate.replace(/^\/+/, "")}`;
    }

    try {
        const parsed = new URL(candidate);
        if (!instagramProfileHosts.has(parsed.hostname.toLowerCase())) {
            return null;
        }

        const firstPathSegment = parsed.pathname
            .split("/")
            .filter(Boolean)[0]
            ?.replace(/^@/, "")
            .trim();
        if (!firstPathSegment) {
            return null;
        }
        if (reservedInstagramPathPrefixes.has(firstPathSegment.toLowerCase())) {
            return null;
        }
        return firstPathSegment;
    } catch {
        return null;
    }
}

function parseTargets(raw: string): BatchRow[] {
    const tokens = raw
        .split(/[\n,]/)
        .map((token) => token.trim())
        .filter(Boolean);

    const dedupedMap = new Map<string, BatchRow>();
    const lastIndexByKey = new Map<string, number>();
    tokens.forEach((token, index) => {
        const linkUsername = extractInstagramUsername(token);
        const normalizedToken = (linkUsername || token).replace(/^@/, "").trim();

        let username: string | null = null;
        let userId: string | null = null;
        let status: BatchRow["status"] = "ready";
        let message = "Ready";

        if (/^\d+$/.test(normalizedToken)) {
            userId = normalizedToken;
        } else if (validUsernamePattern.test(normalizedToken)) {
            username = normalizedToken;
        } else {
            status = "invalid";
            message = "Enter a username, Instagram profile link, or numeric user ID.";
        }

        const dedupeKey = userId
            ? `user:${userId}`
            : username
              ? `username:${username.toLowerCase()}`
              : `invalid:${token.toLowerCase()}`;
        dedupedMap.set(dedupeKey, {
            rawInput: token,
            username,
            userId,
            status,
            message,
            prediction: null,
            task: null,
        });
        lastIndexByKey.set(dedupeKey, index);
    });

    return Array.from(dedupedMap.entries())
        .sort(
            ([firstKey], [secondKey]) =>
                (lastIndexByKey.get(firstKey) ?? 0) -
                (lastIndexByKey.get(secondKey) ?? 0),
        )
        .map(([, row]) => row);
}

function getRowTitle(row: BatchRow): string {
    const resolvedUsername = row.prediction?.target_username || row.username;
    if (resolvedUsername) {
        return `@${resolvedUsername}`;
    }
    if (row.userId) {
        return `ID ${row.userId}`;
    }
    return row.rawInput;
}

function createPredictionSessionId(): string {
    return `pred_session_${Date.now()}_${Math.random().toString(36).slice(2, 10)}`;
}

async function pollTask(row: BatchRow, taskId: string, predictionId: string) {
    const maxPolls = 30;
    for (let attempt = 0; attempt < maxPolls && !disposed; attempt += 1) {
        await new Promise((resolve) => setTimeout(resolve, 1500));
        const task = await api.getPredictionTaskStatus(taskId);
        row.task = task;

        if (task.status === "completed") {
            const details = await api.getPrediction(predictionId);
            row.prediction = details.prediction;
            row.status = "completed";
            row.message = "Prediction refreshed and ready.";
            return;
        }

        if (task.status === "error") {
            row.status = "error";
            row.message = mapTargetAccessError(
                task.error || null,
                "Prediction refresh failed.",
            );
            return;
        }

        row.status = "running";
        row.message = "Refreshing target data. Please wait...";
    }

    if (!disposed && row.status !== "completed") {
        row.status = "error";
        row.message =
            "Timed out waiting for task completion. You can retry this username.";
    }
}

async function runBatch() {
    rows.value = parseTargets(input.value);

    if (!rows.value.length) {
        return;
    }

    isRunning.value = true;
    setBulkBatchRunning(true);
    const predictionSessionId = createPredictionSessionId();
    try {
        const queue = rows.value.filter((row) => row.status === "ready");
        const workers = Array.from({ length: Math.min(3, queue.length) }).map(
            async () => {
                while (queue.length && !disposed) {
                    const row = queue.shift();
                    if (!row) {
                        return;
                    }
                    await executeRow(row, predictionSessionId);
                }
            },
        );

        await Promise.all(workers);
    } finally {
        if (!disposed) {
            isRunning.value = false;
        }
        setBulkBatchRunning(false);
    }
}

async function executeRow(
    row: BatchRow,
    predictionSessionId: string,
) {
    if (!row.username && !row.userId) {
        row.status = "invalid";
        row.message = "Enter a username, Instagram profile link, or numeric user ID.";
        return;
    }

    try {
        const response: FollowBackPredictionResponse =
            await api.createFollowBackPrediction({
                username: row.username ?? undefined,
                user_id: row.userId ?? undefined,
                refresh: false,
                force_background: false,
                prediction_session_id: predictionSessionId,
            });

        row.prediction = response.prediction;
        row.task = response.task;

        if (!response.task) {
            row.status = "completed";
            row.message = "Prediction ready from available data.";
            return;
        }

        row.status = "queued";
        row.message = "Queued for refresh. Waiting for background worker...";
        await pollTask(
            row,
            response.task.task_id,
            response.prediction.prediction_id,
        );
    } catch (error: unknown) {
        const message = mapTargetAccessError(
            extractApiErrorMessage(error),
            "Could not request prediction for this target.",
        );
        row.status = "error";
        row.message = message;
    }
}

function formatProbability(value: number | null) {
    if (value === null || Number.isNaN(value)) return "--";
    return `${Math.round(value * 100)}%`;
}

function toPercent(value: number | null): number | null {
    if (value === null || Number.isNaN(value)) {
        return null;
    }
    return Math.round(value * 100);
}

function coerceBoolean(value: unknown): boolean {
    return value === true;
}

function getPredictionFeatureBreakdown(row: BatchRow):
    | {
          me_following_account?: unknown;
          being_followed_by_account?: unknown;
      }
    | null {
    if (!row.prediction) {
        return null;
    }

    const directBreakdown = row.prediction.feature_breakdown as {
        me_following_account?: unknown;
        being_followed_by_account?: unknown;
    } | null;

    if (directBreakdown) {
        return directBreakdown;
    }

    const payload = row.prediction.result_payload as {
        feature_breakdown?: {
            me_following_account?: unknown;
            being_followed_by_account?: unknown;
        };
    } | null;

    return payload?.feature_breakdown ?? null;
}

function hasAltFollowback(row: BatchRow) {
    const payload = row.prediction?.result_payload as {
        alt_followback_assessment?: {
            is_alt_account_following_you?: boolean;
        };
    } | null;
    return Boolean(
        payload?.alt_followback_assessment?.is_alt_account_following_you,
    );
}

function clearResults() {
    rows.value = [];
    exportMessage.value = "";
}

function resetFilters() {
    filterMeFollowing.value = false;
    filterMyFollower.value = false;
    minFollowBackProbability.value = 0;
    minConfidence.value = 0;
    followBackOperator.value = ">=";
    confidenceOperator.value = ">=";
    orderBy.value = "follow_back";
}

function getVisibleCompletedRows(): BatchRow[] {
    return filteredRows.value.filter(
        (row) => row.status === "completed" && row.prediction !== null,
    );
}

function getCompletedUsernames(completedRows: BatchRow[]): string[] {
    const usernames = new Set<string>();
    for (const row of completedRows) {
        const username = row.prediction?.target_username?.trim();
        if (username) {
            usernames.add(username);
        }
    }
    return Array.from(usernames);
}

function getCompletedJsonPayload(
    completedRows: BatchRow[],
): Array<Record<string, unknown>> {
    return completedRows.map((row) => ({
        username: row.prediction!.target_username,
        target_profile_id: row.prediction!.target_profile_id,
        probability: row.prediction!.probability,
        confidence: row.prediction!.confidence,
        status: row.prediction!.status,
        outcome_status: row.prediction!.outcome_status,
        requested_at: row.prediction!.requested_at,
        computed_at: row.prediction!.computed_at,
        data_as_of: row.prediction!.data_as_of,
        source_input: row.rawInput,
    }));
}

async function copyTextToClipboard(text: string, successLabel: string) {
    try {
        await navigator.clipboard.writeText(text);
        exportMessage.value = successLabel;
    } catch {
        exportMessage.value = "Clipboard copy failed. Please try download instead.";
    }
}

function downloadTextFile(filename: string, content: string, mimeType: string) {
    const blob = new Blob([content], { type: mimeType });
    const url = URL.createObjectURL(blob);
    const anchor = document.createElement("a");
    anchor.href = url;
    anchor.download = filename;
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
    URL.revokeObjectURL(url);
}

async function copyCompletedAsTxt() {
    const completedRows = getVisibleCompletedRows();
    const usernames = getCompletedUsernames(completedRows);
    if (!usernames.length) {
        exportMessage.value =
            "No completed usernames in the filtered results.";
        return;
    }
    await copyTextToClipboard(
        usernames.join("\n"),
        `Copied ${usernames.length} username(s) as TXT.`,
    );
}

async function copyCompletedAsJson() {
    const completedRows = getVisibleCompletedRows();
    const payload = getCompletedJsonPayload(completedRows);
    if (!payload.length) {
        exportMessage.value =
            "No completed predictions in the filtered results.";
        return;
    }
    await copyTextToClipboard(
        JSON.stringify(payload, null, 2),
        `Copied ${payload.length} filtered prediction record(s) as JSON.`,
    );
}

function downloadCompletedAsTxt() {
    const completedRows = getVisibleCompletedRows();
    const usernames = getCompletedUsernames(completedRows);
    if (!usernames.length) {
        exportMessage.value =
            "No completed usernames in the filtered results.";
        return;
    }
    downloadTextFile("prediction_usernames.txt", usernames.join("\n"), "text/plain;charset=utf-8");
    exportMessage.value = `Downloaded ${usernames.length} username(s) TXT file.`;
}

function downloadCompletedAsJson() {
    const completedRows = getVisibleCompletedRows();
    const payload = getCompletedJsonPayload(completedRows);
    if (!payload.length) {
        exportMessage.value =
            "No completed predictions in the filtered results.";
        return;
    }
    downloadTextFile(
        "prediction_details.json",
        JSON.stringify(payload, null, 2),
        "application/json;charset=utf-8",
    );
    exportMessage.value =
        `Downloaded ${payload.length} filtered prediction record(s) as JSON.`;
}

function openPredictionHistory() {
    void router.push({ name: "predictions-history" });
}
</script>

<template>
    <section class="space-y-5 fade-in">
        <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6">
            <h2 class="text-xl font-bold font-display text-gradient">
                Bulk Follow-Back Predictions
            </h2>
            <p class="text-sm text-slate-400 mt-1">
                Paste Instagram usernames, profile links, or numeric user IDs
                separated by new lines or commas to check follow-back
                probability.
            </p>

            <textarea
                v-model="input"
                rows="6"
                class="input-dark mt-4"
                :placeholder="batchPlaceholder"
            />

            <div class="mt-3 flex items-center justify-between gap-3">
                <p class="text-xs text-slate-500">
                    Active profile: {{ props.profileId }}
                </p>
                <div class="flex items-center gap-2">
                    <button
                        class="btn-ghost px-4 py-2 rounded-lg text-sm font-semibold"
                        @click="openPredictionHistory"
                    >
                        Prediction History
                    </button>
                    <button
                        v-if="rows.length"
                        class="btn-ghost px-4 py-2 rounded-lg text-sm font-semibold"
                        @click="clearResults"
                    >
                        Clear
                    </button>
                    <button
                        :disabled="isRunning"
                        class="btn-violet px-4 py-2 rounded-lg text-sm font-semibold disabled:opacity-50"
                        @click="runBatch"
                    >
                        {{ isRunning ? "Running batch..." : "Start Batch" }}
                    </button>
                </div>
            </div>

            <div
                v-if="canExportCompleted"
                class="mt-4 border border-white/10 rounded-xl bg-white/[0.03] p-3"
            >
                <p class="text-xs text-slate-300 font-semibold mb-2">
                    Completed export options (filtered view)
                </p>
                <div class="flex flex-wrap items-center gap-2">
                    <button
                        class="btn-ghost px-3 py-1.5 rounded-lg text-xs font-semibold"
                        @click="copyCompletedAsTxt"
                    >
                        Copy TXT (usernames)
                    </button>
                    <button
                        class="btn-ghost px-3 py-1.5 rounded-lg text-xs font-semibold"
                        @click="copyCompletedAsJson"
                    >
                        Copy JSON (detailed)
                    </button>
                    <button
                        class="btn-ghost px-3 py-1.5 rounded-lg text-xs font-semibold"
                        @click="downloadCompletedAsTxt"
                    >
                        Download TXT
                    </button>
                    <button
                        class="btn-ghost px-3 py-1.5 rounded-lg text-xs font-semibold"
                        @click="downloadCompletedAsJson"
                    >
                        Download JSON
                    </button>
                </div>
                <p v-if="exportMessage" class="text-xs text-cyan-300 mt-2">
                    {{ exportMessage }}
                </p>
            </div>
        </div>


        <PredictionStatePanel
            v-if="!rows.length"
            title="No batch started yet"
            message="Paste one or more usernames, profile links, or user IDs to queue predictions. Cached results return immediately and queued refreshes will update progressively."
            tone="info"
        />

        <div
            v-if="rows.length"
            class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 overflow-hidden"
        >
            <div class="px-4 py-3 border-b border-white/[0.07] bg-white/[0.01]">
                <div class="flex flex-wrap items-center gap-4 text-xs text-slate-300">
                    <label class="inline-flex items-center gap-2">
                        <input
                            v-model="filterMeFollowing"
                            type="checkbox"
                            class="accent-cyan-500"
                        />
                        Me following
                    </label>

                    <label class="inline-flex items-center gap-2">
                        <input
                            v-model="filterMyFollower"
                            type="checkbox"
                            class="accent-cyan-500"
                        />
                        My follower
                    </label>

                    <label class="inline-flex items-center gap-2">
                        <div class="flex items-center gap-1">
                            <button
                                @click="followBackOperator = '>='"
                                :class="[
                                    'px-2 py-1 rounded text-xs font-semibold transition-colors',
                                    followBackOperator === '>='
                                        ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                                ]"
                            >
                                ≥
                            </button>
                            <button
                                @click="followBackOperator = '<='"
                                :class="[
                                    'px-2 py-1 rounded text-xs font-semibold transition-colors',
                                    followBackOperator === '<='
                                        ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                                ]"
                            >
                                ≤
                            </button>
                        </div>
                        <span>Follow back {{ minFollowBackProbability }}%</span>
                        <input
                            v-model.number="minFollowBackProbability"
                            type="range"
                            min="0"
                            max="100"
                            step="1"
                            class="w-32"
                        />
                    </label>

                    <label class="inline-flex items-center gap-2">
                        <div class="flex items-center gap-1">
                            <button
                                @click="confidenceOperator = '>='"
                                :class="[
                                    'px-2 py-1 rounded text-xs font-semibold transition-colors',
                                    confidenceOperator === '>='
                                        ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                                ]"
                            >
                                ≥
                            </button>
                            <button
                                @click="confidenceOperator = '<='"
                                :class="[
                                    'px-2 py-1 rounded text-xs font-semibold transition-colors',
                                    confidenceOperator === '<='
                                        ? 'bg-cyan-500/30 text-cyan-300 border border-cyan-500/50'
                                        : 'bg-white/5 text-slate-400 border border-white/10 hover:bg-white/10'
                                ]"
                            >
                                ≤
                            </button>
                        </div>
                        <span>Confidence {{ minConfidence }}%</span>
                        <input
                            v-model.number="minConfidence"
                            type="range"
                            min="0"
                            max="100"
                            step="1"
                            class="w-32"
                        />
                    </label>

                    <label class="inline-flex items-center gap-2">
                        <span>Order by</span>
                        <select
                            v-model="orderBy"
                            class="bg-[#0f1a30] border border-white/10 rounded-md px-2 py-1 text-xs"
                        >
                            <option value="follow_back">Follow back</option>
                            <option value="confidence">Confidence</option>
                        </select>
                    </label>

                    <button
                        class="btn-ghost px-2 py-1 rounded-md text-xs font-semibold"
                        @click="resetFilters"
                    >
                        Reset filters
                    </button>
                </div>
            </div>

            <div
                class="px-4 py-3 border-b border-white/[0.07] bg-white/[0.02] text-sm text-slate-400 flex gap-4"
            >
                <span>Completed: {{ completedCount }}</span>
                <span>Issues: {{ erroredCount }}</span>
                <span>Total: {{ rows.length }}</span>
                <span>Shown: {{ filteredRows.length }}</span>
            </div>
            <div class="divide-y divide-white/[0.07]">
                <div
                    v-for="row in filteredRows"
                    :key="row.userId || row.username || row.rawInput"
                    class="px-4 py-3 grid lg:grid-cols-[1.3fr,0.9fr,2fr,1fr] gap-3 items-start"
                >
                    <div>
                        <p class="font-semibold text-sm text-slate-100">
                            {{ getRowTitle(row) }}
                        </p>
                        <p
                            v-if="row.rawInput !== (row.prediction?.target_username || row.username || row.userId || row.rawInput)"
                            class="text-[11px] text-slate-500 mt-1 break-all"
                        >
                            {{ row.rawInput }}
                        </p>
                        <RouterLink
                            v-if="row.prediction && (row.prediction.target_username || row.username)"
                            :to="{
                                name: 'discovery',
                                params: {
                                    username:
                                        row.prediction.target_username ||
                                        row.username,
                                },
                            }"
                            class="text-xs text-cyan-400 hover:text-cyan-300 font-medium"
                        >
                            Open discovery
                        </RouterLink>
                        <p
                            v-if="hasAltFollowback(row)"
                            class="mt-1 inline-flex items-center px-2 py-1 rounded-full text-[10px] font-semibold border bg-amber-500/15 text-amber-300 border-amber-500/30"
                        >
                            Alt acc follows you
                        </p>
                    </div>

                    <div>
                        <PredictionStatusBadge :status="row.status" />
                    </div>

                    <div class="space-y-2">
                        <p class="text-sm text-slate-300">
                            {{ row.message }}
                        </p>
                        <TaskProgressBar :task="row.task" />
                    </div>

                    <div class="lg:justify-self-end">
                        <ProbabilityChip
                            :probability="row.prediction?.probability ?? null"
                            :confidence="row.prediction?.confidence ?? null"
                        />
                        <p
                            v-if="
                                row.prediction &&
                                row.prediction.target_profile_id
                            "
                            class="text-[11px] text-slate-500 mt-1 text-right"
                        >
                            {{
                                formatProbability(
                                    row.prediction?.probability ?? null,
                                )
                            }}
                        </p>
                    </div>
                </div>
            </div>
        </div>
    </section>
</template>
