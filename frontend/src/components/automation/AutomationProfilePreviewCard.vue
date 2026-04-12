<script setup lang="ts">
import { computed } from "vue";
import ProfilePicture from "../ProfilePicture.vue";
import type { AutomationPreviewItem } from "../../types/automation";

const props = defineProps<{
    item: AutomationPreviewItem;
    profileId: string;
    showStatus?: boolean;
}>();

const displayName = computed(
    () =>
        props.item.display_username ??
        props.item.normalized_username ??
        props.item.raw_input,
);
</script>

<template>
    <article
        class="flex items-center gap-3 rounded-xl border border-white/8 bg-slate-950/35 px-3 py-2"
    >
        <ProfilePicture
            v-if="item.normalized_user_id"
            :pk-id="item.normalized_user_id"
            :profile-id="profileId"
            :alt="displayName"
            class="h-10 w-10"
        />
        <div
            v-else
            class="h-10 w-10 overflow-hidden rounded-full bg-slate-800 shrink-0 flex items-center justify-center"
        >
            <span class="text-slate-500 text-lg select-none">👤</span>
        </div>

        <div class="min-w-0 flex-1">
            <p class="truncate text-sm font-semibold text-slate-100">
                @{{ displayName }}
            </p>
        </div>

        <span
            v-if="showStatus && item.status"
            class="shrink-0 rounded-full border border-white/10 bg-white/5 px-2 py-0.5 text-[10px] uppercase tracking-wide text-slate-300"
        >
            {{ item.status }}
        </span>
    </article>
</template>