<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { RouterLink } from "vue-router";
import PredictionStatePanel from "../components/prediction/PredictionStatePanel.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import { setBulkBatchRunning } from "../services/uiTaskState";
import type {
    FollowBackPredictionResponse,
    PredictionRecord,
    PredictionTask,
} from "../types/prediction";

const props = defineProps<{
    profileId: string;
}>();

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

    const deduped: BatchRow[] = [];
    const seen = new Set<string>();
    for (const token of tokens) {
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
        if (!seen.has(dedupeKey)) {
            seen.add(dedupeKey);
            deduped.push({
                rawInput: token,
                username,
                userId,
                status,
                message,
                prediction: null,
                task: null,
            });
        }
    }
    return deduped;
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
            row.message = task.error || "Prediction refresh failed.";
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

async function executeRow(row: BatchRow) {
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
        const message =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error ||
            "Could not request prediction for this target.";
        row.status = "error";
        row.message = message;
    }
}

async function runBatch() {
    rows.value = parseTargets(input.value);

    if (!rows.value.length) {
        return;
    }

    isRunning.value = true;
    setBulkBatchRunning(true);
    try {
        const queue = rows.value.filter((row) => row.status === "ready");
        const workers = Array.from({ length: Math.min(3, queue.length) }).map(
            async () => {
                while (queue.length && !disposed) {
                    const row = queue.shift();
                    if (!row) {
                        return;
                    }
                    await executeRow(row);
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

function formatProbability(value: number | null) {
    if (value === null || Number.isNaN(value)) return "--";
    return `${Math.round(value * 100)}%`;
}

function clearResults() {
    rows.value = [];
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
            <div
                class="px-4 py-3 border-b border-white/[0.07] bg-white/[0.02] text-sm text-slate-400 flex gap-4"
            >
                <span>Completed: {{ completedCount }}</span>
                <span>Issues: {{ erroredCount }}</span>
                <span>Total: {{ rows.length }}</span>
            </div>
            <div class="divide-y divide-white/[0.07]">
                <div
                    v-for="row in rows"
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
