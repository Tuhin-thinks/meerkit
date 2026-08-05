# Frontend

Current frontend architecture for the Vue 3 app in `frontend/src`.

## Stack

- Vue 3 + TypeScript
- Vue Router
- Pinia
- TanStack Query (`@tanstack/vue-query`)
- Axios
- TailwindCSS
- Vite

## Entry + App Shell

- Entry: `frontend/src/main.ts`
- Root shell: `frontend/src/App.vue`

`App.vue` is responsible for:

- auth forms (register/login/logout)
- Instagram account create/select/update/delete UI
- selecting active account for API calls
- the account details page with **Overview / API Usage / Cache / Alt Accounts Registry / API Scripts** tabs
- top-level route-to-view composition

> **Note:** The old **Credentials** tab was removed. Session credentials are refreshed by re-saving curl commands in the **API Scripts** tab (`ApiPatternsPanel.vue`).

## Route Map

Configured in `frontend/src/router/index.ts`:

- `/dashboard`
- `/history`
- `/predictions`
- `/predictions/history`
- `/predictions/history/sessions/:sessionId`
- `/automation`
- `/automation/intelligent-batch-follow`
- `/automation/batch-unfollow`
- `/automation/left-right-compare`
- `/automation/left-right-compare/history`
- `/automation/left-right-compare/results/:actionId?`
- `/discovery/:username?`
- `/tasks`
- `/admin`
- `/admin/accounts/:instagramUserId`

## Main Views

- `Dashboard.vue`: scan trigger/status, summary, latest diff, unfollower export.
- `HistoryView.vue`: paginated history + analytics + diff modal.
- `DiscoveryView.vue`: follow-back prediction + refresh + feedback + relationship cache controls.
- `PredictionsBulkView.vue`: bulk prediction workflow.
- `PredictionsHistoryView.vue`: prediction session list.
- `PredictionsHistorySessionView.vue`: prediction items grouped by target.
- `AutomationView.vue`: automation module launcher.
- `IntelligentBatchFollowAutomationView.vue`: stage/confirm/poll/cancel follow actions.
- `BatchUnfollowAutomationView.vue`: browse-or-paste candidates + stage/confirm flow.
- `LeftRightFollowCompareAutomationView.vue`: compare setup and execution.
- `LeftRightFollowCompareHistoryView.vue`: compare run history.
- `LeftRightFollowCompareResultsView.vue`: matrix + graph result explorer.
- `TasksView.vue`: unified live task board.

!!! warning "⚠️ Instagram Rate Limits Apply"
    Keep follow/unfollow actions under **150–200/day** (new accounts: **under 100/day**). Spread actions gradually throughout the day. [Monitor your API usage →](showcase.md#5-api-monitoring-and-limits)

## API Client

`frontend/src/services/api.ts` includes endpoint wrappers for:

- auth + account management
- curl patterns: `parseCurl`, `storeCurlPattern`, `getCurlPattern`, `listCurlPatterns`, `updateCurlPattern`, `deleteCurlPattern`, `testCurlPattern`, `generateCurlScript`, plus `getPreference`/`setPreference` for field-selection preferences
- scan/history/diff/image
- prediction and prediction tasks
- unified tasks list
- automation (actions, safelists, alternative-account links, cache metrics)

Active Instagram scope is managed through:

- `setActiveInstagramUserForApi(instagramUserId)`
- a module-level `activeInstagramUserId` used in query params

## Query/Mutation Patterns

- TanStack Query manages polling and invalidation.
- Scan status and tasks are polled at intervals.
- Mutations update/invalidate query cache after successful writes.
- Global defaults are set in `main.ts` (stale time, gc time, retries).

## API Scripts (Curl Patterns)

The account details page exposes an **API Scripts** tab that configures the curl-pattern gateway:

- `components/apiPatterns/ApiPatternsPanel.vue`: lists the operations (`fetch_user_profile_data`, `fetch_followers_list`, `fetch_following_list`, `follow_user`, `unfollow_user`, `search_user`) with Configure/Edit entry points.
- `components/apiPatterns/CurlScriptEditor.vue`: curl textarea + parse/save/test/generate actions; parses a pasted curl command and lets the user pick which cookies, headers, data, and variables to send.
- `components/apiPatterns/CurlFieldGroup.vue`: reusable field checkbox group for the parsed suggestions.
- `components/apiPatterns/ScriptPreview.vue`: displays the generated standalone Python script.

Field-selection preferences are persisted per user/pattern via `GET|PUT /api/curl-patterns/preferences/<key>`.

## Local Persistence Helpers

- `services/automationJobRegistry.ts`:
  - stores active automation jobs in `localStorage`
  - supports recover-on-refresh behavior
- `services/uiTaskState.ts`:
  - local UI signal for running bulk job states

## UI Components

- follower/profile cards and skeleton loading components
- prediction components (`PredictionStatusBadge`, `TaskProgressBar`, etc.)
- automation registry panel (`AltAccountsRegistryPanel.vue`)
- API Scripts panel + curl editor components (see above)

## Build + Run

Development:

```bash
cd frontend
npm run dev
```

Production build:

```bash
cd frontend
npm run build
```

Quality checks:

```bash
cd frontend
npm run lint
npm run type-check
```

See [Backend API](backend.md) and [API Reference](api-reference.md) for backend contracts.
