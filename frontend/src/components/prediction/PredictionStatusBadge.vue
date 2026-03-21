<script setup lang="ts">
import { computed } from "vue";
import type { PredictionStatus } from "../../types/prediction";

const props = defineProps<{
    status: PredictionStatus | "ready" | "invalid";
}>();

const badgeClass = computed(() => {
    switch (props.status) {
        case "completed":
            return "bg-emerald-100 text-emerald-800";
        case "queued":
            return "bg-amber-100 text-amber-800";
        case "running":
            return "bg-sky-100 text-sky-800";
        case "cancelled":
            return "bg-gray-200 text-gray-700";
        case "error":
        case "invalid":
            return "bg-rose-100 text-rose-800";
        default:
            return "bg-gray-100 text-gray-700";
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
