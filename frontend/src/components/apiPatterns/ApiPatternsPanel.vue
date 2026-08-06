<script setup lang="ts">
import { ref, computed } from "vue";
import { listCurlPatterns } from "../../services/api";
import type { ApiCurlPattern } from "../../types/apiPattern";
import CurlScriptEditor from "./CurlScriptEditor.vue";
import ProjectionTab from "./ProjectionTab.vue";

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

const activeTab = ref<"editor" | "projection">("editor");
const patterns = ref<ApiCurlPattern[]>([]);
const loading = ref(false);
const editingInternalName = ref<string | null>(null);

async function loadPatterns() {
  loading.value = true;
  try {
    patterns.value = await listCurlPatterns();
  } catch {
    patterns.value = [];
  } finally {
    loading.value = false;
  }
}

function statusLabel(pattern: ApiCurlPattern | undefined): string {
  if (!pattern) return "Not configured";
  return "Configured";
}

function statusClass(pattern: ApiCurlPattern | undefined): string {
  if (!pattern) return "text-slate-500";
  return "text-emerald-400";
}

function editPattern(internalName: string) {
  editingInternalName.value = internalName;
}

function closeEditor() {
  editingInternalName.value = null;
  void loadPatterns();
}

function onSaved() {
  void loadPatterns();
}

function onDeleted() {
  editingInternalName.value = null;
  void loadPatterns();
}

loadPatterns();
</script>

<template>
  <div class="space-y-6">
    <!-- Header -->
    <div>
      <h3 class="text-base font-semibold text-slate-100">API Scripts</h3>
      <p class="text-xs text-slate-500 mt-1">
        Configure curl-based API patterns for each Instagram endpoint. These patterns replace hardcoded calls.
      </p>
    </div>

    <!-- Tabs -->
    <div class="flex items-center gap-1 border-b border-white/[0.07] pb-3">
      <button
        type="button"
        class="text-xs px-3 py-1.5 rounded-lg font-medium transition"
        :class="activeTab === 'editor' ? 'bg-violet-500/15 text-violet-200 border border-violet-400/30' : 'text-slate-400 hover:text-slate-200 border border-transparent'"
        @click="activeTab = 'editor'"
      >
        Editor
      </button>
      <button
        type="button"
        class="text-xs px-3 py-1.5 rounded-lg font-medium transition"
        :class="activeTab === 'projection' ? 'bg-violet-500/15 text-violet-200 border border-violet-400/30' : 'text-slate-400 hover:text-slate-200 border border-transparent'"
        @click="activeTab = 'projection'"
      >
        Projection
      </button>
    </div>

    <ProjectionTab
      v-if="activeTab === 'projection'"
      :profile-id="profileId"
    />

    <template v-else>
      <!-- Loading -->
      <p v-if="loading" class="text-sm text-slate-400">Loading patterns...</p>

      <!-- Pattern list -->
      <div v-else class="space-y-2">
        <div
          v-for="item in INTERNAL_NAMES"
          :key="item.name"
          class="rounded-xl border border-white/[0.07] bg-white/[0.02] p-3 transition hover:border-white/[0.12]"
        >
          <div class="flex items-center justify-between">
            <div class="min-w-0">
              <p class="text-sm font-semibold text-slate-200">{{ item.label }}</p>
              <p class="text-xs font-mono text-slate-500">{{ item.name }}</p>
            </div>
            <div class="flex items-center gap-2 shrink-0">
              <span
                class="text-[10px] font-medium px-2 py-0.5 rounded-full border"
                :class="statusClass(patterns.find(p => p.internal_name === item.name)) + ' border-current/20'"
              >
                {{ statusLabel(patterns.find(p => p.internal_name === item.name)) }}
              </span>
              <button
                type="button"
                class="text-xs px-2.5 py-1 rounded-lg font-medium border border-violet-400/30 bg-violet-500/10 text-violet-300 hover:bg-violet-500/15 transition"
                @click="editPattern(item.name)"
              >
                {{ patterns.find(p => p.internal_name === item.name) ? "Edit" : "Configure" }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </template>

    <!-- Editor modal -->
    <Teleport to="body">
      <div
        v-if="editingInternalName"
        class="fixed inset-0 z-50 flex items-start justify-center bg-black/60 p-4 pt-8 backdrop-blur-sm overflow-y-auto"
        @click="closeEditor"
      >
        <div
          class="w-full max-w-2xl rounded-2xl border border-white/10 bg-[#1b2030]/95 p-6 shadow-2xl shadow-black/50 backdrop-blur"
          @click.stop
        >
          <div class="flex items-center justify-between mb-4">
            <h4 class="text-sm font-semibold text-slate-100">
              Configure: {{ INTERNAL_NAMES.find(n => n.name === editingInternalName)?.label }}
            </h4>
            <button
              type="button"
              class="text-slate-500 hover:text-slate-300 text-lg leading-none"
              @click="closeEditor"
            >
              ✕
            </button>
          </div>
          <CurlScriptEditor
            :key="editingInternalName"
            :internal-name="editingInternalName"
            :display-name="INTERNAL_NAMES.find(n => n.name === editingInternalName)?.label ?? editingInternalName"
            :profile-id="profileId"
            @saved="onSaved"
            @deleted="onDeleted"
          />
        </div>
      </div>
    </Teleport>
  </div>
</template>
