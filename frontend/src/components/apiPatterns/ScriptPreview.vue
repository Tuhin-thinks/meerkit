<script setup lang="ts">
import { ref } from "vue";

const props = defineProps<{
  script: string;
}>();

const copied = ref(false);

function copyScript() {
  void navigator.clipboard.writeText(props.script);
  copied.value = true;
  setTimeout(() => {
    copied.value = false;
  }, 2000);
}

function downloadScript() {
  const blob = new Blob([props.script], { type: "text/x-python" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = "instagram_api_script.py";
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="space-y-2">
    <div class="flex items-center justify-between">
      <p class="text-xs font-semibold uppercase tracking-wide text-slate-400">Generated Script</p>
      <div class="flex gap-2">
        <button
          type="button"
          class="text-xs px-2 py-1 rounded font-medium border transition"
          :class="copied
            ? 'bg-emerald-500/20 border-emerald-400/40 text-emerald-300'
            : 'bg-white/[0.04] border-white/[0.08] text-slate-300 hover:bg-white/[0.07]'"
          @click="copyScript"
        >
          {{ copied ? "Copied!" : "Copy" }}
        </button>
        <button
          type="button"
          class="text-xs px-2 py-1 rounded font-medium border bg-white/[0.04] border-white/[0.08] text-slate-300 hover:bg-white/[0.07] transition"
          @click="downloadScript"
        >
          Download
        </button>
      </div>
    </div>
    <pre
      class="max-h-96 overflow-auto rounded-xl border border-white/[0.07] bg-[#0d1426] p-4 text-xs font-mono text-slate-300 leading-relaxed"
    ><code>{{ script }}</code></pre>
  </div>
</template>
