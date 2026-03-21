<script setup lang="ts">
import { computed } from "vue";
import type { PredictionStatus } from "../../types/prediction";

const props = defineProps<{
    status: PredictionStatus | "ready" | "invalid";
}>();

const badgeClass = computed(() => {
    switch (props.status) {
        case "completed":
            return "bg-emerald-500/15 text-emerald-300 border border-emerald-500/25";
        case "queued":
            return "bg-amber-500/15 text-amber-300 border border-amber-500/25";
        case "running":
            return "bg-sky-500/15 text-sky-300 border border-sky-500/25";
        case "cancelled":
            return "bg-slate-700/40 text-slate-300 border border-slate-600/60";
        case "error":
        case "invalid":
            return "bg-rose-500/15 text-rose-300 border border-rose-500/25";
        default:
            return "bg-slate-700/30 text-slate-300 border border-slate-600/50";
    }
});

const label = computed(() => props.status.replace("_", " "));
</script>

<template>
    <span
        :class="badgeClass"
        class="inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold uppercase tracking-wide"
    >
        {{ label }}
    </span>
</template>
