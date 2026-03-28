<script setup lang="ts">
import { computed, onMounted, ref } from "vue";
import { RouterLink, useRoute, useRouter } from "vue-router";
import ProfilePicture from "../components/ProfilePicture.vue";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import ProbabilityChip from "../components/prediction/ProbabilityChip.vue";
import * as api from "../services/api";
import { extractApiErrorMessage } from "../services/targetAccessErrors";
import type { PredictionSessionItem } from "../types/prediction";

const props = defineProps<{
    profileId: string;
    profileUsername?: string | null;
}>();

const route = useRoute();
const router = useRouter();

const items = ref<PredictionSessionItem[]>([]);
const loading = ref(false);
const loadError = ref("");

const sessionId = computed(() => {
    const value = route.params.sessionId;
    return typeof value === "string" ? value : "";
});

const sortedItems = computed(() =>
    items.value.slice().sort((a, b) => {
        const first = Date.parse(a.requested_at || "");
        const second = Date.parse(b.requested_at || "");
        return (
            (Number.isNaN(second) ? 0 : second) -
            (Number.isNaN(first) ? 0 : first)
        );
    }),
);

interface PredictionSessionGroup {
    key: string;
    primary: PredictionSessionItem;
    duplicates: PredictionSessionItem[];
}

function getGroupKey(item: PredictionSessionItem): string {
    const profileId = (item.target_profile_id || "").trim();
    if (profileId) {
        return `id:${profileId}`;
    }
    const username =
        item.target_profile_summary?.username || item.target_username || "";
    const normalizedUsername = username.trim().toLowerCase();
    if (normalizedUsername) {
        return `username:${normalizedUsername}`;
    }
    return `prediction:${item.prediction_id}`;
}

const groupedItems = computed<PredictionSessionGroup[]>(() => {
    const groupsByKey = new Map<string, PredictionSessionGroup>();
    for (const item of sortedItems.value) {
        const key = getGroupKey(item);
        const existing = groupsByKey.get(key);
        if (!existing) {
            groupsByKey.set(key, {
                key,
                primary: item,
                duplicates: [],
            });
            continue;
        }
        existing.duplicates.push(item);
    }
    return Array.from(groupsByKey.values());
});

function openHistory() {
    void router.push({ name: "predictions-history" });
}

function getFeatureValue(
    item: PredictionSessionItem,
    key: "me_following_account" | "being_followed_by_account",
): boolean | null {
    const breakdown = item.feature_breakdown as {
        me_following_account?: unknown;
        being_followed_by_account?: unknown;
    } | null;

    if (!breakdown) {
        return null;
    }

    const raw = breakdown[key];
    if (typeof raw !== "boolean") {
        return null;
    }
    return raw;
}

function getInitials(item: PredictionSessionItem): string {
    const summary = item.target_profile_summary;
    const label =
        summary?.full_name || summary?.username || item.target_username || "IG";
    const parts = label
        .trim()
        .split(/\s+/)
        .filter(Boolean)
        .slice(0, 2)
        .map((value) => value[0]?.toUpperCase() || "");
    return parts.join("") || "IG";
}

async function loadSessionItems() {
    if (!sessionId.value || loading.value) {
        return;
    }

    loading.value = true;
    loadError.value = "";
    try {
        items.value = await api.getPredictionSessionItems(sessionId.value);
    } catch (error: unknown) {
        loadError.value =
            extractApiErrorMessage(error) ||
            "Could not load items for this prediction session.";
    } finally {
        loading.value = false;
    }
}

onMounted(() => {
    void loadSessionItems();
});
</script>

<template>
    <section class="space-y-6 fade-in">
        <header
            class="rounded-3xl border border-white/10 lrc-results-header p-6 md:p-8 relative overflow-hidden"
        >
            <button
                class="btn-ghost rounded-lg px-3 py-1.5 text-xs mb-5 inline-flex items-center gap-1.5 relative z-10"
                @click="openHistory"
            >
                ← Back to Prediction History
            </button>

            <div
                class="relative z-10 flex flex-wrap items-start justify-between gap-4"
            >
                <div>
                    <p
                        class="text-xs uppercase tracking-[0.22em] text-cyan-100/90 font-semibold"
                    >
                        Follow-Back Predictions
                    </p>
                    <h2
                        class="text-2xl md:text-4xl font-display font-bold text-white mt-2"
                    >
                        Session Predictions
                    </h2>
                    <p class="text-sm text-slate-100/85 mt-3 leading-relaxed">
                        Session ID: {{ sessionId }}
                    </p>
                    <p class="text-xs text-cyan-100/80 mt-4">
                        Active profile:
                        {{
                            props.profileUsername
                                ? "@" + props.profileUsername
                                : props.profileId
                        }}
                    </p>
                </div>

                <button
                    class="btn-ghost rounded-lg px-3 py-1.5 text-xs"
                    :disabled="loading"
                    @click="loadSessionItems"
                >
                    Refresh
                </button>
            </div>
        </header>

        <div
            v-if="loadError"
            class="rounded-2xl border border-rose-400/25 bg-rose-500/10 text-rose-200 px-4 py-3 text-sm"
        >
            {{ loadError }}
        </div>

        <div
            v-else-if="loading && !groupedItems.length"
            class="rounded-2xl border border-white/10 bg-[#121d33] px-4 py-6 text-sm text-slate-300"
        >
            Loading prediction session items...
        </div>

        <div
            v-else-if="!groupedItems.length"
            class="rounded-2xl border border-white/10 bg-[#121d33] px-4 py-6 text-sm text-slate-300"
        >
            No predictions found for this session.
        </div>

        <section
            v-else
            class="rounded-2xl border border-white/10 bg-[#121d33] overflow-hidden"
        >
            <div class="divide-y divide-white/[0.07]">
                <article
                    v-for="group in groupedItems"
                    :key="group.key"
                    class="px-4 py-4 grid lg:grid-cols-[1.2fr,0.9fr,1fr] gap-4 items-start"
                >
                    <div class="flex items-start gap-3">
                        <ProfilePicture
                            v-if="group.primary.target_profile_id"
                            :pk-id="group.primary.target_profile_id"
                            :profile-id="props.profileId"
                            :alt="
                                group.primary.target_profile_summary
                                    ?.username ||
                                group.primary.target_username ||
                                'Profile'
                            "
                            class="w-12 h-12 shrink-0"
                        />
                        <div
                            v-else
                            class="w-12 h-12 rounded-full bg-[#0d1426] border border-white/10 flex items-center justify-center text-xs font-semibold text-cyan-200 shrink-0"
                        >
                            <span>{{ getInitials(group.primary) }}</span>
                        </div>

                        <div class="min-w-0">
                            <p
                                class="font-semibold text-sm text-slate-100 break-all"
                            >
                                {{
                                    group.primary.target_profile_summary
                                        ?.full_name ||
                                    (group.primary.target_username
                                        ? "@" + group.primary.target_username
                                        : "Unknown account")
                                }}
                            </p>
                            <p
                                v-if="
                                    group.primary.target_profile_summary
                                        ?.username ||
                                    group.primary.target_username
                                "
                                class="text-xs text-cyan-300 mt-0.5 break-all flex items-center gap-1.5"
                            >
                                <a
                                    :href="`https://www.instagram.com/${group.primary.target_profile_summary?.username || group.primary.target_username}/`"
                                    target="_blank"
                                    rel="noopener noreferrer"
                                    class="hover:text-cyan-200 hover:underline"
                                    >@{{
                                        group.primary.target_profile_summary
                                            ?.username ||
                                        group.primary.target_username
                                    }}</a
                                >
                                <RouterLink
                                    :to="{
                                        name: 'discovery',
                                        params: {
                                            username:
                                                group.primary
                                                    .target_profile_summary
                                                    ?.username ||
                                                group.primary.target_username,
                                        },
                                    }"
                                    class="text-cyan-400 hover:text-cyan-300"
                                    title="Open in Discovery"
                                    aria-label="Open in Discovery"
                                >
                                    <span aria-hidden="true">🔍</span>
                                </RouterLink>
                            </p>
                            <p
                                class="text-[11px] text-slate-500 mt-1 break-all"
                            >
                                {{
                                    group.primary.target_profile_summary
                                        ?.target_profile_id ||
                                    group.primary.target_profile_id
                                }}
                            </p>

                            <div
                                class="mt-2 flex flex-wrap items-center gap-2 text-[11px]"
                            >
                                <span
                                    class="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-slate-300"
                                >
                                    Followers:
                                    {{
                                        group.primary.target_profile_summary
                                            ?.follower_count ?? "--"
                                    }}
                                </span>
                                <span
                                    class="px-2 py-1 rounded-full bg-white/5 border border-white/10 text-slate-300"
                                >
                                    Following:
                                    {{
                                        group.primary.target_profile_summary
                                            ?.following_count ?? "--"
                                    }}
                                </span>
                            </div>

                            <div
                                class="mt-2 flex flex-wrap items-center gap-2 text-[11px]"
                            >
                                <span class="text-slate-400">
                                    Me following:
                                    {{
                                        getFeatureValue(
                                            group.primary,
                                            "me_following_account",
                                        ) === null
                                            ? "--"
                                            : getFeatureValue(
                                                    group.primary,
                                                    "me_following_account",
                                                )
                                              ? "Yes"
                                              : "No"
                                    }}
                                </span>
                                <span class="text-slate-400">
                                    Follows me:
                                    {{
                                        getFeatureValue(
                                            group.primary,
                                            "being_followed_by_account",
                                        ) === null
                                            ? "--"
                                            : getFeatureValue(
                                                    group.primary,
                                                    "being_followed_by_account",
                                                )
                                              ? "Yes"
                                              : "No"
                                    }}
                                </span>
                            </div>
                        </div>
                    </div>

                    <div class="space-y-2">
                        <PredictionStatusBadge :status="group.primary.status" />
                        <p class="text-[11px] text-slate-500">
                            Requested:
                            {{
                                new Date(
                                    group.primary.requested_at,
                                ).toLocaleString()
                            }}
                        </p>
                        <p
                            v-if="group.primary.computed_at"
                            class="text-[11px] text-slate-500"
                        >
                            Computed:
                            {{
                                new Date(
                                    group.primary.computed_at,
                                ).toLocaleString()
                            }}
                        </p>
                    </div>

                    <div class="justify-self-start lg:justify-self-end">
                        <ProbabilityChip
                            :probability="group.primary.probability"
                            :confidence="group.primary.confidence"
                        />
                    </div>

                    <details
                        v-if="group.duplicates.length"
                        class="lg:col-span-3 mt-1 rounded-lg border border-white/10 bg-white/[0.02] px-3 py-2"
                    >
                        <summary
                            class="cursor-pointer text-[11px] text-slate-400 hover:text-slate-300"
                        >
                            {{ group.duplicates.length }} more duplicates in
                            this session
                        </summary>
                        <div class="mt-2 space-y-2">
                            <div
                                v-for="duplicate in group.duplicates"
                                :key="duplicate.prediction_id"
                                class="flex flex-wrap items-center justify-between gap-2 rounded-md border border-white/10 bg-[#0d1426]/40 px-2 py-1.5"
                            >
                                <div class="text-[11px] text-slate-400">
                                    Requested:
                                    {{
                                        new Date(
                                            duplicate.requested_at,
                                        ).toLocaleString()
                                    }}
                                    <span v-if="duplicate.computed_at">
                                        • Computed:
                                        {{
                                            new Date(
                                                duplicate.computed_at,
                                            ).toLocaleString()
                                        }}
                                    </span>
                                </div>
                                <div class="shrink-0">
                                    <PredictionStatusBadge
                                        :status="duplicate.status"
                                    />
                                </div>
                            </div>
                        </div>
                    </details>
                </article>
            </div>
        </section>
    </section>
</template>
