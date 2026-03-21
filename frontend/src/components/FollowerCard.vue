<script setup lang="ts">
import { RouterLink } from "vue-router";
import ProfilePicture from "./ProfilePicture.vue";
import type { FollowerRecord } from "../types/follower";

defineProps<{
    follower: FollowerRecord;
    profileId: string
    /** Use a tighter layout when rendered inside a modal or diff panel */
    compact?: boolean;
}>();
</script>

<template>
    <div
        :class="compact ? 'p-3 gap-3' : 'p-4 gap-4'"
        class="bg-[#16213a] rounded-xl border border-white/[0.07] flex items-center card-hover transition-all"
    >
        <ProfilePicture
            :pk-id="follower.pk_id"
            :profile-id="profileId"
            :alt="follower.username"
            :class="compact ? 'w-9 h-9' : 'w-12 h-12'"
        />

        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
                <span class="font-semibold text-slate-100 text-sm truncate">
                    @{{ follower.username }}
                </span>
                <span
                    v-if="follower.is_private"
                    class="text-xs bg-white/[0.07] text-slate-400 px-1.5 py-0.5 rounded-full shrink-0"
                >
                    Private
                </span>
            </div>
            <p
                v-if="follower.full_name"
                class="text-xs text-slate-500 truncate mt-0.5"
            >
                {{ follower.full_name }}
            </p>
        </div>

        <div class="shrink-0 flex items-center gap-2">
            <RouterLink
                :to="{ name: 'discovery', params: { username: follower.username } }"
                class="text-xs text-cyan-400 hover:text-cyan-300 font-medium px-2 py-1 rounded hover:bg-cyan-500/10 transition-colors"
            >
                Discover
            </RouterLink>

            <a
                :href="`https://www.instagram.com/${follower.username}`"
                target="_blank"
                rel="noopener noreferrer"
                class="text-xs text-violet-400 hover:text-violet-300 font-medium px-2 py-1 rounded hover:bg-violet-500/10 transition-colors"
            >
                View ↗
            </a>
        </div>
    </div>
</template>
