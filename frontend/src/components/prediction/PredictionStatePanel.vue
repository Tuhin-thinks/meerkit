<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
    title: string;
    message: string;
    tone?: "neutral" | "info" | "warning" | "error";
}>();

const panelClass = computed(() => {
    switch (props.tone) {
        case "info":
            return "bg-blue-500/10 border-blue-500/25 text-blue-300";
        case "warning":
            return "bg-amber-500/10 border-amber-500/25 text-amber-300";
        case "error":
            return "bg-rose-500/10 border-rose-500/25 text-rose-300";
        default:
            return "bg-slate-800/60 border-slate-700 text-slate-300";
    }
});
</script>

<template>
    <div :class="panelClass" class="rounded-xl border p-4">
        <p class="text-sm font-semibold">{{ title }}</p>
        <p class="text-sm mt-1 opacity-90">{{ message }}</p>
        <div v-if="$slots.default" class="mt-3">
            <slot />
        </div>
    </div>
</template>
