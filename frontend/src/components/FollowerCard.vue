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
        class="bg-white rounded-xl border border-gray-100 flex items-center hover:shadow-md transition-shadow"
    >
        <ProfilePicture
            :pk-id="follower.pk_id"
            :profile-id="profileId"
            :alt="follower.username"
            :class="compact ? 'w-9 h-9' : 'w-12 h-12'"
        />

        <div class="flex-1 min-w-0">
            <div class="flex items-center gap-1.5 flex-wrap">
                <span class="font-semibold text-gray-900 text-sm truncate">
                    @{{ follower.username }}
                </span>
                <span
                    v-if="follower.is_private"
                    class="text-xs bg-gray-100 text-gray-500 px-1.5 py-0.5 rounded-full shrink-0"
                >
                    Private
                </span>
            </div>
            <p
                v-if="follower.full_name"
                class="text-xs text-gray-500 truncate mt-0.5"
            >
                {{ follower.full_name }}
            </p>
        </div>

        <div class="shrink-0 flex items-center gap-2">
            <RouterLink
                :to="{ name: 'discovery', params: { username: follower.username } }"
                class="text-xs text-teal-700 hover:text-teal-900 font-medium px-2 py-1 rounded hover:bg-teal-50 transition-colors"
            >
                Discover
            </RouterLink>

            <a
                :href="`https://www.instagram.com/${follower.username}`"
                target="_blank"
                rel="noopener noreferrer"
                class="text-xs text-indigo-600 hover:text-indigo-800 font-medium px-2 py-1 rounded hover:bg-indigo-50 transition-colors"
            >
                View ↗
            </a>
        </div>
    </div>
</template>
