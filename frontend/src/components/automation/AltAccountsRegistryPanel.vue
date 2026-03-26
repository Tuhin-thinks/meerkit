<script setup lang="ts">
import { computed, onMounted, ref, watch } from "vue";
import {
    addAlternativeAccountLinks,
    getAlternativeAccountLinks,
    removeAlternativeAccountLink,
} from "../../services/api";
import type { AlternativeAccountLinkEntry } from "../../types/automation";

const props = withDefaults(
    defineProps<{
        title?: string;
        description?: string;
        primaryPlaceholder?: string;
        lockedPrimaryAccount?: string | null;
        saveButtonLabel?: string;
        compact?: boolean;
    }>(),
    {
        title: "Linked Accounts Registry",
        description:
            "Organize your accounts in a tree structure. Expand primary accounts to see their linked alternatives.",
        primaryPlaceholder: "Primary account (@username, link, or user id)",
        lockedPrimaryAccount: null,
        saveButtonLabel: "Save Link Group",
        compact: false,
    },
);

const altPrimaryInput = ref("");
const altAccountsInput = ref("");
const altLinks = ref<AlternativeAccountLinkEntry[]>([]);
const altLinksLoading = ref(false);
const altLinksError = ref<string | null>(null);
const altLinksStatus = ref<string | null>(null);
const altLinkSaving = ref(false);
const editingGroup = ref<string | null>(null);
const editAddInput = ref("");

type AltGroup = {
    primary: string;
    primaryIdentityKey: string;
    linkedinAccounts: string[];
    entries: AlternativeAccountLinkEntry[];
    summary: string;
};

const groupedAltLinks = computed((): AltGroup[] => {
    const grouped: Record<string, AlternativeAccountLinkEntry[]> = {};
    for (const entry of altLinks.value) {
        const key =
            entry.primary_normalized_username || entry.primary_identity_key;
        grouped[key] = grouped[key] || [];
        grouped[key].push(entry);
    }
    return Object.entries(grouped)
        .map(([primary, entries]) => {
            const linkedinAccounts = Array.from(
                new Set(
                    entries.flatMap((entry) => entry.linkedin_accounts || []),
                ),
            );
            const altEntries = entries
                .filter((entry) => Boolean(entry.alt_identity_key))
                .sort((a, b) =>
                    (
                        a.alt_normalized_username ||
                        a.alt_identity_key ||
                        ""
                    ).localeCompare(
                        b.alt_normalized_username || b.alt_identity_key || "",
                    ),
                );
            const allHandles = [
                ...altEntries.map(
                    (e) =>
                        e.alt_normalized_username || e.alt_identity_key || "",
                ),
                ...linkedinAccounts,
            ];
            const summary =
                allHandles.length === 0
                    ? "no linked accounts"
                    : allHandles.length === 1
                      ? allHandles[0]
                      : `${allHandles[0]} and ${allHandles.length - 1} more`;
            return {
                primary,
                primaryIdentityKey: entries[0]?.primary_identity_key || primary,
                linkedinAccounts,
                entries: altEntries,
                summary,
            };
        })
        .sort((a, b) => a.primary.localeCompare(b.primary));
});

function toggleEditingGroup(primaryKey: string) {
    if (editingGroup.value === primaryKey) {
        editingGroup.value = null;
    } else {
        editingGroup.value = primaryKey;
        editAddInput.value = "";
    }
}

function parseUniqueEntries(raw: string) {
    return Array.from(
        new Set(
            raw
                .split(/[\n,]/)
                .map((t) => t.trim())
                .filter(Boolean),
        ),
    );
}

function splitLinkedinFromCombined(raw: string): {
    instagrams: string[];
    linkedins: string[];
} {
    const all = parseUniqueEntries(raw);
    const linkedins = all.filter((e) =>
        e.toLowerCase().includes("linkedin.com"),
    );
    const instagrams = all.filter(
        (e) => !e.toLowerCase().includes("linkedin.com"),
    );
    return { instagrams, linkedins };
}

function effectivePrimaryInput() {
    return (props.lockedPrimaryAccount || altPrimaryInput.value).trim();
}

async function loadAlternativeLinks() {
    altLinksLoading.value = true;
    altLinksError.value = null;
    try {
        const response = await getAlternativeAccountLinks();
        if (props.lockedPrimaryAccount?.trim()) {
            const filterKey = props.lockedPrimaryAccount.trim().toLowerCase();
            altLinks.value = response.entries.filter((entry) => {
                const candidate = (
                    entry.primary_normalized_username ||
                    entry.primary_identity_key
                ).toLowerCase();
                return candidate === filterKey;
            });
            return;
        }
        altLinks.value = response.entries;
    } catch (err: unknown) {
        altLinksError.value =
            err instanceof Error
                ? err.message
                : "Failed to load linked accounts";
    } finally {
        altLinksLoading.value = false;
    }
}

async function saveAlternativeLinks() {
    const primary = effectivePrimaryInput();
    const { instagrams: alts, linkedins } = splitLinkedinFromCombined(
        altAccountsInput.value,
    );
    if (!primary || (!alts.length && !linkedins.length)) {
        altLinksError.value =
            "Enter one primary account and at least one linked account.";
        return;
    }

    altLinkSaving.value = true;
    altLinksError.value = null;
    altLinksStatus.value = null;
    try {
        const response = await addAlternativeAccountLinks({
            primary_account: primary,
            alternative_accounts: alts,
            linkedin_accounts: linkedins,
            trigger_discovery: true,
        });
        if (!props.lockedPrimaryAccount) {
            altPrimaryInput.value = "";
        }
        altAccountsInput.value = "";
        if (response.discovery.queued_count > 0) {
            altLinksStatus.value = `Queued discovery for ${response.discovery.queued_count} account(s).`;
        } else if (
            response.discovery.skipped_discovery_identity_keys.length > 0
        ) {
            altLinksStatus.value =
                "Saved registry, but some discovery jobs could not be queued.";
        } else {
            altLinksStatus.value = "Saved.";
        }
        await loadAlternativeLinks();
    } catch (err: unknown) {
        altLinksError.value =
            err instanceof Error
                ? err.message
                : "Could not save linked-account links";
    } finally {
        altLinkSaving.value = false;
    }
}

async function deleteAlternativeLink(
    primaryIdentityKey: string,
    altIdentityKey: string | null,
) {
    if (!altIdentityKey) {
        return;
    }
    try {
        await removeAlternativeAccountLink(primaryIdentityKey, altIdentityKey);
        await loadAlternativeLinks();
    } catch (err: unknown) {
        altLinksError.value =
            err instanceof Error
                ? err.message
                : "Could not remove linked-account link";
    }
}

async function deleteGroupLinks(
    primaryIdentityKey: string,
    entries: AlternativeAccountLinkEntry[],
) {
    try {
        for (const entry of entries) {
            if (entry.alt_identity_key) {
                await removeAlternativeAccountLink(
                    primaryIdentityKey,
                    entry.alt_identity_key,
                );
            }
        }
        await loadAlternativeLinks();
    } catch (err: unknown) {
        altLinksError.value =
            err instanceof Error
                ? err.message
                : "Could not remove linked accounts";
    }
}

async function saveEditLinks(group: AltGroup) {
    const { instagrams, linkedins } = splitLinkedinFromCombined(
        editAddInput.value,
    );
    if (!instagrams.length && !linkedins.length) return;
    altLinkSaving.value = true;
    altLinksError.value = null;
    altLinksStatus.value = null;
    try {
        const response = await addAlternativeAccountLinks({
            primary_account: group.primaryIdentityKey,
            alternative_accounts: instagrams,
            linkedin_accounts: linkedins,
            trigger_discovery: true,
        });
        editAddInput.value = "";
        altLinksStatus.value =
            response.discovery.queued_count > 0
                ? `Queued discovery for ${response.discovery.queued_count} account(s).`
                : "Saved.";
        await loadAlternativeLinks();
    } catch (err: unknown) {
        altLinksError.value =
            err instanceof Error ? err.message : "Could not save";
    } finally {
        altLinkSaving.value = false;
    }
}

watch(
    () => props.lockedPrimaryAccount,
    () => {
        void loadAlternativeLinks();
    },
);

onMounted(async () => {
    await loadAlternativeLinks();
});
</script>

<template>
    <div
        class="rounded-2xl border border-white/10 bg-white/[0.035] shadow-lg shadow-black/10"
        :class="compact ? 'p-4' : 'p-5 md:p-6'"
    >
        <!-- Header -->
        <div class="flex items-center justify-between gap-3 mb-1">
            <h3 class="text-base font-semibold text-slate-100">{{ title }}</h3>
            <button
                class="text-xs text-slate-400 hover:text-slate-100 transition-colors"
                :disabled="altLinksLoading"
                @click="loadAlternativeLinks"
            >
                {{ altLinksLoading ? "Refreshing..." : "Refresh" }}
            </button>
        </div>
        <p class="text-xs text-slate-500 mb-5 leading-relaxed">
            {{ description }}
        </p>

        <!-- Add form \u2014 unlocked: single-line primary + multi-line linked accounts -->
        <template v-if="!lockedPrimaryAccount">
            <div class="space-y-2">
                <input
                    v-model="altPrimaryInput"
                    class="input-dark"
                    :placeholder="primaryPlaceholder"
                />
                <textarea
                    v-model="altAccountsInput"
                    rows="3"
                    class="input-dark"
                    placeholder="Linked account usernames or profile links, one per line"
                />
                <div class="flex items-center gap-3 pt-0.5">
                    <button
                        class="btn-violet rounded-lg px-4 py-2 text-sm font-semibold"
                        :disabled="
                            altLinkSaving ||
                            !altPrimaryInput.trim() ||
                            !altAccountsInput.trim()
                        "
                        @click="saveAlternativeLinks"
                    >
                        {{ altLinkSaving ? "Saving\u2026" : "Add to Registry" }}
                    </button>
                    <Transition name="fade-msg">
                        <span
                            v-if="altLinksStatus"
                            class="text-xs text-emerald-400"
                            >{{ altLinksStatus }}</span
                        >
                        <span
                            v-else-if="altLinksError"
                            class="text-xs text-rose-400"
                            >{{ altLinksError }}</span
                        >
                    </Transition>
                </div>
            </div>
        </template>

        <!-- Add form \u2014 locked: primary is implicit, only linked accounts needed -->
        <template v-else>
            <div class="space-y-2">
                <textarea
                    v-model="altAccountsInput"
                    rows="3"
                    class="input-dark"
                    placeholder="Linked account usernames or profile links, one per line"
                />
                <div class="flex items-center gap-3 pt-0.5">
                    <button
                        class="btn-violet rounded-lg px-4 py-2 text-sm font-semibold"
                        :disabled="altLinkSaving || !altAccountsInput.trim()"
                        @click="saveAlternativeLinks"
                    >
                        {{ altLinkSaving ? "Saving\u2026" : "Save" }}
                    </button>
                    <Transition name="fade-msg">
                        <span
                            v-if="altLinksStatus"
                            class="text-xs text-emerald-400"
                            >{{ altLinksStatus }}</span
                        >
                        <span
                            v-else-if="altLinksError"
                            class="text-xs text-rose-400"
                            >{{ altLinksError }}</span
                        >
                    </Transition>
                </div>
            </div>
        </template>

        <!-- Section divider + count -->
        <template v-if="groupedAltLinks.length">
            <div class="flex items-center gap-3 mt-6 mb-2">
                <div class="h-px flex-1 bg-white/[0.10]" />
                <span
                    class="text-[10px] uppercase tracking-widest text-slate-400 select-none"
                >
                    {{ groupedAltLinks.length }} registered
                </span>
                <div class="h-px flex-1 bg-white/[0.10]" />
            </div>

            <!-- Flat list of account groups -->
            <div class="space-y-2">
                <div v-for="group in groupedAltLinks" :key="group.primary">
                    <!-- Summary row -->
                    <div
                        class="flex items-center gap-3 rounded-xl border border-white/[0.07] bg-white/[0.03] px-3 py-2.5 transition-colors hover:bg-white/[0.06] hover:border-white/[0.12] group/row"
                    >
                        <span
                            class="w-2 h-2 rounded-full bg-cyan-300/80 shadow-[0_0_10px_rgba(103,232,249,0.25)] shrink-0"
                        />
                        <span
                            class="text-sm font-semibold text-slate-100 shrink-0 max-w-[28%] truncate"
                            >@{{ group.primary }}</span
                        >
                        <span class="shrink-0 text-slate-400" aria-hidden="true">
                            <svg
                                class="w-4 h-4"
                                viewBox="0 0 20 20"
                                fill="none"
                            >
                                <path
                                    d="M4 10h11m0 0-4-4m4 4-4 4"
                                    stroke="currentColor"
                                    stroke-width="1.6"
                                    stroke-linecap="round"
                                    stroke-linejoin="round"
                                />
                            </svg>
                        </span>
                        <span class="text-xs text-slate-300 flex-1 truncate">{{
                            group.summary
                        }}</span>

                        <!-- LinkedIn indicator -->
                        <svg
                            v-if="group.linkedinAccounts.length"
                            class="w-3.5 h-3.5 text-sky-400 shrink-0"
                            viewBox="0 0 24 24"
                            fill="currentColor"
                        >
                            <path
                                d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
                            />
                        </svg>

                        <!-- Hover actions -->
                        <div
                            class="flex items-center gap-1 opacity-0 group-hover/row:opacity-100 transition-opacity shrink-0"
                        >
                            <button
                                type="button"
                                class="text-[10px] px-2 py-1 rounded-md transition-colors"
                                :class="
                                    editingGroup === group.primaryIdentityKey
                                        ? 'text-violet-200 hover:text-white bg-violet-500/20 border border-violet-400/20'
                                        : 'text-slate-300 hover:text-white bg-white/[0.04] hover:bg-white/[0.08] border border-white/[0.06]'
                                "
                                @click="
                                    toggleEditingGroup(group.primaryIdentityKey)
                                "
                            >
                                {{
                                    editingGroup === group.primaryIdentityKey
                                        ? "close"
                                        : "edit"
                                }}
                            </button>
                            <button
                                type="button"
                                class="text-[10px] text-rose-300 hover:text-white px-2 py-1 rounded-md border border-rose-400/15 bg-rose-500/[0.08] hover:bg-rose-500/[0.14] transition-colors"
                                @click="
                                    deleteGroupLinks(
                                        group.primaryIdentityKey,
                                        group.entries,
                                    )
                                "
                            >
                                delete
                            </button>
                        </div>
                    </div>

                    <!-- Inline edit panel -->
                    <div
                        v-if="editingGroup === group.primaryIdentityKey"
                        class="mx-3 mb-2 rounded-b-xl border-x border-b border-white/[0.07] bg-white/[0.025] px-4 pb-3 pt-2 space-y-1"
                    >
                        <!-- LinkedIn pills -->
                        <div
                            v-if="group.linkedinAccounts.length"
                            class="flex flex-wrap gap-1.5 pb-2"
                        >
                            <span
                                v-for="li in group.linkedinAccounts"
                                :key="li"
                                class="inline-flex items-center gap-1 px-2.5 py-1 rounded-full text-[10px] font-medium bg-sky-500/12 text-sky-300 border border-sky-400/20"
                            >
                                <svg
                                    class="w-2.5 h-2.5 shrink-0"
                                    viewBox="0 0 24 24"
                                    fill="currentColor"
                                >
                                    <path
                                        d="M20.447 20.452h-3.554v-5.569c0-1.328-.027-3.037-1.852-3.037-1.853 0-2.136 1.445-2.136 2.939v5.667H9.351V9h3.414v1.561h.046c.477-.9 1.637-1.85 3.37-1.85 3.601 0 4.267 2.37 4.267 5.455v6.286zM5.337 7.433a2.062 2.062 0 01-2.063-2.065 2.064 2.064 0 112.063 2.065zm1.782 13.019H3.555V9h3.564v11.452zM22.225 0H1.771C.792 0 0 .774 0 1.729v20.542C0 23.227.792 24 1.771 24h20.451C23.2 24 24 23.227 24 22.271V1.729C24 .774 23.2 0 22.222 0h.003z"
                                    />
                                </svg>
                                {{ li }}
                            </span>
                        </div>

                        <!-- Alt account rows (individually removable) -->
                        <div
                            v-for="entry in group.entries"
                            :key="entry.link_id"
                            class="flex items-center gap-2 rounded-lg px-2 py-1.5 bg-white/[0.025] group/alt"
                        >
                            <span
                                class="w-1.5 h-1.5 rounded-full bg-slate-400/70 shrink-0"
                            />
                            <span
                                class="text-xs text-slate-200 flex-1 truncate"
                            >
                                @{{
                                    entry.alt_normalized_username ||
                                    entry.alt_identity_key
                                }}
                            </span>
                            <button
                                type="button"
                                class="opacity-0 group-hover/alt:opacity-100 text-[10px] text-rose-300 hover:text-white transition-all shrink-0 rounded px-2 py-0.5 hover:bg-rose-500/[0.12]"
                                @click="
                                    deleteAlternativeLink(
                                        entry.primary_identity_key,
                                        entry.alt_identity_key,
                                    )
                                "
                            >
                                Remove
                            </button>
                        </div>

                        <!-- Add more -->
                        <div class="pt-2 space-y-1.5">
                            <textarea
                                v-model="editAddInput"
                                rows="2"
                                class="input-dark text-xs"
                                placeholder="Add more usernames or profile links, one per line"
                                @keydown.escape="editingGroup = null"
                            />
                            <div class="flex items-center gap-2.5">
                                <button
                                    type="button"
                                    class="btn-violet text-xs px-3 py-1 rounded-md"
                                    :disabled="
                                        altLinkSaving || !editAddInput.trim()
                                    "
                                    @click="saveEditLinks(group)"
                                >
                                    {{ altLinkSaving ? "Adding\u2026" : "Add" }}
                                </button>
                                <button
                                    type="button"
                                    class="text-xs text-slate-400 hover:text-slate-200 transition-colors"
                                    @click="editingGroup = null"
                                >
                                    close
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </template>

        <div
            v-else-if="!altLinksLoading"
            class="mt-6 rounded-xl border border-dashed border-white/[0.10] bg-white/[0.02] py-5 text-center text-slate-500"
        >
            <p class="text-xs">No linked accounts yet</p>
        </div>
    </div>
</template>

<style scoped>
.fade-msg-enter-active,
.fade-msg-leave-active {
    transition: opacity 0.25s ease;
}
.fade-msg-enter-from,
.fade-msg-leave-to {
    opacity: 0;
}
</style>
