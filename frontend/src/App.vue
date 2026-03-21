<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import Dashboard from "./views/Dashboard.vue";
import HistoryView from "./views/HistoryView.vue";
import PredictionsBulkView from "./views/PredictionsBulkView.vue";
import DiscoveryView from "./views/DiscoveryView.vue";
import TasksView from "./views/TasksView.vue";
import TechBackground from "./components/TechBackground.vue";
import * as api from "./services/api";
import type {
    InstagramUserRecord,
    InstagramApiUsageAccountSummary,
} from "./types/follower";

const queryClient = useQueryClient();
const route = useRoute();
const router = useRouter();
const staleThresholdMs = 24 * 60 * 60 * 1000;

type AppView = "dashboard" | "history" | "predictions" | "discovery" | "tasks" | "admin" | "details";

const loginForm = ref({ name: "", password: "" });
const registerForm = ref({ name: "", password: "" });
const instagramUserForm = ref({
    name: "",
    csrf_token: "",
    session_id: "",
    user_id: "",
});

const selectedInstagramUser = ref<InstagramUserRecord | null>(null);
const activeAccountMessage = ref("");
const accountUpdateForm = ref({
    display_name: "",
    cookie_string: "",
});
const accountUpdateMessage = ref("");
const selectedApiUsage = ref<InstagramApiUsageAccountSummary | null>(null);
const apiUsageLoading = ref(false);
const apiUsageError = ref("");

const { data: meData, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 30_000,
});

const isLoggedIn = computed(() => !!meData.value?.app_user_id);

const currentView = computed<AppView>(() => {
    const view = (route.name as AppView | undefined) ?? "dashboard";
    if (["dashboard", "history", "predictions", "discovery", "tasks", "admin", "details"].includes(view)) {
        return view;
    }
    return "dashboard";
});

const { mutate: doRegister, isPending: registerPending, error: registerError } = useMutation({
    mutationFn: () => api.registerAppUser(registerForm.value),
});

const { mutate: doLogin, isPending: loginPending, error: loginError } = useMutation({
    mutationFn: () => api.loginAppUser(loginForm.value),
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload);
        const active = payload.active_instagram_user;
        if (active) {
            api.setActiveInstagramUserForApi(active.instagram_user_id);
            router.push({ name: "dashboard" });
            queryClient.invalidateQueries();
        } else {
            router.push({ name: "admin" });
        }
    },
});

const { mutate: doLogout, isPending: logoutPending } = useMutation({
    mutationFn: api.logout,
    onSuccess: async () => {
        api.setActiveInstagramUserForApi("");
        selectedInstagramUser.value = null;
        queryClient.setQueryData(["me"], null);
        await queryClient.invalidateQueries();
        router.push({ name: "dashboard" });
    },
});

const {
    mutate: addInstagramUser,
    isPending: addInstagramUserPending,
    error: addInstagramUserError,
} = useMutation({
    mutationFn: () => api.createInstagramUser(instagramUserForm.value),
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload.me);
        instagramUserForm.value = {
            name: "",
            csrf_token: "",
            session_id: "",
            user_id: "",
        };
        const active = payload.me.active_instagram_user;
        if (active) {
            api.setActiveInstagramUserForApi(active.instagram_user_id);
        }
        router.push({ name: "admin" });
        queryClient.invalidateQueries();
    },
});

const { mutate: switchInstagramUser, isPending: switchPending } = useMutation({
    mutationFn: (instagramUserId: string) => api.selectInstagramUser(instagramUserId),
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload.me);
        api.setActiveInstagramUserForApi(
            payload.active_instagram_user.instagram_user_id,
        );
        selectedInstagramUser.value = payload.active_instagram_user;
        activeAccountMessage.value = payload.message;
        queryClient.invalidateQueries();
    },
});

const {
    mutate: saveInstagramUserEdits,
    isPending: saveInstagramUserEditsPending,
    error: saveInstagramUserEditsError,
} = useMutation({
    mutationFn: (payload: {
        instagramUserId: string;
        display_name?: string;
        cookie_string?: string;
    }) =>
        api.updateInstagramUser(payload.instagramUserId, {
            display_name: payload.display_name,
            cookie_string: payload.cookie_string,
        }),
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload.me);
        selectedInstagramUser.value = payload.instagram_user;
        accountUpdateForm.value.display_name = payload.instagram_user.name;
        accountUpdateForm.value.cookie_string = "";
        accountUpdateMessage.value = payload.message;
        queryClient.invalidateQueries();
    },
});

const { mutate: removeInstagramUser, isPending: removePending } = useMutation({
    mutationFn: (instagramUserId: string) => api.deleteInstagramUser(instagramUserId),
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload.me);
        selectedInstagramUser.value = null;
        const active = payload.me.active_instagram_user;
        api.setActiveInstagramUserForApi(active ? active.instagram_user_id : "");
        if (!active) {
            router.push({ name: "admin" });
        }
        queryClient.invalidateQueries();
    },
});

const { mutate: removeAllInstagramUsers, isPending: removeAllPending } = useMutation({
    mutationFn: api.deleteAllInstagramUsers,
    onSuccess: (payload) => {
        queryClient.setQueryData(["me"], payload.me);
        selectedInstagramUser.value = null;
        api.setActiveInstagramUserForApi("");
        router.push({ name: "admin" });
        queryClient.invalidateQueries();
    },
});

const activeInstagramUser = computed<InstagramUserRecord | null>(
    () => meData.value?.active_instagram_user ?? null,
);

const instagramUsers = computed<InstagramUserRecord[]>(
    () => meData.value?.instagram_users ?? [],
);

watch(
    () => activeInstagramUser.value?.instagram_user_id,
    (instagramUserId) => {
        if (instagramUserId) {
            api.setActiveInstagramUserForApi(instagramUserId);
        }
    },
    { immediate: true },
);

watch(currentView, () => {
    activeAccountMessage.value = "";
    accountUpdateMessage.value = "";
});

interface CookiePreview {
    sessionid: string | null;
    ds_user_id: string | null;
    csrftoken: string | null;
}

function parseCookieString(raw: string): CookiePreview {
    const result: CookiePreview = { sessionid: null, ds_user_id: null, csrftoken: null };
    let source = raw.trim();
    if (source.toLowerCase().startsWith("cookie:")) {
        source = source.slice(source.indexOf(":") + 1).trim();
    }
    for (const chunk of source.split(";")) {
        const piece = chunk.trim();
        if (!piece || !piece.includes("=")) continue;
        const eqIdx = piece.indexOf("=");
        const key = piece.slice(0, eqIdx).trim();
        const value = piece.slice(eqIdx + 1).trim();
        if (key === "sessionid") result.sessionid = value || null;
        if (key === "ds_user_id") result.ds_user_id = value || null;
        if (key === "csrftoken") result.csrftoken = value || null;
    }
    return result;
}

const parsedCookiePreview = computed<CookiePreview | null>(() => {
    const raw = accountUpdateForm.value.cookie_string.trim();
    if (!raw) return null;
    return parseCookieString(raw);
});

function parseIsoTime(value?: string | null): number | null {
    if (!value) return null;
    const millis = Date.parse(value);
    return Number.isNaN(millis) ? null : millis;
}

function isCredentialStale(value?: string | null): boolean {
    const timestamp = parseIsoTime(value);
    if (!timestamp) return false;
    return Date.now() - timestamp > staleThresholdMs;
}

function hasStaleCredentials(user: InstagramUserRecord): boolean {
    return (
        isCredentialStale(user.csrf_token_added_at ?? user.created_at) ||
        isCredentialStale(user.session_id_added_at ?? user.created_at)
    );
}

async function loadDetails(instagramUserId: string) {
    selectedInstagramUser.value = await api.getInstagramUser(instagramUserId);
    if (selectedInstagramUser.value) {
        accountUpdateForm.value.display_name = selectedInstagramUser.value.name;
        accountUpdateForm.value.cookie_string = "";
    }
    accountUpdateMessage.value = "";

    apiUsageLoading.value = true;
    apiUsageError.value = "";
    try {
        const summary = await api.getInstagramApiUsageSummary(instagramUserId);
        selectedApiUsage.value = summary.accounts[0] ?? null;
    } catch (_err) {
        selectedApiUsage.value = null;
        apiUsageError.value = "Could not load API usage metrics right now.";
    } finally {
        apiUsageLoading.value = false;
    }
}

async function openDetails(instagramUserId: string) {
    await router.push({ name: "details", params: { instagramUserId } });
    await loadDetails(instagramUserId);
}

watch(
    [() => route.params.instagramUserId, isLoggedIn],
    async ([instagramUserId, loggedIn]) => {
        if (!loggedIn || currentView.value !== "details") {
            return;
        }
        if (!instagramUserId || typeof instagramUserId !== "string") {
            return;
        }
        await loadDetails(instagramUserId);
    },
    { immediate: true },
);

function submitInstagramUserEdits() {
    if (!selectedInstagramUser.value) {
        return;
    }

    const displayName = accountUpdateForm.value.display_name.trim();
    const cookieString = accountUpdateForm.value.cookie_string.trim();

    if (!displayName && !cookieString) {
        accountUpdateMessage.value = "Enter a display name or paste a cookie string first.";
        return;
    }

    saveInstagramUserEdits({
        instagramUserId: selectedInstagramUser.value.instagram_user_id,
        display_name: displayName || undefined,
        cookie_string: cookieString || undefined,
    });
}

function goTo(view: AppView) {
    if (view === "details" && selectedInstagramUser.value) {
        router.push({
            name: "details",
            params: { instagramUserId: selectedInstagramUser.value.instagram_user_id },
        });
        return;
    }
    router.push({ name: view });
}

const discoveryUsername = computed(() => {
    const value = route.params.username;
    return typeof value === "string" ? value : "";
});
</script>

<template>
    <div class="relative min-h-screen bg-[#0d1426] text-slate-100" v-if="!meLoading">
        <TechBackground />
        <div class="relative z-10">

        <!-- ── Login / Register ──────────────────────────────────────── -->
        <main v-if="!isLoggedIn" class="min-h-screen flex items-center justify-center px-4 py-16">
            <div class="w-full max-w-md space-y-5 fade-in">
                <!-- Brand mark -->
                <div class="text-center mb-8">
                    <div class="inline-flex items-center justify-center w-16 h-16 rounded-2xl bg-violet-600/10 border border-violet-500/20 mb-4 pulse-ring">
                        <span class="text-3xl">✦</span>
                    </div>
                    <h1 class="text-3xl font-bold font-display text-gradient">Meerkit</h1>
                    <p class="text-sm text-slate-400 mt-1">Follower Intelligence</p>
                </div>

                <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl p-6 shadow-2xl shadow-black/40">
                    <h2 class="text-lg font-semibold text-slate-100 mb-1">Sign in</h2>
                    <p class="text-xs text-slate-500 mb-5">App user credentials only.</p>

                    <form class="space-y-3" @submit.prevent="doLogin()">
                        <input
                            v-model="loginForm.name"
                            placeholder="Name"
                            class="input-dark"
                        />
                        <input
                            v-model="loginForm.password"
                            type="password"
                            placeholder="Password"
                            class="input-dark"
                        />
                        <button
                            :disabled="loginPending"
                            class="btn-violet w-full rounded-xl px-4 py-2.5 text-sm font-semibold"
                        >
                            {{ loginPending ? "Signing in…" : "Sign in" }}
                        </button>
                    </form>
                    <p v-if="loginError" class="text-sm text-rose-400 mt-3">Invalid credentials.</p>
                </div>

                <div class="bg-[#16213a] border border-white/[0.07] rounded-2xl p-6 shadow-2xl shadow-black/40">
                    <h2 class="text-base font-semibold text-slate-200 mb-3">Create account</h2>
                    <form class="space-y-3" @submit.prevent="doRegister()">
                        <input v-model="registerForm.name" placeholder="Name" class="input-dark" />
                        <input v-model="registerForm.password" type="password" placeholder="Password" class="input-dark" />
                        <button
                            :disabled="registerPending"
                            class="btn-ghost w-full rounded-xl px-4 py-2.5 text-sm font-semibold"
                        >
                            {{ registerPending ? "Creating…" : "Create account" }}
                        </button>
                    </form>
                    <p v-if="registerError" class="text-sm text-rose-400 mt-3">Could not create account.</p>
                </div>
            </div>
        </main>

        <template v-else>
            <!-- ── Navigation ───────────────────────────────────────── -->
            <nav class="sticky top-0 z-10 bg-[#0d1426]/85 backdrop-blur-xl border-b border-white/[0.06] px-6 py-3 shadow-xl shadow-black/20">
                <div class="max-w-6xl mx-auto flex items-center justify-between gap-4">
                    <!-- Brand -->
                    <div>
                        <p class="text-lg font-bold font-display text-gradient tracking-tight">✦ Meerkit</p>
                        <p class="text-[11px] text-slate-500">{{ meData?.name }}</p>
                        <p v-if="activeInstagramUser" class="text-[11px] text-slate-500 mt-0.5">
                            <span class="text-slate-400 font-medium">@{{ activeInstagramUser.name }}</span>
                        </p>
                    </div>

                    <!-- Tab nav -->
                    <div class="flex gap-0.5 bg-white/[0.04] border border-white/[0.06] p-1 rounded-xl">
                        <button
                            v-for="item in [
                                { key: 'dashboard',   label: '⌂ Dashboard'   },
                                { key: 'history',     label: '📋 History'     },
                                { key: 'predictions', label: '🔮 Predictions' },
                                { key: 'tasks',       label: '⚡ Tasks'       },
                                { key: 'admin',       label: '⚙ Admin'       },
                            ]"
                            :key="item.key"
                            :class="currentView === item.key
                                ? 'bg-violet-600/15 text-violet-300 shadow-inner'
                                : 'text-slate-400 hover:text-slate-200 hover:bg-white/[0.04]'"
                            class="px-3.5 py-1.5 rounded-lg text-xs font-medium transition-all"
                            @click="goTo(item.key as AppView)"
                        >
                            {{ item.label }}
                        </button>
                    </div>

                    <button
                        :disabled="logoutPending"
                        @click="doLogout()"
                        class="btn-danger rounded-lg px-3 py-1.5 text-xs font-semibold"
                    >
                        Logout
                    </button>
                </div>
            </nav>

            <!-- ── Main content ──────────────────────────────────────── -->
            <main class="max-w-6xl mx-auto px-6 py-8">
                <KeepAlive>
                    <Dashboard
                        v-if="currentView === 'dashboard' && activeInstagramUser"
                        :profile-id="activeInstagramUser.instagram_user_id"
                    />
                </KeepAlive>

                <KeepAlive>
                    <HistoryView
                        v-if="currentView === 'history' && activeInstagramUser"
                        :profile-id="activeInstagramUser.instagram_user_id"
                    />
                </KeepAlive>

                <KeepAlive>
                    <PredictionsBulkView
                        v-if="currentView === 'predictions' && activeInstagramUser"
                        :profile-id="activeInstagramUser.instagram_user_id"
                    />
                </KeepAlive>

                <KeepAlive>
                    <DiscoveryView
                        v-if="currentView === 'discovery' && activeInstagramUser"
                        :profile-id="activeInstagramUser.instagram_user_id"
                        :initial-username="discoveryUsername"
                    />
                </KeepAlive>

                <KeepAlive>
                    <TasksView
                        v-if="currentView === 'tasks' && activeInstagramUser"
                        :profile-id="activeInstagramUser.instagram_user_id"
                    />
                </KeepAlive>

                <!-- ── Admin ─────────────────────────────────────────── -->
                <div v-if="currentView === 'admin'" class="grid lg:grid-cols-2 gap-6 fade-in">
                    <section class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6">
                        <div class="flex items-center justify-between mb-5">
                            <h2 class="text-base font-semibold text-slate-100">Instagram Accounts</h2>
                            <button
                                :disabled="removeAllPending"
                                @click="removeAllInstagramUsers()"
                                class="btn-danger rounded-lg px-3 py-1.5 text-xs font-medium"
                            >
                                Delete All
                            </button>
                        </div>

                        <div v-if="!instagramUsers.length" class="text-sm text-slate-500 text-center py-8">No accounts yet.</div>
                        <div v-else class="space-y-2">
                            <button
                                v-for="u in instagramUsers"
                                :key="u.instagram_user_id"
                                class="w-full text-left border border-white/[0.06] rounded-xl px-4 py-3 hover:bg-white/[0.04] hover:border-violet-500/20 transition-all card-hover gradient-border"
                                @click="openDetails(u.instagram_user_id)"
                            >
                                <div class="flex items-center gap-2">
                                    <p class="text-sm font-semibold text-slate-100">{{ u.name }}</p>
                                    <span
                                        v-if="activeInstagramUser?.instagram_user_id === u.instagram_user_id"
                                        class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400 border border-emerald-400/20"
                                    >Active</span>
                                    <span
                                        v-if="hasStaleCredentials(u)"
                                        class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-400/10 text-amber-400 border border-amber-400/20"
                                    >Credentials old</span>
                                </div>
                                <p class="text-xs text-slate-500 mt-0.5">USER_ID: {{ u.user_id }}</p>
                            </button>
                        </div>
                    </section>

                    <section class="bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6">
                        <h2 class="text-base font-semibold text-slate-100 mb-5">Add Instagram Account</h2>
                        <form class="space-y-3" @submit.prevent="addInstagramUser()">
                            <input v-model="instagramUserForm.name"       placeholder="Display name (optional)"  class="input-dark" />
                            <input v-model="instagramUserForm.csrf_token" placeholder="CSRF_TOKEN (required)"    class="input-dark" />
                            <input v-model="instagramUserForm.session_id" placeholder="SESSION_ID (required)"   class="input-dark" />
                            <input v-model="instagramUserForm.user_id"    placeholder="USER_ID (required)"      class="input-dark" />
                            <button :disabled="addInstagramUserPending" class="btn-violet w-full rounded-xl px-4 py-2.5 text-sm font-semibold">
                                {{ addInstagramUserPending ? "Adding…" : "Add Account" }}
                            </button>
                        </form>
                        <p v-if="addInstagramUserError" class="text-sm text-rose-400 mt-3">Could not add account. All credential fields are mandatory.</p>
                    </section>
                </div>

                <!-- ── Account Details ───────────────────────────────── -->
                <div
                    v-if="currentView === 'details' && selectedInstagramUser"
                    class="max-w-2xl bg-[#16213a] border border-white/[0.07] rounded-2xl shadow-2xl shadow-black/30 p-6 fade-in"
                >
                    <button
                        @click="goTo('admin')"
                        class="btn-ghost rounded-lg px-3 py-1.5 text-xs mb-5 inline-flex items-center gap-1"
                    >
                        ← Back to Admin
                    </button>
                    <h2 class="text-xl font-bold text-slate-100 mb-4 font-display">{{ selectedInstagramUser.name }}</h2>
                    <p v-if="activeAccountMessage" class="mb-4 text-sm rounded-xl px-3 py-2.5 bg-emerald-400/10 text-emerald-400 border border-emerald-400/20">
                        {{ activeAccountMessage }}
                    </p>
                    <div class="grid gap-2 text-sm">
                        <p>
                            <span class="text-slate-400 font-medium">Status:</span>
                            <span
                                v-if="activeInstagramUser?.instagram_user_id === selectedInstagramUser.instagram_user_id"
                                class="ml-2 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-400/10 text-emerald-400 border border-emerald-400/20"
                            >Active account</span>
                            <span v-else class="ml-2 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-white/[0.06] text-slate-400">Inactive</span>
                        </p>
                        <p><span class="text-slate-400 font-medium">Instagram User ID:</span> <span class="text-slate-200">{{ selectedInstagramUser.instagram_user_id }}</span></p>
                        <p v-if="selectedInstagramUser.username"><span class="text-slate-400 font-medium">Username:</span> <span class="text-slate-200">{{ selectedInstagramUser.username }}</span></p>
                        <p><span class="text-slate-400 font-medium">USER_ID:</span> <span class="text-slate-200">{{ selectedInstagramUser.user_id }}</span></p>
                        <p><span class="text-slate-400 font-medium">CSRF_TOKEN:</span> <span class="text-slate-300 break-all text-xs">{{ selectedInstagramUser.csrf_token }}</span></p>
                        <p><span class="text-slate-400 font-medium">SESSION_ID:</span> <span class="text-slate-300 break-all text-xs">{{ selectedInstagramUser.session_id }}</span></p>
                        <p><span class="text-slate-400 font-medium">Created:</span> <span class="text-slate-200">{{ new Date(selectedInstagramUser.created_at).toLocaleString() }}</span></p>
                        <p>
                            <span class="text-slate-400 font-medium">CSRF token added:</span>
                            <span class="text-slate-200">{{ selectedInstagramUser.csrf_token_added_at ? new Date(selectedInstagramUser.csrf_token_added_at).toLocaleString() : "Unknown" }}</span>
                        </p>
                        <p>
                            <span class="text-slate-400 font-medium">Session ID added:</span>
                            <span class="text-slate-200">{{ selectedInstagramUser.session_id_added_at ? new Date(selectedInstagramUser.session_id_added_at).toLocaleString() : "Unknown" }}</span>
                        </p>
                        <p v-if="hasStaleCredentials(selectedInstagramUser)" class="text-amber-400 text-xs mt-1">
                            ⚠ One or more credentials are older than 1 day.
                        </p>
                    </div>

                    <!-- API Usage section -->
                    <section class="mt-6 border border-white/[0.07] rounded-xl p-4 bg-white/[0.02]">
                        <h3 class="text-sm font-semibold text-slate-200">Instagram API Usage</h3>
                        <p class="text-xs text-slate-500 mt-1">Grouped by category and caller for this account.</p>

                        <p v-if="apiUsageLoading" class="text-sm text-slate-400 mt-3">Loading usage metrics…</p>
                        <p v-else-if="apiUsageError" class="text-sm text-rose-400 mt-3">{{ apiUsageError }}</p>

                        <div v-else-if="selectedApiUsage" class="mt-4">
                            <div class="grid grid-cols-2 gap-3 mb-4">
                                <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
                                    <p class="text-xs text-slate-500 uppercase tracking-wide">All time</p>
                                    <p class="text-sm font-semibold text-slate-100 mt-0.5">
                                        {{ selectedApiUsage.all_time_count.toLocaleString() }} calls
                                    </p>
                                </div>
                                <div class="rounded-xl bg-white/[0.03] border border-white/[0.06] px-3 py-2.5">
                                    <p class="text-xs text-slate-500 uppercase tracking-wide">Last 24h</p>
                                    <p class="text-sm font-semibold text-slate-100 mt-0.5">
                                        {{ selectedApiUsage.last_24h_count.toLocaleString() }} calls
                                    </p>
                                </div>
                            </div>

                            <div v-if="selectedApiUsage.categories.length" class="space-y-2">
                                <div
                                    v-for="category in selectedApiUsage.categories"
                                    :key="category.category"
                                    class="rounded-xl border border-white/[0.06] p-3 bg-white/[0.02]"
                                >
                                    <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-1">
                                        <p class="text-sm font-semibold text-slate-200">{{ category.category }}</p>
                                        <p class="text-xs text-slate-500">
                                            {{ category.all_time_count.toLocaleString() }} total · {{ category.last_24h_count.toLocaleString() }} in 24h
                                        </p>
                                    </div>
                                    <div class="mt-1.5 space-y-1" v-if="category.callers.length">
                                        <p
                                            v-for="caller in category.callers"
                                            :key="`${caller.caller_service}:${caller.caller_method}`"
                                            class="text-xs text-slate-500"
                                        >
                                            <span class="text-slate-400">{{ caller.caller_service }}.{{ caller.caller_method }}</span>
                                            — {{ caller.all_time_count.toLocaleString() }} total, {{ caller.last_24h_count.toLocaleString() }} in 24h
                                        </p>
                                    </div>
                                </div>
                            </div>
                            <p v-else class="text-sm text-slate-500">No tracked API calls yet.</p>
                        </div>
                        <p v-else class="text-sm text-slate-500 mt-3">No tracked API calls yet.</p>
                    </section>

                    <!-- Update form -->
                    <form class="mt-5 space-y-3 border border-white/[0.07] rounded-xl p-4 bg-white/[0.02]" @submit.prevent="submitInstagramUserEdits()">
                        <h3 class="text-sm font-semibold text-slate-200">Update Account Details</h3>
                        <input
                            v-model="accountUpdateForm.display_name"
                            placeholder="Display name"
                            class="input-dark"
                        />
                        <textarea
                            v-model="accountUpdateForm.cookie_string"
                            placeholder="Paste cookie string here (must include sessionid and ds_user_id)"
                            rows="4"
                            class="input-dark"
                        />
                        <!-- Cookie preview -->
                        <div v-if="parsedCookiePreview" class="rounded-xl border border-white/[0.06] bg-white/[0.02] px-4 py-3 text-xs">
                            <p class="font-semibold text-slate-300 mb-2">Cookie preview</p>
                            <div class="grid gap-1.5">
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-slate-500">sessionid</span>
                                    <span :class="parsedCookiePreview.sessionid ? 'text-slate-200 break-all' : 'text-rose-400 italic'">{{ parsedCookiePreview.sessionid ?? 'not found' }}</span>
                                </div>
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-slate-500">ds_user_id</span>
                                    <span :class="parsedCookiePreview.ds_user_id ? 'text-slate-200 break-all' : 'text-rose-400 italic'">{{ parsedCookiePreview.ds_user_id ?? 'not found' }}</span>
                                </div>
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-slate-500">csrftoken</span>
                                    <span :class="parsedCookiePreview.csrftoken ? 'text-slate-200 break-all' : 'text-amber-400 italic'">{{ parsedCookiePreview.csrftoken ?? 'not found (optional)' }}</span>
                                </div>
                            </div>
                        </div>
                        <button
                            :disabled="saveInstagramUserEditsPending"
                            class="btn-ghost w-full rounded-xl px-4 py-2.5 text-sm font-semibold"
                        >
                            {{ saveInstagramUserEditsPending ? "Saving…" : "Save Updates" }}
                        </button>
                        <p v-if="accountUpdateMessage" class="text-sm text-emerald-400">{{ accountUpdateMessage }}</p>
                        <p v-if="saveInstagramUserEditsError" class="text-sm text-rose-400">
                            Could not update account. Check cookie content and try again.
                        </p>
                    </form>

                    <div class="mt-5 flex gap-2">
                        <button
                            :disabled="switchPending"
                            @click="switchInstagramUser(selectedInstagramUser.instagram_user_id)"
                            class="btn-violet rounded-lg px-4 py-2 text-sm font-semibold"
                        >
                            Set Active
                        </button>
                        <button
                            :disabled="removePending"
                            @click="removeInstagramUser(selectedInstagramUser.instagram_user_id)"
                            class="btn-danger rounded-lg px-4 py-2 text-sm font-semibold"
                        >
                            Delete Account
                        </button>
                    </div>
                </div>

                <div
                    v-if="!activeInstagramUser && currentView !== 'admin' && currentView !== 'details'"
                    class="text-sm text-slate-500 text-center py-20"
                >
                    Select or create an Instagram account from the Admin page first.
                </div>
            </main>
        </template>
        </div>
    </div>
</template>
