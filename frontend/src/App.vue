<script setup lang="ts">
import { computed, ref, watch } from "vue";
import { useMutation, useQuery, useQueryClient } from "@tanstack/vue-query";
import { useRoute, useRouter } from "vue-router";
import Dashboard from "./views/Dashboard.vue";
import HistoryView from "./views/HistoryView.vue";
import PredictionsBulkView from "./views/PredictionsBulkView.vue";
import DiscoveryView from "./views/DiscoveryView.vue";
import * as api from "./services/api";
import type { InstagramUserRecord } from "./types/follower";

const queryClient = useQueryClient();
const route = useRoute();
const router = useRouter();
const staleThresholdMs = 24 * 60 * 60 * 1000;

type AppView = "dashboard" | "history" | "predictions" | "discovery" | "admin" | "details";

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

const { data: meData, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 30_000,
});

const isLoggedIn = computed(() => !!meData.value?.app_user_id);

const currentView = computed<AppView>(() => {
    const view = (route.name as AppView | undefined) ?? "dashboard";
    if (["dashboard", "history", "predictions", "discovery", "admin", "details"].includes(view)) {
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
    <div class="min-h-screen bg-gray-50 text-gray-900" v-if="!meLoading">
        <main v-if="!isLoggedIn" class="max-w-xl mx-auto px-6 py-16 space-y-6">
            <div class="bg-white border border-gray-200 shadow-sm rounded-2xl p-6">
                <h1 class="text-2xl font-bold text-gray-900 mb-1">App Login</h1>
                <p class="text-sm text-gray-500 mb-6">
                    Login uses app user name and password only.
                </p>

                <form class="space-y-4" @submit.prevent="doLogin()">
                    <input
                        v-model="loginForm.name"
                        placeholder="Name"
                        class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    />
                    <input
                        v-model="loginForm.password"
                        type="password"
                        placeholder="Password"
                        class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    />
                    <button
                        :disabled="loginPending"
                        class="w-full bg-indigo-600 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
                    >
                        {{ loginPending ? "Logging in…" : "Login" }}
                    </button>
                </form>
                <p v-if="loginError" class="text-sm text-rose-600 mt-3">
                    Invalid app credentials.
                </p>
            </div>

            <div class="bg-white border border-gray-200 shadow-sm rounded-2xl p-6">
                <h2 class="text-lg font-semibold text-gray-900 mb-3">
                    Create App User
                </h2>
                <form class="space-y-3" @submit.prevent="doRegister()">
                    <input
                        v-model="registerForm.name"
                        placeholder="Name"
                        class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    />
                    <input
                        v-model="registerForm.password"
                        type="password"
                        placeholder="Password"
                        class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                    />
                    <button
                        :disabled="registerPending"
                        class="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-black disabled:opacity-50"
                    >
                        {{ registerPending ? "Creating…" : "Create User" }}
                    </button>
                </form>
                <p v-if="registerError" class="text-sm text-rose-600 mt-3">
                    Could not create app user.
                </p>
            </div>
        </main>

        <template v-else>
            <nav
                class="sticky top-0 z-10 bg-white border-b border-gray-200 px-6 py-3 shadow-sm"
            >
                <div class="max-w-6xl mx-auto flex items-center justify-between gap-4">
                    <div>
                        <p class="text-lg font-bold tracking-tight">📊 Follower Tracker</p>
                        <p class="text-xs text-gray-500">App user: {{ meData?.name }}</p>
                        <p v-if="activeInstagramUser" class="text-xs text-gray-500 mt-0.5">
                            Active account:
                            <span class="font-semibold text-gray-700">{{ activeInstagramUser.name }}</span>
                        </p>
                    </div>

                    <div class="flex gap-1 bg-gray-100 p-1 rounded-lg">
                        <button
                            v-for="item in [
                                { key: 'dashboard', label: 'Dashboard' },
                                { key: 'history', label: 'History' },
                                { key: 'predictions', label: 'Predictions' },
                                { key: 'admin', label: 'Admin' },
                            ]"
                            :key="item.key"
                            :class="
                                currentView === item.key
                                    ? 'bg-white shadow text-gray-900'
                                    : 'text-gray-500 hover:text-gray-700'
                            "
                            class="px-4 py-1.5 rounded-md text-sm font-medium transition-all"
                            @click="goTo(item.key as AppView)"
                        >
                            {{ item.label }}
                        </button>
                    </div>

                    <button
                        :disabled="logoutPending"
                        @click="doLogout()"
                        class="text-xs px-3 py-1.5 rounded-lg bg-rose-50 text-rose-700 hover:bg-rose-100"
                    >
                        Logout
                    </button>
                </div>
            </nav>

            <main class="max-w-6xl mx-auto px-6 py-8">
                <Dashboard
                    v-if="currentView === 'dashboard' && activeInstagramUser"
                    :profile-id="activeInstagramUser.instagram_user_id"
                />

                <HistoryView
                    v-else-if="currentView === 'history' && activeInstagramUser"
                    :profile-id="activeInstagramUser.instagram_user_id"
                />

                <PredictionsBulkView
                    v-else-if="currentView === 'predictions' && activeInstagramUser"
                    :profile-id="activeInstagramUser.instagram_user_id"
                />

                <DiscoveryView
                    v-else-if="currentView === 'discovery' && activeInstagramUser"
                    :profile-id="activeInstagramUser.instagram_user_id"
                    :initial-username="discoveryUsername"
                />

                <div v-else-if="currentView === 'admin'" class="grid lg:grid-cols-2 gap-6">
                    <section class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
                        <div class="flex items-center justify-between mb-4">
                            <h2 class="text-lg font-semibold">Instagram Users</h2>
                            <button
                                :disabled="removeAllPending"
                                @click="removeAllInstagramUsers()"
                                class="text-xs px-3 py-1.5 rounded bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                            >
                                Delete All
                            </button>
                        </div>

                        <div v-if="!instagramUsers.length" class="text-sm text-gray-500">
                            No instagram users yet. Add one using the form.
                        </div>
                        <div v-else class="space-y-2">
                            <button
                                v-for="u in instagramUsers"
                                :key="u.instagram_user_id"
                                class="w-full text-left border border-gray-200 rounded-lg px-3 py-2 hover:bg-gray-50"
                                @click="openDetails(u.instagram_user_id)"
                            >
                                <div class="flex items-center gap-2">
                                    <p class="text-sm font-semibold">{{ u.name }}</p>
                                    <span
                                        v-if="activeInstagramUser?.instagram_user_id === u.instagram_user_id"
                                        class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"
                                    >
                                        Active
                                    </span>
                                    <span
                                        v-if="hasStaleCredentials(u)"
                                        class="text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-amber-100 text-amber-800"
                                    >
                                        Credentials old
                                    </span>
                                </div>
                                <p class="text-xs text-gray-500">USER_ID: {{ u.user_id }}</p>
                            </button>
                        </div>
                    </section>

                    <section class="bg-white border border-gray-200 rounded-2xl shadow-sm p-6">
                        <h2 class="text-lg font-semibold mb-4">Add Instagram User</h2>
                        <form class="space-y-3" @submit.prevent="addInstagramUser()">
                            <input
                                v-model="instagramUserForm.name"
                                placeholder="Display name (optional)"
                                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                            />
                            <input
                                v-model="instagramUserForm.csrf_token"
                                placeholder="CSRF_TOKEN (required)"
                                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                            />
                            <input
                                v-model="instagramUserForm.session_id"
                                placeholder="SESSION_ID (required)"
                                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                            />
                            <input
                                v-model="instagramUserForm.user_id"
                                placeholder="USER_ID (required)"
                                class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                            />
                            <button
                                :disabled="addInstagramUserPending"
                                class="w-full bg-indigo-600 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-indigo-700 disabled:opacity-50"
                            >
                                {{ addInstagramUserPending ? "Adding…" : "Add Instagram User" }}
                            </button>
                        </form>
                        <p v-if="addInstagramUserError" class="text-sm text-rose-600 mt-3">
                            Could not add instagram user. All credential fields are mandatory.
                        </p>
                    </section>
                </div>

                <div
                    v-else-if="currentView === 'details' && selectedInstagramUser"
                    class="max-w-2xl bg-white border border-gray-200 rounded-2xl shadow-sm p-6"
                >
                    <button
                        @click="goTo('admin')"
                        class="text-xs mb-4 px-2 py-1 rounded bg-gray-100 hover:bg-gray-200"
                    >
                        ← Back to Admin
                    </button>
                    <h2 class="text-xl font-bold mb-4">{{ selectedInstagramUser.name }}</h2>
                    <p v-if="activeAccountMessage" class="mb-4 text-sm rounded-lg px-3 py-2 bg-emerald-50 text-emerald-700 border border-emerald-200">
                        {{ activeAccountMessage }}
                    </p>
                    <div class="grid gap-2 text-sm">
                        <p>
                            <span class="font-semibold">Status:</span>
                            <span
                                v-if="activeInstagramUser?.instagram_user_id === selectedInstagramUser.instagram_user_id"
                                class="ml-2 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-emerald-100 text-emerald-700"
                            >
                                Active account
                            </span>
                            <span
                                v-else
                                class="ml-2 text-[10px] uppercase tracking-wide px-2 py-0.5 rounded-full bg-gray-100 text-gray-700"
                            >
                                Inactive
                            </span>
                        </p>
                        <p><span class="font-semibold">Instagram User ID:</span> {{ selectedInstagramUser.instagram_user_id }}</p>
                        <p v-if="selectedInstagramUser.username"><span class="font-semibold">Username:</span> {{ selectedInstagramUser.username }}</p>
                        <p><span class="font-semibold">USER_ID:</span> {{ selectedInstagramUser.user_id }}</p>
                        <p><span class="font-semibold">CSRF_TOKEN:</span> {{ selectedInstagramUser.csrf_token }}</p>
                        <p><span class="font-semibold">SESSION_ID:</span> {{ selectedInstagramUser.session_id }}</p>
                        <p><span class="font-semibold">Created:</span> {{ new Date(selectedInstagramUser.created_at).toLocaleString() }}</p>
                        <p>
                            <span class="font-semibold">CSRF token added:</span>
                            {{ selectedInstagramUser.csrf_token_added_at ? new Date(selectedInstagramUser.csrf_token_added_at).toLocaleString() : "Unknown" }}
                        </p>
                        <p>
                            <span class="font-semibold">Session ID added:</span>
                            {{ selectedInstagramUser.session_id_added_at ? new Date(selectedInstagramUser.session_id_added_at).toLocaleString() : "Unknown" }}
                        </p>
                        <p v-if="hasStaleCredentials(selectedInstagramUser)" class="text-amber-700">
                            Credential warning: one or more credentials are older than 1 day.
                        </p>
                    </div>

                    <form class="mt-6 space-y-3 border border-gray-200 rounded-xl p-4" @submit.prevent="submitInstagramUserEdits()">
                        <h3 class="text-sm font-semibold text-gray-800">Update Account Details</h3>
                        <input
                            v-model="accountUpdateForm.display_name"
                            placeholder="Display name"
                            class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                        />
                        <textarea
                            v-model="accountUpdateForm.cookie_string"
                            placeholder="Paste cookie string here (must include sessionid and ds_user_id)"
                            rows="4"
                            class="w-full border border-gray-200 rounded-lg px-3 py-2 text-sm"
                        />
                        <div v-if="parsedCookiePreview" class="rounded-lg border border-gray-200 bg-gray-50 px-3 py-2.5 text-xs">
                            <p class="font-semibold text-gray-700 mb-1.5">Cookie preview</p>
                            <div class="grid gap-1">
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-gray-500">sessionid</span>
                                    <span :class="parsedCookiePreview.sessionid ? 'text-gray-900 break-all' : 'text-rose-500 italic'">{{ parsedCookiePreview.sessionid ?? 'not found' }}</span>
                                </div>
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-gray-500">ds_user_id</span>
                                    <span :class="parsedCookiePreview.ds_user_id ? 'text-gray-900 break-all' : 'text-rose-500 italic'">{{ parsedCookiePreview.ds_user_id ?? 'not found' }}</span>
                                </div>
                                <div class="flex items-start gap-2">
                                    <span class="w-24 shrink-0 text-gray-500">csrftoken</span>
                                    <span :class="parsedCookiePreview.csrftoken ? 'text-gray-900 break-all' : 'text-amber-600 italic'">{{ parsedCookiePreview.csrftoken ?? 'not found (optional)' }}</span>
                                </div>
                            </div>
                        </div>
                        <button
                            :disabled="saveInstagramUserEditsPending"
                            class="w-full bg-gray-800 text-white rounded-lg px-4 py-2.5 text-sm font-semibold hover:bg-black disabled:opacity-50"
                        >
                            {{ saveInstagramUserEditsPending ? "Saving updates…" : "Save Updates" }}
                        </button>
                        <p v-if="accountUpdateMessage" class="text-sm text-emerald-700">{{ accountUpdateMessage }}</p>
                        <p v-if="saveInstagramUserEditsError" class="text-sm text-rose-600">
                            Could not update account details. Check cookie content and try again.
                        </p>
                    </form>

                    <div class="mt-6 flex gap-2">
                        <button
                            :disabled="switchPending"
                            @click="switchInstagramUser(selectedInstagramUser.instagram_user_id)"
                            class="px-4 py-2 text-sm rounded bg-indigo-600 text-white hover:bg-indigo-700 disabled:opacity-50"
                        >
                            Set Active
                        </button>
                        <button
                            :disabled="removePending"
                            @click="removeInstagramUser(selectedInstagramUser.instagram_user_id)"
                            class="px-4 py-2 text-sm rounded bg-rose-50 text-rose-700 hover:bg-rose-100 disabled:opacity-50"
                        >
                            Delete
                        </button>
                    </div>
                </div>

                <div v-else class="text-sm text-gray-500">
                    Select or create an instagram user from the Admin page first.
                </div>
            </main>
        </template>
    </div>
</template>
