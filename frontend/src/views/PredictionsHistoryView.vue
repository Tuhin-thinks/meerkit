<script setup lang="ts">
import { onMounted, ref } from "vue";
import { useRouter } from "vue-router";
import PredictionStatusBadge from "../components/prediction/PredictionStatusBadge.vue";
import * as api from "../services/api";
import { extractApiErrorMessage } from "../services/targetAccessErrors";
import type { PredictionHistorySession } from "../types/prediction";

const props = defineProps<{
    profileId: string;
    profileUsername?: string | null;
}>();

const router = useRouter();
const predictionHistory = ref<PredictionHistorySession[]>([]);
const loading = ref(false);
const historyError = ref("");
const hasMore = ref(true);
const offset = ref(0);
const pageSize = 10;

function openBulkPredictions() {
    void router.push({ name: "predictions" });
}

function formatSessionCount(value: number): string {
    return `${value} ${value === 1 ? "account" : "accounts"}`;
}

function formatSessionLabel(sessionId: string): string {
    if (sessionId.startsWith("legacy_ps_")) {
        const datePart = sessionId.split("_").find((p) => /^\d{12}$/.test(p));
        if (datePart) {
            return datePart.slice(0, 8) + "_" + datePart.slice(8);
        }
    }
    if (sessionId.startsWith("pred_session_")) {
        const ts = Number(sessionId.split("_")[2]);
        if (!Number.isNaN(ts) && ts > 0) {
            const d = new Date(ts);
            const year = d.getFullYear();
            const month = String(d.getMonth() + 1).padStart(2, "0");
            const day = String(d.getDate()).padStart(2, "0");
            const hours = String(d.getHours()).padStart(2, "0");
            const mins = String(d.getMinutes()).padStart(2, "0");
            return `${year}${month}${day}_${hours}${mins}`;
        }
    }
    return sessionId.slice(-8);
}

function openPredictionSession(sessionId: string) {
    void router.push({
        name: "predictions-history-session",
        params: { sessionId },
    });
}

async function loadPredictionHistory(reset = false) {
    if (loading.value) {
        return;
    }
    loading.value = true;
    historyError.value = "";

    if (reset) {
        offset.value = 0;
        hasMore.value = true;
        predictionHistory.value = [];
    }

    try {
        const items = await api.getPredictionHistory({
            limit: pageSize,
            offset: offset.value,
        });
        if (reset) {
            predictionHistory.value = items;
        } else {
            predictionHistory.value = [...predictionHistory.value, ...items];
        }
        offset.value += items.length;
        hasMore.value = items.length === pageSize;
    } catch (error: unknown) {
        historyError.value =
            extractApiErrorMessage(error) ||
            "Could not load prediction history right now.";
    } finally {
        loading.value = false;
    }
}

onMounted(() => {
    void loadPredictionHistory(true);
});
</script>

<template>
    <section class="space-y-6 fade-in">
        <header
            class="rounded-3xl border border-white/10 lrc-results-header p-6 md:p-8 relative overflow-hidden"
        >
            <button
                class="btn-ghost rounded-lg px-3 py-1.5 text-xs mb-5 inline-flex items-center gap-1.5 relative z-10"
                @click="openBulkPredictions"
            >
                ← Back to Bulk Predictions
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
                        Prediction History
                    </h2>
                    <p
                        class="text-sm text-slate-100/85 mt-3 max-w-3xl leading-relaxed"
                    >
                        Review past prediction runs without interrupting your
                        active bulk prediction workflow.
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
                    @click="loadPredictionHistory(true)"
                >
                    Refresh
                </button>
            </div>
        </header>

        <div
            v-if="historyError"
            class="rounded-2xl border border-rose-400/25 bg-rose-500/10 text-rose-200 px-4 py-3 text-sm"
        >
            {{ historyError }}
        </div>

        <div
            v-else-if="loading && !predictionHistory.length"
            class="rounded-2xl border border-white/10 bg-[#121d33] px-4 py-6 text-sm text-slate-300"
        >
            Loading prediction history...
        </div>

        <div
            v-else-if="!predictionHistory.length"
            class="rounded-2xl border border-white/10 bg-[#121d33] px-4 py-6 text-sm text-slate-300"
        >
            No prediction history found yet.
        </div>

        <section
            v-else
            class="rounded-2xl border border-white/10 bg-[#121d33] overflow-hidden"
        >
            <div class="divide-y divide-white/[0.07]">
                <div
                    v-for="entry in predictionHistory"
                    :key="entry.prediction_session_id"
                    class="px-4 py-3 grid lg:grid-cols-[1.4fr,0.8fr,180px] gap-3 items-start"
                >
                    <div>
                        <p class="font-semibold text-sm text-slate-100">
                            Session {{ formatSessionLabel(entry.prediction_session_id) }}
                        </p>
                        <p class="text-xs text-cyan-300 mt-1">
                            Scanned for {{ formatSessionCount(entry.prediction_count) }}
                        </p>
                        <p class="text-[11px] text-slate-500 mt-1">
                            {{ new Date(entry.last_requested_at).toLocaleString() }}
                        </p>
                        <p
                            v-if="entry.latest_target_username"
                            class="text-[11px] text-slate-500 mt-1"
                        >
                            Latest target: @{{ entry.latest_target_username }}
                        </p>
                        <button
                            class="btn-ghost mt-2 px-2.5 py-1 rounded-md text-[11px] font-semibold"
                            @click="openPredictionSession(entry.prediction_session_id)"
                        >
                            Open predicted list
                        </button>
                    </div>

                    <div>
                        <PredictionStatusBadge :status="entry.status" />
                    </div>

                    <div class="w-[100px] text-xs text-slate-300 space-y-1 justify-self-end text-left">
                        <p>Completed: {{ entry.completed_count }}</p>
                        <p>Running: {{ entry.running_count }}</p>
                        <p>Queued: {{ entry.queued_count }}</p>
                        <p>Errors: {{ entry.error_count }}</p>
                    </div>
                </div>
            </div>

            <div class="px-4 py-3 border-t border-white/[0.07] bg-white/[0.02]">
                <button
                    v-if="hasMore"
                    class="btn-ghost px-4 py-2 rounded-lg text-sm font-semibold"
                    :disabled="loading"
                    @click="loadPredictionHistory(false)"
                >
                    {{ loading ? "Loading..." : "Load 10 more" }}
                </button>
                <p v-else class="text-xs text-slate-400">
                    End of prediction history.
                </p>
            </div>
        </section>
    </section>
</template>
