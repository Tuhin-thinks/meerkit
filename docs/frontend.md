# Frontend

Complete guide to the Vue 3 frontend architecture, components, and state management.

## Frontend Overview

The frontend is a Vue 3 + TypeScript + TailwindCSS single-page application (SPA) with:

- **Vite** build tool
- **TanStack Query** for server state management
- **Pinia** for client-side state (optional)
- **TailwindCSS** for styling
- **axios** for HTTP requests

## Project Structure

```
frontend/src/
├── main.ts                  # App entry point
├── App.vue                  # Root component
├── style.css                # Global styles
│
├── components/
│   ├── FollowerCard.vue    # Follower display card
│   ├── ProfilePicture.vue  # Profile image viewer
│   ├── SkeletonCard.vue    # Loading skeleton
│   └── ...
│
├── views/
│   ├── Dashboard.vue       # Main scan/diff view
│   ├── HistoryView.vue     # Scan history timeline
│   └── ...
│
├── services/
│   └── api.ts              # Axios + endpoints
│
└── types/
    └── follower.ts         # TypeScript interfaces
```

### Views in Action

**Dashboard View** - Track real-time follower changes

![Scan History](images/meerkit-scan-history.png)

## Core Components

### App.vue (Root)

Main application component handling:

- User authentication (login/register)
- Account management (add/select Instagram accounts)
- View routing (Dashboard, History, Admin)
- Global error handling

**Key State:**

```typescript
const { data: meData, isLoading: meLoading } = useQuery({
    queryKey: ["me"],
    queryFn: api.me,
    staleTime: 30_000,
});
```

**Key Features:**

- Login/Register forms
- Instagram account selector
- Cookie string parser (for easy credential entry)
- Credential staleness checker (24h threshold)

### Dashboard.vue

Main dashboard showing scan results.

**Query Keys:**

```typescript
// Poll every 2s while running
useQuery({
    queryKey: ["scan", "status", profileId],
    refetchInterval: (query) => {
        const status = query.state.data?.status;
        return status === "running" ? 2000 : false;
    },
});

// Latest scan total count + diff counts
useQuery({
    queryKey: ["summary", profileId],
    staleTime: Infinity, // Never auto-refetch
});

// New followers + unfollowers
useQuery({
    queryKey: ["diff", "latest", profileId],
    staleTime: Infinity,
});
```

**Sections:**

1. **Header Card** – Last scan time, follower count, scan button
2. **Tab Bar** – New Followers / Unfollowers tabs
3. **Follower Grid** – Follower cards with images

**Re-fetching Strategy:**

```typescript
// When scan completes (running → idle)
watch(
  () => scanStatus.value?.status,
  (newStatus, oldStatus) => {
    if (oldStatus === "running" && newStatus === "idle") {
      // Refresh derived queries
      queryClient.invalidateQueries({ queryKey: ["diff", "latest", ...] });
    }
  },
);
```

### FollowerCard.vue

Displays a single follower with profile picture and verification badge.

**Props:**

```typescript
interface Props {
    follower: FollowerRecord;
    profileId: string;
}

interface FollowerRecord {
    pk_id: string;
    username: string;
    full_name: string;
    is_verified: boolean;
    is_private: boolean;
    profile_pic_url: string;
}
```

**Features:**

- Profile picture (click to enlarge)
- Verification badge (blue checkmark)
- Private account indicator (lock icon)
- Clickable Instagram link

### ProfilePicture.vue

Modal image viewer for profile pictures.

**Functionality:**

- Lazy loading from `/api/image/{pk_id}`
- Fallback to placeholder if missing
- Zoom/lightbox display

### SkeletonCard.vue

Loading placeholder (skeleton) while data is fetching.

**CSS Animation:**

```css
@keyframes skeleton-loading {
    0% {
        background-color: hsl(200, 20%, 80%);
    }
    100% {
        background-color: hsl(200, 20%, 95%);
    }
}
```

## Services

### api.ts

HTTP client with all backend endpoints.

```typescript
const http = axios.create({
  baseURL: '/api',
  timeout: 120_000,
});

// Auth endpoints
export const me = () => http.get<MeResponse>('/auth/me');
export const loginAppUser = (payload) => http.post('/auth/login', payload);

// Scan endpoints
export const getScanStatus = () =>
  http.get('/scan/status', { params: { profile_id: ... } });
export const triggerScan = () =>
  http.post('/scan', null, { params: { profile_id: ... } });

// Diff endpoints
export const getLatestDiff = () =>
  http.get('/diff/latest', { params: { profile_id: ... } });
```

**Active Profile Management:**

```typescript
let activeInstagramUserId = "";

export const setActiveInstagramUserForApi = (id: string) => {
    activeInstagramUserId = id;
};
```

## Type Definitions

### follower.ts

```typescript
export interface ScanStatus {
    status: "idle" | "running" | "error";
    started_at: string | null;
    last_scan_id: string | null;
    last_scan_at: string | null;
    error: string | null;
}

export interface ScanSummary {
    scan_id: string;
    timestamp: string;
    follower_count: number; // Added after fix
    diff_id: string | null;
    new_count?: number;
    unfollow_count?: number;
}

export interface FollowerRecord {
    pk_id: string;
    username: string;
    full_name: string;
    profile_pic_url: string;
    is_private: boolean;
    is_verified: boolean;
}

export interface MeResponse {
    app_user_id: string;
    name: string;
    instagram_users: InstagramUserRecord[];
    active_instagram_user: InstagramUserRecord | null;
}
```

## State Management

### TanStack Query

Server state management (data from API) using `useQuery` and `useMutation`:

```typescript
// Fetch data
const { data, isLoading, error } = useQuery({
    queryKey: ["key"],
    queryFn: () => api.endpoint(),
    staleTime: 5 * 60 * 1000, // 5 minutes
});

// Mutate data
const { mutate, isPending } = useMutation({
    mutationFn: (payload) => api.createItem(payload),
    onSuccess: (data) => {
        queryClient.invalidateQueries({ queryKey: ["items"] });
    },
});
```

### Query Client Configuration

```typescript
const queryClient = new QueryClient({
    defaultOptions: {
        queries: {
            staleTime: 5 * 60 * 1000, // 5 min
            gcTime: 60 * 60 * 1000, // 1 hour
            refetchOnWindowFocus: false,
            retry: 1,
        },
    },
});
```

## Styling

### TailwindCSS Classes

```html
<!-- Responsive grid -->
<div class="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-4">
    <!-- Cards -->
    <div class="bg-white rounded-2xl border border-gray-100 shadow-sm p-6">
        <!-- Buttons -->
        <button
            class="px-4 py-2 bg-indigo-600 text-white rounded-lg hover:bg-indigo-700"
        >
            <!-- Badge -->
            <span
                class="px-2 py-1 bg-emerald-100 text-emerald-700 rounded-full text-xs"
            ></span>
        </button>
    </div>
</div>
```

## Key Features

### Responsive Design

Breakpoints:

- `sm`: 640px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px

Mobile-first approach ensures good experience on all devices.

### Real-time Status Polling

```typescript
const { data: scanStatus } = useQuery({
    queryKey: ["scan", "status", profileId],
    refetchInterval: (query) => {
        return query.state.data?.status === "running" ? 2000 : false;
    },
    refetchOnWindowFocus: false,
});
```

Automatically stops polling when scan completes.

### Error Handling

```typescript
const { mutate, error } = useMutation({
    mutationFn: api.loginUser,
});

if (error) {
    if (error.response?.status === 401) {
        // Auth error
    } else {
        // Network or server error
    }
}
```

### Form Validation & Submission

```typescript
const loginForm = ref({ name: "", password: "" });

const { mutate: doLogin, isPending } = useMutation({
    mutationFn: () => api.loginAppUser(loginForm.value),
    onSuccess: (payload) => {
        // Update global state
        queryClient.setQueryData(["me"], payload);
        currentView.value = "dashboard";
    },
});
```

## Build & Development

### Development Server

```bash
cd frontend
npm run dev
```

Creates dev server on http://localhost:5173 with:

- Hot Module Replacement (HMR)
- API proxy to http://localhost:5000

### Production Build

```bash
npm run build
# Outputs: frontend/dist/
```

Features:

- Code splitting
- Minification
- Tree-shaking
- Source maps

### Code Quality

```bash
# Lint
npm run lint

# Type check
npm run type-check

# Format
npm run format
```

## Common Patterns

### Fetch Data with Loading State

```vue
<template>
    <div v-if="isLoading" class="text-center">Loading...</div>
    <div v-else-if="data">{{ data.follower_count }}</div>
    <div v-else>No data</div>
</template>

<script setup>
const { data, isLoading } = useQuery({
    queryKey: ["summary"],
    queryFn: api.getSummary,
});
</script>
```

### Submit Form and Invalidate Cache

```vue
<script setup>
const { mutate: submit } = useMutation({
    mutationFn: api.updateProfile,
    onSuccess: () => {
        // Refetch profile data
        queryClient.invalidateQueries({ queryKey: ["me"] });
        // Show success message or toast
    },
});
</script>
```

### Guard Routes Based on Auth

```typescript
<template v-if="!isLoggedIn">
  <!-- Show login form -->
</template>

<template v-else>
  <!-- Show dashboard -->
</template>

<script setup>
const isLoggedIn = computed(() => !!meData.value?.app_user_id);
</script>
```

## Performance Optimization

### Code Splitting

Vite automatically splits routes into chunks:

```typescript
const Dashboard = () => import("./views/Dashboard.vue");
```

### Image Lazy Loading

```html
<img src="..." loading="lazy" />
```

### Query Deduplication

TanStack Query automatically deduplicates same-key requests.

### Stale Time Strategy

- `Dashboard.vue`: Keep data in sync with background scans
- `History.vue`: Cache indefinitely until user manually refreshes

---

Next: [Database Schema](database.md) or [Development](development.md)
