<script setup lang="ts">
import { computed, onBeforeUnmount, ref } from "vue";
import { RouterLink } from "vue-router";
import PredictionStatePanel from "../components/prediction/PredictionStatePanel.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import type {
    FollowBackPredictionResponse,
    PredictionRecord,
    PredictionTask,
} from "../types/prediction";

const props = defineProps<{
    profileId: string;
}>();

interface BatchRow {
    username: string;
    status: "ready" | "queued" | "running" | "completed" | "error" | "invalid";
    message: string;
    prediction: PredictionRecord | null;
    task: PredictionTask | null;
}

const input = ref("");
const isRunning = ref(false);
const rows = ref<BatchRow[]>([]);
const batchPlaceholder = ["example_user", "second.user", "third_user"].join(
    "\n",
);
let disposed = false;

onBeforeUnmount(() => {
    disposed = true;
});

const validUsernamePattern = /^[a-zA-Z0-9._]+$/;

const completedCount = computed(
    () => rows.value.filter((row) => row.status === "completed").length,
);

const erroredCount = computed(
    () =>
        rows.value.filter(
            (row) => row.status === "error" || row.status === "invalid",
        ).length,
);

function parseUsernames(raw: string): string[] {
    const tokens = raw
        .split(/[\n,]/)
        .map((token) => token.trim())
        .filter(Boolean);

    const deduped: string[] = [];
    const seen = new Set<string>();
    for (const token of tokens) {
        const normalized = token.toLowerCase();
        if (!seen.has(normalized)) {
            seen.add(normalized);
            deduped.push(token);
        }
    }
    return deduped;
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
    if (!validUsernamePattern.test(row.username)) {
        row.status = "invalid";
        row.message = "Username contains unsupported characters.";
        return;
    }

    try {
        const response: FollowBackPredictionResponse =
            await api.createFollowBackPrediction({
                username: row.username,
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
            "Could not request prediction for this username.";
        row.status = "error";
        row.message = message;
    }
}

async function runBatch() {
    const usernames = parseUsernames(input.value);
    rows.value = usernames.map((username) => ({
        username,
        status: "ready",
        message: "Ready",
        prediction: null,
        task: null,
    }));

    if (!rows.value.length) {
        return;
    }

    isRunning.value = true;
    const queue = [...rows.value];
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
    if (!disposed) {
        isRunning.value = false;
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
    <section class="space-y-5">
        <div class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
            <h2 class="text-lg font-bold text-gray-900">
                Bulk Follow-Back Predictions
            </h2>
            <p class="text-sm text-gray-500 mt-1">
                Paste Instagram usernames separated by new lines or commas to
                check follow-back probability.
            </p>

            <textarea
                v-model="input"
                rows="6"
                class="mt-4 w-full border border-gray-200 rounded-xl px-3 py-2 text-sm"
                :placeholder="batchPlaceholder"
            />

            <div class="mt-3 flex items-center justify-between gap-3">
                <p class="text-xs text-gray-500">
                    Active profile: {{ props.profileId }}
                </p>
                <div class="flex items-center gap-2">
                    <button
                        v-if="rows.length"
                        class="px-4 py-2 rounded-lg bg-gray-100 text-gray-700 text-sm font-semibold hover:bg-gray-200"
                        @click="clearResults"
                    >
                        Clear
                    </button>
                    <button
                        :disabled="isRunning"
                        class="px-4 py-2 rounded-lg bg-indigo-600 text-white text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
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
            message="Paste one or more usernames to queue predictions. Cached results return immediately and queued refreshes will update progressively."
            tone="info"
        />

        <div
            v-if="rows.length"
            class="bg-white border border-gray-200 rounded-2xl shadow-sm overflow-hidden"
        >
            <div
                class="px-4 py-3 border-b border-gray-100 bg-gray-50 text-sm text-gray-600 flex gap-4"
            >
                <span>Completed: {{ completedCount }}</span>
                <span>Issues: {{ erroredCount }}</span>
                <span>Total: {{ rows.length }}</span>
            </div>
            <div class="divide-y divide-gray-100">
                <div
                    v-for="row in rows"
                    :key="row.username"
                    class="px-4 py-3 grid lg:grid-cols-[1.3fr,0.9fr,2fr,1fr] gap-3 items-start"
                >
                    <div>
                        <p class="font-semibold text-sm text-gray-900">
                            @{{ row.username }}
                        </p>
                        <RouterLink
                            v-if="row.prediction"
                            :to="{
                                name: 'discovery',
                                params: { username: row.username },
                            }"
                            class="text-xs text-teal-700 hover:text-teal-900 font-medium"
                        >
                            Open discovery
                        </RouterLink>
                    </div>

                    <div>
                        <PredictionStatusBadge :status="row.status" />
                    </div>

                    <div class="space-y-2">
                        <p class="text-sm text-gray-700">
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
                            class="text-[11px] text-gray-400 mt-1 text-right"
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
