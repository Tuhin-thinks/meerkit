<script setup lang="ts">
import { computed } from "vue";
import type { PredictionTask } from "../../types/prediction";

const props = defineProps<{
    task: PredictionTask | null;
}>();

const width = computed(
    () => `${Math.max(8, Math.round((props.task?.progress ?? 0) * 100))}%`,
);
</script>

<template>
    <div
        v-if="task && (task.status === 'queued' || task.status === 'running')"
        class="space-y-1"
    >
        <div class="h-2 rounded-full bg-gray-100 overflow-hidden">
            <div
                :style="{ width }"
                class="h-full rounded-full bg-gradient-to-r from-sky-500 to-indigo-500 transition-all"
            />
        </div>
        <p class="text-[11px] text-gray-500">
            {{ task.status }} · {{ Math.round((task.progress || 0) * 100) }}%
        </p>
    </div>
</template>
