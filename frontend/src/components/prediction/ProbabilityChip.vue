<script setup lang="ts">
import { computed } from "vue";

const props = defineProps<{
    probability: number | null;
    confidence?: number | null;
    size?: "sm" | "lg";
}>();

const label = computed(() => {
    if (props.probability === null || Number.isNaN(props.probability)) {
        return "--";
    }
    return `${Math.round(props.probability * 100)}%`;
});

const confidenceLabel = computed(() => {
    if (
        props.confidence === undefined ||
        props.confidence === null ||
        Number.isNaN(props.confidence)
    ) {
        return null;
    }
    return `conf. ${Math.round(props.confidence * 100)}%`;
});

const toneClass = computed(() => {
    const value = props.probability ?? -1;
    if (value >= 0.75)
        return "bg-emerald-50 text-emerald-800 border-emerald-200";
    if (value >= 0.45) return "bg-amber-50 text-amber-800 border-amber-200";
    if (value >= 0) return "bg-rose-50 text-rose-800 border-rose-200";
    return "bg-gray-50 text-gray-500 border-gray-200";
});

const sizeClass = computed(() =>
    props.size === "lg" ? "px-4 py-3 text-left" : "px-3 py-2 text-right",
);
</script>

<template>
    <div :class="[toneClass, sizeClass]" class="rounded-xl border">
        <p
            :class="
                props.size === 'lg'
                    ? 'text-xs uppercase tracking-wide'
                    : 'text-[11px] uppercase tracking-wide'
            "
        >
            Follow-back
        </p>
        <p
            :class="
                props.size === 'lg'
                    ? 'text-2xl font-bold mt-1'
                    : 'text-sm font-bold'
            "
        >
            {{ label }}
        </p>
        <p v-if="confidenceLabel" class="text-[11px] mt-1 opacity-80">
            {{ confidenceLabel }}
        </p>
    </div>
</template>
