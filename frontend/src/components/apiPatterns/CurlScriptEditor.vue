<script setup lang="ts">
import { ref, computed, onUnmounted } from "vue";
import {
  parseCurl,
  storeCurlPattern,
  getCurlPattern,
  generateCurlScript,
  testCurlPattern,
  deleteCurlPattern,
  getPreference,
  setPreference,
} from "../../services/api";
import type { CurlParseResult, ApiCurlPattern, PatternTestResult, CurlField } from "../../types/apiPattern";
import type { FieldPreferences } from "../../services/api";
import CurlFieldGroup from "./CurlFieldGroup.vue";
import ScriptPreview from "./ScriptPreview.vue";

const props = defineProps<{
  internalName: string;
  displayName: string;
  profileId: string;
}>();

const emit = defineEmits<{
  (e: "saved"): void;
  (e: "deleted"): void;
}>();

const curlText = ref("");
const parseResult = ref<CurlParseResult | null>(null);
const parseError = ref("");
const isParsing = ref(false);

const savedPattern = ref<ApiCurlPattern | null>(null);
const isLoading = ref(false);

const generatedScript = ref("");
const scriptLoading = ref(false);

const testResult = ref<PatternTestResult | null>(null);
const testLoading = ref(false);
const testError = ref("");

const saveLoading = ref(false);
const saveError = ref("");

const hasUnsavedChanges = ref(false);

const selectedCookies = ref<string[]>([]);
const selectedHeaders = ref<string[]>([]);
const selectedData = ref<string[]>([]);
const selectedVariables = ref<string[]>([]);

const preferenceKey = `curl_fields:${props.internalName}`;
let _prefDebounce: ReturnType<typeof setTimeout> | undefined;

onUnmounted(() => {
  if (_prefDebounce) clearTimeout(_prefDebounce);
});

function _debouncedSave() {
  if (_prefDebounce) clearTimeout(_prefDebounce);
  _prefDebounce = setTimeout(savePreferences, 300);
}

function _selectionSnapshot(): FieldPreferences {
  return {
    selected_cookies: [...selectedCookies.value],
    selected_headers: [...selectedHeaders.value],
    selected_data: [...selectedData.value],
    selected_variables: [...selectedVariables.value],
  };
}

function _applyPreferences(prefs: FieldPreferences | null, suggestions: CurlParseResult["suggestions"]) {
  const selected = new Set(prefs ? prefs.selected_cookies : []);
  selectedCookies.value = suggestions.cookies.filter((f) => selected.has(f.key)).map((f) => f.key);
  suggestions.cookies.forEach((f) => { f.selected = selected.has(f.key); });

  const selectedH = new Set(prefs ? prefs.selected_headers : []);
  selectedHeaders.value = suggestions.headers.filter((f) => selectedH.has(f.key)).map((f) => f.key);
  suggestions.headers.forEach((f) => { f.selected = selectedH.has(f.key); });

  const selectedD = new Set(prefs ? prefs.selected_data : []);
  selectedData.value = suggestions.data.filter((f) => selectedD.has(f.key)).map((f) => f.key);
  suggestions.data.forEach((f) => { f.selected = selectedD.has(f.key); });

  const selectedV = new Set(prefs ? prefs.selected_variables : []);
  selectedVariables.value = suggestions.variables.filter((f) => selectedV.has(f.key)).map((f) => f.key);
  suggestions.variables.forEach((f) => { f.selected = selectedV.has(f.key); });
}

async function savePreferences() {
  try {
    await setPreference(preferenceKey, _selectionSnapshot(), props.profileId);
  } catch (err) {
    console.error("savePreferences failed", err);
  }
}

async function loadSaved() {
  isLoading.value = true;
  try {
    const [pattern, prefs] = await Promise.all([
      getCurlPattern(props.internalName, props.profileId),
      getPreference(preferenceKey, props.profileId),
    ]);
    if (pattern) {
      savedPattern.value = pattern;
      curlText.value = pattern.curl_command;
      selectedCookies.value = pattern.selected_cookies ?? [];
      selectedHeaders.value = pattern.selected_headers ?? [];
      selectedData.value = pattern.selected_data ?? [];
      selectedVariables.value = pattern.selected_variables ?? [];
      generatedScript.value = pattern.generated_script ?? "";
      parseError.value = "";
      parseResult.value = null;
      hasUnsavedChanges.value = false;
    }
    if (prefs && !pattern) {
      selectedCookies.value = prefs.selected_cookies;
      selectedHeaders.value = prefs.selected_headers;
      selectedData.value = prefs.selected_data;
      selectedVariables.value = prefs.selected_variables;
    }
  } catch {
    // Pattern not yet saved or preferences not yet set
  } finally {
    isLoading.value = false;
  }
}

async function handleParse() {
  if (!curlText.value.trim()) return;
  isParsing.value = true;
  parseError.value = "";
  parseResult.value = null;
  try {
    const oldPrefs = _selectionSnapshot();
    const result = await parseCurl(curlText.value);
    parseResult.value = result;

    const prefs = oldPrefs.selected_cookies.length || oldPrefs.selected_headers.length
      || oldPrefs.selected_data.length || oldPrefs.selected_variables.length
      ? oldPrefs
      : await getPreference(preferenceKey, props.profileId);
    _applyPreferences(prefs, result.suggestions);
    hasUnsavedChanges.value = true;
    savePreferences();
  } catch (err: unknown) {
    parseError.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? "Failed to parse curl command";
  } finally {
    isParsing.value = false;
  }
}

async function handleSave() {
  if (!curlText.value.trim() || !parseResult.value) return;
  saveLoading.value = true;
  saveError.value = "";
  try {
    await storeCurlPattern(props.internalName, {
      display_name: props.displayName,
      curl_command: curlText.value,
      url: parseResult.value.url,
      http_method: parseResult.value.http_method,
      selected_cookies: selectedCookies.value,
      selected_headers: selectedHeaders.value,
      selected_data: selectedData.value,
      selected_variables: selectedVariables.value,
    }, props.profileId);
    hasUnsavedChanges.value = false;
    savedPattern.value = await getCurlPattern(props.internalName, props.profileId);
    emit("saved");
  } catch (err: unknown) {
    saveError.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? "Failed to save pattern";
  } finally {
    saveLoading.value = false;
  }
}

async function handleGenerate() {
  scriptLoading.value = true;
  try {
    const result = await generateCurlScript(props.internalName, props.profileId);
    generatedScript.value = result.script;
  } catch {
    generatedScript.value = "# Could not generate script — save the pattern first.";
  } finally {
    scriptLoading.value = false;
  }
}

async function handleTest() {
  testLoading.value = true;
  testError.value = "";
  testResult.value = null;
  try {
    testResult.value = await testCurlPattern(props.internalName, undefined, props.profileId);
  } catch (err: unknown) {
    testError.value = (err as { response?: { data?: { error?: string } } })?.response?.data?.error ?? "Test failed";
  } finally {
    testLoading.value = false;
  }
}

async function handleDelete() {
  try {
    await deleteCurlPattern(props.internalName, props.profileId);
    curlText.value = "";
    parseResult.value = null;
    savedPattern.value = null;
    generatedScript.value = "";
    hasUnsavedChanges.value = false;
    emit("deleted");
  } catch {
    // Silently fail
  }
}

function getParseFields(fieldType: string): CurlField[] | undefined {
  return fieldType === "cookies" ? parseResult.value?.suggestions.cookies
    : fieldType === "headers" ? parseResult.value?.suggestions.headers
    : fieldType === "data" ? parseResult.value?.suggestions.data
    : parseResult.value?.suggestions.variables;
}

function toggleField(fieldType: string, key: string) {
  const arr = fieldType === "cookies" ? selectedCookies
    : fieldType === "headers" ? selectedHeaders
    : fieldType === "data" ? selectedData
    : selectedVariables;
  const idx = arr.value.indexOf(key);
  let newSelected: boolean;
  if (idx >= 0) {
    arr.value.splice(idx, 1);
    newSelected = false;
  } else {
    arr.value.push(key);
    newSelected = true;
  }
  hasUnsavedChanges.value = true;
  const field = getParseFields(fieldType)?.find((f) => f.key === key);
  if (field) field.selected = newSelected;
  _debouncedSave();
}

function selectAll(fieldType: string) {
  const fields = getParseFields(fieldType);
  if (!fields) return;
  const arr = fieldType === "cookies" ? selectedCookies
    : fieldType === "headers" ? selectedHeaders
    : fieldType === "data" ? selectedData
    : selectedVariables;
  arr.value = fields.map((f) => f.key);
  fields.forEach((f) => { f.selected = true; });
  hasUnsavedChanges.value = true;
  _debouncedSave();
}

function deselectAll(fieldType: string) {
  const fields = getParseFields(fieldType);
  const arr = fieldType === "cookies" ? selectedCookies
    : fieldType === "headers" ? selectedHeaders
    : fieldType === "data" ? selectedData
    : selectedVariables;
  arr.value = [];
  fields?.forEach((f) => { f.selected = false; });
  hasUnsavedChanges.value = true;
  _debouncedSave();
}

function toggleSelectAll() {
  const fields = parseResult.value?.suggestions;
  if (!fields) return;
  const allSelected = fields.cookies.every((f) => selectedCookies.value.includes(f.key))
    && fields.headers.every((f) => selectedHeaders.value.includes(f.key))
    && fields.data.every((f) => selectedData.value.includes(f.key))
    && fields.variables.every((f) => selectedVariables.value.includes(f.key));
  const newVal = !allSelected;
  selectedCookies.value = newVal ? fields.cookies.map((f) => f.key) : [];
  selectedHeaders.value = newVal ? fields.headers.map((f) => f.key) : [];
  selectedData.value = newVal ? fields.data.map((f) => f.key) : [];
  selectedVariables.value = newVal ? fields.variables.map((f) => f.key) : [];
  fields.cookies.forEach((f) => { f.selected = newVal; });
  fields.headers.forEach((f) => { f.selected = newVal; });
  fields.data.forEach((f) => { f.selected = newVal; });
  fields.variables.forEach((f) => { f.selected = newVal; });
  hasUnsavedChanges.value = true;
  _debouncedSave();
}

const allFieldsSelected = computed(() => {
  const fields = parseResult.value?.suggestions;
  if (!fields) return false;
  return fields.cookies.length > 0 && fields.cookies.every((f) => selectedCookies.value.includes(f.key))
    && fields.headers.length > 0 && fields.headers.every((f) => selectedHeaders.value.includes(f.key))
    && fields.data.length > 0 && fields.data.every((f) => selectedData.value.includes(f.key))
    && fields.variables.length > 0 && fields.variables.every((f) => selectedVariables.value.includes(f.key));
});

loadSaved();
</script>

<template>
  <div class="space-y-4">
    <div v-if="isLoading" class="text-sm text-slate-400 py-4 text-center">Loading saved pattern...</div>

    <div v-else class="space-y-4">
      <!-- Curl input -->
      <div>
        <label class="block text-xs font-semibold uppercase tracking-wide text-slate-400 mb-1.5">
          Paste curl command for <span class="text-violet-300">{{ displayName }}</span>
        </label>
        <textarea
          v-model="curlText"
          rows="5"
          class="input-dark w-full text-xs font-mono"
          placeholder="curl 'https://www.instagram.com/...' -H '...' --data-raw '...'"
        />
        <div class="flex gap-2 mt-2">
          <button
            type="button"
            :disabled="isParsing || !curlText.trim()"
            class="btn-violet rounded-lg px-3 py-1.5 text-xs font-semibold"
            @click="handleParse"
          >
            {{ isParsing ? "Parsing..." : "Parse" }}
          </button>
          <button
            v-if="savedPattern"
            type="button"
            class="btn-danger rounded-lg px-3 py-1.5 text-xs font-semibold"
            @click="handleDelete"
          >
            Delete
          </button>
        </div>
        <p v-if="parseError" class="text-xs text-rose-400 mt-2">{{ parseError }}</p>
      </div>

      <!-- Field groups -->
      <div v-if="parseResult" class="space-y-4">
        <div class="flex items-center justify-between">
          <p class="text-xs text-slate-500">Select which fields to include in the request</p>
          <button
            type="button"
            class="text-[10px] px-2 py-0.5 rounded font-medium border transition"
            :class="allFieldsSelected
              ? 'bg-rose-500/15 border-rose-400/30 text-rose-300'
              : 'bg-white/[0.04] border-white/[0.08] text-slate-400 hover:text-slate-200'"
            @click="toggleSelectAll"
          >
            {{ allFieldsSelected ? "Deselect All" : "Select All" }}
          </button>
        </div>

        <div v-if="parseResult.suggestions.cookies.length">
          <CurlFieldGroup
            label="Cookies"
            :fields="parseResult.suggestions.cookies"
            field-type="cookies"
            @toggle="(key: string) => toggleField('cookies', key)"
            @select-all="selectAll('cookies')"
            @deselect-all="deselectAll('cookies')"
          />
        </div>

        <div v-if="parseResult.suggestions.headers.length">
          <CurlFieldGroup
            label="Headers"
            :fields="parseResult.suggestions.headers"
            field-type="headers"
            @toggle="(key: string) => toggleField('headers', key)"
            @select-all="selectAll('headers')"
            @deselect-all="deselectAll('headers')"
          />
        </div>

        <div v-if="parseResult.suggestions.data.length">
          <CurlFieldGroup
            label="Data"
            :fields="parseResult.suggestions.data"
            field-type="data"
            @toggle="(key: string) => toggleField('data', key)"
            @select-all="selectAll('data')"
            @deselect-all="deselectAll('data')"
          />
        </div>

        <div v-if="parseResult.suggestions.variables.length">
          <CurlFieldGroup
            label="Variables"
            :fields="parseResult.suggestions.variables"
            field-type="variables"
            @toggle="(key: string) => toggleField('variables', key)"
            @select-all="selectAll('variables')"
            @deselect-all="deselectAll('variables')"
          />
        </div>

        <!-- Save / Generate / Test -->
        <div class="flex gap-2 pt-2 border-t border-white/[0.06]">
          <button
            type="button"
            :disabled="saveLoading || !hasUnsavedChanges"
            class="bg-emerald-500 rounded-lg px-4 py-1.5 text-xs font-semibold text-white transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-50"
            @click="handleSave"
          >
            {{ saveLoading ? "Saving..." : "Save" }}
          </button>
          <button
            type="button"
            :disabled="!savedPattern"
            class="bg-violet-500 rounded-lg px-3 py-1.5 text-xs font-semibold text-white transition hover:bg-violet-400 disabled:cursor-not-allowed disabled:opacity-50"
            @click="handleGenerate"
          >
            {{ scriptLoading ? "Generating..." : "Generate Script" }}
          </button>
          <button
            type="button"
            :disabled="!savedPattern"
            class="bg-white/[0.06] rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:bg-white/[0.10] disabled:cursor-not-allowed disabled:opacity-50"
            @click="handleTest"
          >
            {{ testLoading ? "Testing..." : "Test" }}
          </button>
        </div>
        <p v-if="saveError" class="text-xs text-rose-400">{{ saveError }}</p>
      </div>

      <!-- Script preview -->
      <div v-if="generatedScript">
        <ScriptPreview :script="generatedScript" />
      </div>

      <!-- Test result -->
      <div v-if="testResult" class="rounded-xl border p-3 text-xs space-y-1"
        :class="testResult.success
          ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-300'
          : 'bg-rose-500/10 border-rose-500/20 text-rose-300'"
      >
        <p>
          <span class="font-semibold">Status:</span>
          {{ testResult.status_code ?? "Error" }}
          <span class="text-slate-500">({{ testResult.elapsed_ms }}ms)</span>
        </p>
        <pre class="mt-1 text-slate-400 font-mono text-[10px] max-h-32 overflow-auto whitespace-pre-wrap">{{ testResult.response_text }}</pre>
      </div>
      <p v-if="testError" class="text-xs text-rose-400">{{ testError }}</p>
    </div>
  </div>
</template>
