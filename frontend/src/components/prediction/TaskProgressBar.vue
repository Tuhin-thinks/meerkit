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
        <div class="h-2 rounded-full bg-slate-800 overflow-hidden">
            <div
                :style="{ width }"
                class="h-full rounded-full bg-gradient-to-r from-cyan-500 to-violet-500 transition-all"
            />
        </div>
        <p class="text-[11px] text-slate-500">
            {{ task.status }} · {{ Math.round((task.progress || 0) * 100) }}%
        </p>
    </div>
</template>
