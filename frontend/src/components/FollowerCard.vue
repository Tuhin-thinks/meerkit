<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from "vue";
import { RouterLink } from "vue-router";
import ProfilePicture from "./ProfilePicture.vue";
import { addAlternativeAccountLinks } from "../services/api";
import type { FollowerRecord } from "../types/follower";

const props = withDefaults(
    defineProps<{
        follower: FollowerRecord;
        profileId: string;
        /** Use a tighter layout when rendered inside a modal or diff panel */
        compact?: boolean;
        showLinkedAccountsAction?: boolean;
    }>(),
    {
        compact: false,
        showLinkedAccountsAction: false,
    },
);

const emit = defineEmits<{
    (e: "linked-accounts-saved", primaryUsername: string): void;
}>();

const linkedAccountsInputRef = ref<HTMLTextAreaElement | null>(null);
const isLinkedAccountsDialogOpen = ref(false);
const linkedAccountsInput = ref("");
const linkedAccountsError = ref("");
const linkedAccountsSuccess = ref("");
const isSavingLinkedAccounts = ref(false);

const altFollowbackAssessment = computed(
    () => props.follower.alt_followback_assessment ?? null,
);
const matchedAltUsernamesLabel = computed(() => {
    const usernames = altFollowbackAssessment.value?.matched_alt_usernames;
    if (!Array.isArray(usernames) || !usernames.length) {
        return "";
    }
    return usernames.slice(0, 3).join(", ");
});

let successTimer: number | null = null;

function clearSuccessTimer() {
    if (successTimer !== null) {
        window.clearTimeout(successTimer);
        successTimer = null;
    }
}

function showSuccessMessage(message: string) {
    clearSuccessTimer();
    linkedAccountsSuccess.value = message;
    successTimer = window.setTimeout(() => {
        linkedAccountsSuccess.value = "";
        successTimer = null;
    }, 2400);
}

function parseUniqueEntries(raw: string) {
    return Array.from(
        new Set(
            raw
                .split(/[\n,]/)
                .map((value) => value.trim())
                .filter(Boolean),
        ),
    );
}

function openLinkedAccountsDialog() {
    linkedAccountsError.value = "";
    linkedAccountsSuccess.value = "";
    linkedAccountsInput.value = "";
    isLinkedAccountsDialogOpen.value = true;
    void nextTick(() => {
        linkedAccountsInputRef.value?.focus();
    });
}

function closeLinkedAccountsDialog() {
    isLinkedAccountsDialogOpen.value = false;
    linkedAccountsError.value = "";
}

async function saveLinkedAccounts() {
    const accounts = parseUniqueEntries(linkedAccountsInput.value);
    if (!accounts.length) {
        linkedAccountsError.value =
            "Enter at least one linked account username, profile link, or user ID.";
        return;
    }

    isSavingLinkedAccounts.value = true;
    linkedAccountsError.value = "";
    try {
        await addAlternativeAccountLinks({
            primary_account: props.follower.username,
            alternative_accounts: accounts,
        });
        closeLinkedAccountsDialog();
        showSuccessMessage("Linked accounts saved.");
        emit("linked-accounts-saved", props.follower.username);
    } catch (error: unknown) {
        linkedAccountsError.value =
            (error as { response?: { data?: { error?: string } } })?.response
                ?.data?.error || "Could not save linked accounts right now.";
    } finally {
        isSavingLinkedAccounts.value = false;
    }
}

function handleDocumentKeydown(event: KeyboardEvent) {
    if (event.key === "Escape") {
        closeLinkedAccountsDialog();
    }
}

watch(isLinkedAccountsDialogOpen, (open) => {
    if (open) {
        document.addEventListener("keydown", handleDocumentKeydown);
        document.body.style.overflow = "hidden";
        return;
    }
    document.removeEventListener("keydown", handleDocumentKeydown);
    document.body.style.overflow = "";
});

onBeforeUnmount(() => {
    clearSuccessTimer();
    document.removeEventListener("keydown", handleDocumentKeydown);
    document.body.style.overflow = "";
});
</script>

<template>
    <div
        :class="compact ? 'p-3 gap-3' : 'p-4 gap-4'"
        class="group relative bg-[#16213a] rounded-xl border border-white/[0.07] flex items-center card-hover transition-all"
    >
        <ProfilePicture
            :pk-id="follower.pk_id"
            :profile-id="profileId"
            :alt="follower.username"
            :cache-key="follower.profile_pic_id"
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
                <span
                    v-if="altFollowbackAssessment?.is_alt_account_following_you"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-amber-500/15 text-amber-300 border-amber-500/30 shrink-0"
                >
                    Linked acc follows you
                    <span
                        v-if="matchedAltUsernamesLabel"
                        class="ml-1 text-amber-200/80 font-normal"
                    >
                        ({{ matchedAltUsernamesLabel }})
                    </span>
                </span>
                <span
                    v-if="showLinkedAccountsAction && follower.account_not_accessible"
                    class="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-semibold border bg-rose-500/15 text-rose-300 border-rose-500/30 shrink-0"
                >
                    Account not accessible
                </span>
            </div>
            <p
                v-if="follower.full_name"
                class="text-xs text-slate-500 truncate mt-0.5"
            >
                {{ follower.full_name }}
            </p>
        </div>

        <div class="shrink-0 relative flex items-center gap-2">
            <button
                v-if="showLinkedAccountsAction"
                type="button"
                class="inline-flex items-center rounded-full border border-sky-400/25 bg-sky-500/10 px-2.5 py-1 text-[11px] font-medium text-sky-300 transition-all duration-150 hover:border-sky-300/40 hover:bg-sky-500/15 hover:text-sky-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-sky-300/40"
                :class="isLinkedAccountsDialogOpen ? 'opacity-100' : 'opacity-0 group-hover:opacity-100 group-focus-within:opacity-100'"
                @click.stop="openLinkedAccountsDialog"
            >
                + linked accounts
            </button>

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

        <Teleport to="body">
            <div
                v-if="isLinkedAccountsDialogOpen && showLinkedAccountsAction"
                class="fixed inset-0 z-50 flex items-center justify-center bg-black/60 p-4 backdrop-blur-sm"
                @click="closeLinkedAccountsDialog"
            >
                <div
                    class="w-full max-w-md rounded-2xl border border-white/10 bg-[#1b2030]/95 p-4 shadow-2xl shadow-black/50 backdrop-blur"
                    @click.stop
                >
                    <p class="text-sm font-semibold text-slate-100">
                        Add linked accounts
                    </p>
                    <p class="mt-1 text-[11px] text-slate-400">
                        Primary account: @{{ follower.username }}
                    </p>
                    <textarea
                        ref="linkedAccountsInputRef"
                        v-model="linkedAccountsInput"
                        rows="3"
                        class="input-dark mt-3 text-sm"
                        placeholder="Enter username, profile link, or user ID"
                    />
                    <p
                        v-if="linkedAccountsError"
                        class="mt-2 text-[11px] text-rose-300"
                    >
                        {{ linkedAccountsError }}
                    </p>
                    <div class="mt-3 flex items-center justify-end gap-2">
                        <button
                            type="button"
                            class="rounded-lg border border-white/10 px-3 py-1.5 text-xs font-semibold text-slate-300 transition-colors hover:bg-white/[0.05]"
                            :disabled="isSavingLinkedAccounts"
                            @click="closeLinkedAccountsDialog"
                        >
                            Cancel
                        </button>
                        <button
                            type="button"
                            class="rounded-lg bg-emerald-500 px-3 py-1.5 text-xs font-semibold text-white transition-colors hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
                            :disabled="isSavingLinkedAccounts"
                            @click="saveLinkedAccounts"
                        >
                            {{ isSavingLinkedAccounts ? "Adding..." : "Add" }}
                        </button>
                    </div>
                </div>
            </div>
        </Teleport>
    </div>
</template>
