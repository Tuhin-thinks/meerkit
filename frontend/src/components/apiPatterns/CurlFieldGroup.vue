<script setup lang="ts">
import { computed } from "vue";
import type { CurlField } from "../../types/apiPattern";

const props = defineProps<{
  label: string;
  fields: CurlField[];
  fieldType: string;
}>();

const emit = defineEmits<{
  (e: "toggle", key: string): void;
  (e: "select-all"): void;
  (e: "deselect-all"): void;
}>();

const allSelected = computed(() => props.fields.length > 0 && props.fields.every((f) => f.selected));
const noneSelected = computed(() => props.fields.every((f) => !f.selected));

const reasonLabel: Record<string, string> = {
  session: "Session",
  constant: "Constant",
  runtime: "Runtime",
  junk: "Junk",
  optional: "Optional",
};

const reasonColor: Record<string, string> = {
  session: "text-cyan-300 bg-cyan-500/10 border-cyan-500/20",
  constant: "text-violet-300 bg-violet-500/10 border-violet-500/20",
  runtime: "text-amber-300 bg-amber-500/10 border-amber-500/20",
  junk: "text-slate-500 bg-slate-500/10 border-slate-500/20",
  optional: "text-slate-400 bg-white/[0.03] border-white/[0.06]",
};
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">{{ label }} ({{ fields.length }})</p>
      <div class="flex gap-1.5">
        <button
          type="button"
          class="text-[10px] px-1.5 py-0.5 rounded font-medium transition"
          :class="allSelected ? 'text-violet-300 bg-violet-500/15' : 'text-slate-500 hover:text-slate-300'"
          @click="emit('select-all')"
        >
          All
        </button>
        <button
          type="button"
          class="text-[10px] px-1.5 py-0.5 rounded font-medium transition"
          :class="noneSelected ? 'text-rose-300 bg-rose-500/15' : 'text-slate-500 hover:text-slate-300'"
          @click="emit('deselect-all')"
        >
          None
        </button>
      </div>
    </div>
    <div class="flex flex-wrap gap-1.5 max-h-48 overflow-y-auto">
      <label
        v-for="field in fields"
        :key="field.key"
        class="inline-flex items-center gap-1.5 px-2 py-1 rounded-lg text-xs border cursor-pointer transition select-none"
        :class="field.selected
          ? 'bg-violet-500/20 border-violet-400/40 text-violet-100'
          : 'bg-white/[0.03] border-white/[0.06] text-slate-400 hover:bg-white/[0.06]'"
      >
        <input
          type="checkbox"
          class="sr-only"
          :checked="field.selected"
          @change="emit('toggle', field.key)"
        />
        <span class="text-[10px]" :class="field.selected ? 'text-violet-300' : 'text-transparent'">✓</span>
        <span class="font-mono">{{ field.key }}</span>
        <span
          class="text-[9px] px-1 rounded font-medium border leading-tight"
          :class="reasonColor[field.reason] || 'text-slate-500 bg-white/[0.03] border-white/[0.06]'"
        >
          {{ reasonLabel[field.reason] || field.reason }}
        </span>
      </label>
    </div>
  </div>
</template>
