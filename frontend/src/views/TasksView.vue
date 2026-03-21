<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import { useUiTaskState } from "../services/uiTaskState";
import type { TaskSummary } from "../types/prediction";

const props = defineProps<{
    profileId: string;
}>();

const queryClient = useQueryClient();
const terminationNoticeByTaskId = ref<Record<string, string>>({});
const terminatingTaskId = ref<string | null>(null);
const { isBulkBatchRunning } = useUiTaskState();

const { data: taskList, isLoading } = useQuery({
    queryKey: ["tasks", props.profileId],
    queryFn: api.listTasks,
    refetchInterval: 2000,
    refetchOnWindowFocus: false,
});

const { data: scanStatus } = useQuery({
    queryKey: ["scan", "status", props.profileId],
    queryFn: api.getScanStatus,
    refetchInterval: 2000,
    refetchOnWindowFocus: false,
});

const tasks = computed(() => {
    const merged = [...(taskList.value?.tasks ?? [])];

    const scanTaskId = `scan:unknown:${props.profileId}`;
    const hasScanTask = merged.some(
        (task) =>
            task.source === "scan" && task.target_profile_id === props.profileId,
    );
    const scanTaskStatus = scanStatus.value?.status;
    if (
        !hasScanTask &&
        scanStatus.value &&
        (scanTaskStatus === "running" || scanTaskStatus === "cancelled")
    ) {
        merged.unshift({
            task_id: scanTaskId,
            task_type: "scan",
            source: "scan",
            status: scanTaskStatus,
            progress: null,
            error: scanStatus.value.error,
            queued_at: scanStatus.value.started_at,
            started_at: scanStatus.value.started_at,
            completed_at: null,
            target_profile_id: props.profileId,
            target_username: null,
            can_cancel: scanTaskStatus === "running",
            metric_label: null,
            metric_value: null,
        });
    }

    if (isBulkBatchRunning.value) {
        merged.unshift({
            task_id: "local:bulk-batch",
            task_type: "bulk_prediction",
            source: "prediction",
            status: "running",
            progress: null,
            error: null,
            queued_at: null,
            started_at: null,
            completed_at: null,
            target_profile_id: props.profileId,
            target_username: null,
            can_cancel: false,
            metric_label: "state",
            metric_value: "processing",
        });
    }

    return merged;
});

const runningCount = computed(
    () =>
        tasks.value.filter((task) => ["queued", "running"].includes(task.status))
            .length,
);

const { mutateAsync: terminateTask } = useMutation({
    mutationFn: async (task: TaskSummary) => {
        if (task.source === "scan") {
            return api.cancelScan();
        }
        return api.cancelPredictionTask(task.task_id);
    },
    onSuccess: async (_, task) => {
        terminationNoticeByTaskId.value = {
            ...terminationNoticeByTaskId.value,
            [task.task_id]: "Termination requested. Task marked as cancelled.",
        };
        await queryClient.invalidateQueries({
            queryKey: ["tasks", props.profileId],
        });
    },
    onError: (error, task) => {
        const message =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error || "Could not terminate this task right now.";
        terminationNoticeByTaskId.value = {
            ...terminationNoticeByTaskId.value,
            [task.task_id]: message,
        };
    },
});

function formatDate(iso: string | null | undefined): string {
    if (!iso) {
        return "--";
    }
    return new Date(iso).toLocaleString();
}

function toPredictionTask(task: TaskSummary) {
    if (typeof task.progress !== "number") {
        return null;
    }
    return {
        task_id: task.task_id,
        prediction_id: "",
        task_type: task.task_type,
        status: task.status,
        progress: task.progress,
        error: task.error,
        queued_at: task.queued_at || "",
        started_at: task.started_at,
        completed_at: task.completed_at,
    };
}

async function onTerminate(task: TaskSummary) {
    terminatingTaskId.value = task.task_id;
    try {
        await terminateTask(task);
    } finally {
        terminatingTaskId.value = null;
    }
}
</script>

<template>
    <section class="space-y-5 fade-in">
        <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6">
            <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 class="text-xl font-bold font-display text-gradient">
                        Tasks
                    </h2>
                    <p class="text-sm text-slate-400 mt-1">
                        Monitor active background work and terminate tasks when
                        needed.
                    </p>
                </div>
                <span
                    class="inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide bg-violet-500/10 text-violet-400 border border-violet-500/20"
                >
                    {{ runningCount }} running
                </span>
            </div>
        </div>

        <div v-if="isLoading" class="grid gap-3">
            <div
                v-for="i in 3"
                :key="i"
                class="h-24 bg-[#16213a] rounded-xl border border-white/[0.06] shimmer"
            />
        </div>

        <div
            v-else-if="!tasks.length"
            class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-10 text-center"
        >
            <p class="font-semibold text-slate-300">No active tasks</p>
            <p class="text-sm mt-1 text-slate-500">
                Start a scan or prediction refresh to see live task updates
                here.
            </p>
        </div>

        <div v-else class="grid gap-3">
            <article
                v-for="task in tasks"
                :key="task.task_id"
                class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-xl shadow-black/20 p-4 card-hover"
            >
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                            <p
                                class="text-sm font-semibold text-slate-100 truncate"
                            >
                                {{ task.task_type.replace(/_/g, " ") }}
                            </p>
                            <span
                                class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-white/[0.06] text-slate-400"
                            >
                                {{ task.source }}
                            </span>
                        </div>
                        <p class="text-xs text-slate-500 mt-1 break-all">
                            Target ID: {{ task.target_profile_id || "--" }}
                        </p>
                        <p class="text-xs text-slate-500">
                            Started:
                            {{ formatDate(task.started_at || task.queued_at) }}
                        </p>
                    </div>

                    <div class="flex items-center gap-2">
                        <PredictionStatusBadge :status="task.status" />
                        <button
                            v-if="task.can_cancel"
                            :disabled="terminatingTaskId === task.task_id"
                            class="btn-danger px-3 py-1.5 rounded-lg text-xs font-semibold disabled:opacity-50"
                            @click="onTerminate(task)"
                        >
                            {{
                                terminatingTaskId === task.task_id
                                    ? "Terminating..."
                                    : "Terminate"
                            }}
                        </button>
                    </div>
                </div>

                <div class="mt-3 space-y-1">
                    <TaskProgressBar :task="toPredictionTask(task)" />
                    <p v-if="task.metric_label" class="text-xs text-slate-500">
                        {{ task.metric_label }}: {{ task.metric_value ?? "--" }}
                    </p>
                    <p v-if="task.error" class="text-xs text-rose-400">
                        {{ task.error }}
                    </p>
                    <p
                        v-if="terminationNoticeByTaskId[task.task_id]"
                        class="text-xs text-emerald-400"
                    >
                        {{ terminationNoticeByTaskId[task.task_id] }}
                    </p>
                </div>
            </article>
        </div>
    </section>
</template>
