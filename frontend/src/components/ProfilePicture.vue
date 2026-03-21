<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{
    pkId: string;
    profileId: string;
    alt: string;
}>();

const hasError = ref(false);
</script>

<template>
    <div
        class="rounded-full overflow-hidden bg-slate-800 shrink-0 flex items-center justify-center"
    >
        <img
            v-if="!hasError"
            :src="`/api/image/${props.pkId}?profile_id=${props.profileId}`"
            :alt="props.alt"
            class="w-full h-full object-cover"
            loading="lazy"
            @error="hasError = true"
        />
        <!-- Fallback avatar when image is unavailable -->
        <span v-else class="text-slate-500 text-xl select-none">👤</span>
    </div>
</template>
