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
            return "bg-blue-50 border-blue-200 text-blue-800";
        case "warning":
            return "bg-amber-50 border-amber-200 text-amber-800";
        case "error":
            return "bg-rose-50 border-rose-200 text-rose-700";
        default:
            return "bg-gray-50 border-gray-200 text-gray-700";
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
