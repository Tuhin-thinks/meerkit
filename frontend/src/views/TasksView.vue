<script setup lang="ts">
import { computed, ref } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import TaskProgressBar from "../components/prediction/TaskProgressBar.vue";
import * as api from "../services/api";
import type { TaskSummary } from "../types/prediction";

const props = defineProps<{
    profileId: string;
}>();

const queryClient = useQueryClient();
const terminationNoticeByTaskId = ref<Record<string, string>>({});
const terminatingTaskId = ref<string | null>(null);

const { data: taskList, isLoading } = useQuery({
    queryKey: ["tasks", props.profileId],
    queryFn: api.listTasks,
    refetchInterval: (query) => {
        const count =
            (query.state.data as { running_count?: number } | undefined)
                ?.running_count ?? 0;
        return count > 0 ? 3000 : 6000;
    },
    refetchOnWindowFocus: false,
});

const tasks = computed(() => taskList.value?.tasks ?? []);
const runningCount = computed(() => taskList.value?.running_count ?? 0);

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
    <section class="space-y-5">
        <div class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
            <div class="flex flex-wrap items-center justify-between gap-3">
                <div>
                    <h2 class="text-lg font-bold text-gray-900">
                        Running Tasks
                    </h2>
                    <p class="text-sm text-gray-500 mt-1">
                        Monitor active background work and terminate tasks when
                        needed.
                    </p>
                </div>
                <span
                    class="inline-flex items-center rounded-full px-3 py-1 text-xs font-semibold uppercase tracking-wide bg-indigo-100 text-indigo-800"
                >
                    {{ runningCount }} running
                </span>
            </div>
        </div>

        <div v-if="isLoading" class="grid gap-3">
            <div
                v-for="i in 3"
                :key="i"
                class="h-24 bg-white rounded-xl border border-gray-100 animate-pulse"
            />
        </div>

        <div
            v-else-if="!tasks.length"
            class="bg-white border border-gray-200 rounded-2xl shadow-sm p-10 text-center text-gray-500"
        >
            <p class="font-semibold text-gray-700">No active tasks</p>
            <p class="text-sm mt-1">
                Start a scan or prediction refresh to see live task updates
                here.
            </p>
        </div>

        <div v-else class="grid gap-3">
            <article
                v-for="task in tasks"
                :key="task.task_id"
                class="bg-white border border-gray-200 rounded-2xl shadow-sm p-4"
            >
                <div class="flex flex-wrap items-start justify-between gap-3">
                    <div class="min-w-0">
                        <div class="flex flex-wrap items-center gap-2">
                            <p
                                class="text-sm font-semibold text-gray-900 truncate"
                            >
                                {{ task.task_type.replace(/_/g, " ") }}
                            </p>
                            <span
                                class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-gray-100 text-gray-600"
                            >
                                {{ task.source }}
                            </span>
                        </div>
                        <p class="text-xs text-gray-500 mt-1 break-all">
                            Target ID: {{ task.target_profile_id || "--" }}
                        </p>
                        <p class="text-xs text-gray-500">
                            Started:
                            {{ formatDate(task.started_at || task.queued_at) }}
                        </p>
                    </div>

                    <div class="flex items-center gap-2">
                        <PredictionStatusBadge :status="task.status" />
                        <button
                            v-if="task.can_cancel"
                            :disabled="terminatingTaskId === task.task_id"
                            class="px-3 py-1.5 rounded-lg bg-rose-50 text-rose-700 text-xs font-semibold hover:bg-rose-100 disabled:opacity-50"
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
                    <p v-if="task.metric_label" class="text-xs text-gray-500">
                        {{ task.metric_label }}: {{ task.metric_value ?? "--" }}
                    </p>
                    <p v-if="task.error" class="text-xs text-rose-600">
                        {{ task.error }}
                    </p>
                    <p
                        v-if="terminationNoticeByTaskId[task.task_id]"
                        class="text-xs text-emerald-700"
                    >
                        {{ terminationNoticeByTaskId[task.task_id] }}
                    </p>
                </div>
            </article>
        </div>
    </section>
</template>
