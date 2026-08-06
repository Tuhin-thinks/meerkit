<script setup lang="ts">
import { ref, onMounted } from "vue";
import { projectCurlPattern } from "../../services/api";
import type { PatternProjection } from "../../types/apiPattern";

const props = defineProps<{
  profileId: string;
}>();

const INTERNAL_NAMES: { name: string; label: string }[] = [
  { name: "fetch_user_profile_data", label: "Fetch User Profile Data" },
  { name: "fetch_followers_list", label: "Fetch Followers List" },
  { name: "fetch_following_list", label: "Fetch Following List" },
  { name: "follow_user", label: "Follow User" },
  { name: "unfollow_user", label: "Unfollow User" },
  { name: "search_user", label: "Search User" },
];

const projections = ref<Record<string, PatternProjection | null>>({});
const loading = ref(false);
const error = ref<string | null>(null);
const copiedUrl = ref<string | null>(null);

async function loadProjections() {
  loading.value = true;
  error.value = null;
  const results: Record<string, PatternProjection | null> = {};
  for (const item of INTERNAL_NAMES) {
    try {
      results[item.name] = await projectCurlPattern(item.name, undefined, props.profileId);
    } catch {
      results[item.name] = null;
    }
  }
  projections.value = results;
  loading.value = false;
}

function kindClass(kind: string): string {
  if (kind === "runtime") return "bg-amber-500/10 text-amber-300 border-amber-400/30";
  if (kind === "session") return "bg-sky-500/10 text-sky-300 border-sky-400/30";
  return "bg-slate-500/10 text-slate-300 border-slate-400/20";
}

async function copyUrl(url: string) {
  try {
    await navigator.clipboard.writeText(url);
    copiedUrl.value = url;
    setTimeout(() => (copiedUrl.value = null), 1500);
  } catch {
    /* clipboard unavailable */
  }
}

function caseTitle(index: number, runtimeValues: Record<string, string | boolean>): string {
  if (Object.keys(runtimeValues).length === 0) return "Case 1: first page / default";
  const parts = Object.entries(runtimeValues).map(([k, v]) => `${k}=${v}`);
  return `Case ${index + 1}: ${parts.join(", ")}`;
}

function renderField(field: { name: string; kind: string; value: string; omitted: boolean; nested?: Array<{ name: string; kind: string; value: string; omitted: boolean }> }): string {
  if (field.omitted) return `${field.name}  [${field.kind}]  (omitted — no runtime value)`;
  return `${field.name}  [${field.kind}]  ${field.value}`;
}

onMounted(loadProjections);
</script>

<template>
  <div class="space-y-6">
    <div class="flex items-center justify-between">
      <div>
        <h3 class="text-base font-semibold text-slate-100">Projection</h3>
        <p class="text-xs text-slate-500 mt-1">
          Exact outgoing requests per endpoint, computed from the stored template and known runtime values. No live Instagram calls.
        </p>
      </div>
      <button
        type="button"
        class="text-xs px-3 py-1.5 rounded-lg font-medium border border-white/10 bg-white/[0.03] text-slate-300 hover:bg-white/[0.06] transition"
        :disabled="loading"
        @click="loadProjections"
      >
        {{ loading ? "Refreshing..." : "Refresh" }}
      </button>
    </div>

    <p v-if="error" class="text-xs text-red-400">{{ error }}</p>
    <p v-if="loading" class="text-sm text-slate-400">Computing projections...</p>

    <template v-else>
      <div
        v-for="item in INTERNAL_NAMES"
        :key="item.name"
        class="rounded-xl border border-white/[0.07] bg-white/[0.02] p-4"
      >
        <div class="flex items-center justify-between mb-3">
          <div>
            <p class="text-sm font-semibold text-slate-200">{{ item.label }}</p>
            <p class="text-xs font-mono text-slate-500">{{ item.name }}</p>
          </div>
          <span
            v-if="projections[item.name]"
            class="text-[10px] font-medium px-2 py-0.5 rounded-full border text-emerald-300 border-emerald-400/30 bg-emerald-500/10"
          >
            {{ projections[item.name]!.http_method }} · {{ projections[item.name]!.runtime_keys.length }} runtime key(s)
          </span>
          <span
            v-else
            class="text-[10px] font-medium px-2 py-0.5 rounded-full border text-slate-500 border-white/10"
          >
            Not configured
          </span>
        </div>

        <div
          v-if="!projections[item.name]"
          class="text-xs text-slate-500"
        >
          Configure this endpoint in the Editor tab to see its projection.
        </div>

        <div
          v-else
          class="space-y-4"
        >
          <div
            v-for="(caseData, idx) in projections[item.name]!.cases"
            :key="idx"
            class="rounded-lg border border-white/[0.06] bg-black/20 p-3"
          >
            <p class="text-[11px] font-semibold text-slate-400 mb-1">
              {{ caseTitle(idx, caseData.runtime_values) }}
            </p>
            <div class="flex items-start gap-2">
              <pre
                class="flex-1 text-[11px] leading-relaxed font-mono text-violet-200 bg-white/[0.02] rounded-lg px-3 py-2 overflow-x-auto whitespace-pre-wrap break-all"
              >{{ caseData.url }}</pre>
              <button
                type="button"
                class="text-[11px] px-2 py-1 rounded border border-white/10 text-slate-300 hover:bg-white/[0.05] transition shrink-0"
                @click="copyUrl(caseData.url)"
              >
                {{ copiedUrl === caseData.url ? "Copied" : "Copy" }}
              </button>
            </div>

            <div
              v-if="caseData.query_params.length"
              class="mt-2 space-y-1"
            >
              <p class="text-[10px] uppercase tracking-wider text-slate-500">Query params</p>
              <div
                v-for="field in caseData.query_params"
                :key="field.name"
                class="flex items-center gap-2 text-[11px] font-mono"
              >
                <span
                  class="text-[9px] uppercase px-1.5 py-0.5 rounded border font-semibold"
                  :class="kindClass(field.kind)"
                >{{ field.kind }}</span>
                <span class="text-slate-400">{{ renderField(field) }}</span>
              </div>
            </div>

            <div
              v-if="caseData.body_fields.length"
              class="mt-2 space-y-1"
            >
              <p class="text-[10px] uppercase tracking-wider text-slate-500">Body fields</p>
              <div
                v-for="field in caseData.body_fields"
                :key="field.name"
                class="text-[11px] font-mono"
              >
                <span
                  class="text-[9px] uppercase px-1.5 py-0.5 rounded border font-semibold"
                  :class="kindClass(field.kind)"
                >{{ field.kind }}</span>
                <span class="text-slate-400 ml-2">{{ renderField(field) }}</span>
                <div
                  v-if="field.nested?.length"
                  class="ml-4 mt-1 space-y-0.5"
                >
                  <div
                    v-for="sub in field.nested"
                    :key="sub.name"
                    class="text-[11px] font-mono"
                  >
                    <span
                      class="text-[9px] uppercase px-1.5 py-0.5 rounded border font-semibold"
                      :class="kindClass(sub.kind)"
                    >{{ sub.kind }}</span>
                    <span class="text-slate-400 ml-2">{{ renderField(sub) }}</span>
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
      </div>
    </template>
  </div>
</template>
