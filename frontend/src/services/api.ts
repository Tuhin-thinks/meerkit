import axios from 'axios'
import type {
  ScanStatus,
  ScanSummary,
  DiffResult,
  ScanMeta,
  MeResponse,
  InstagramUserRecord,
  InstagramApiUsageSummaryResponse,
} from '../types/follower'
import type {
  FollowBackPredictionResponse,
  PredictionAssessment,
  PredictionDetailResponse,
  PredictionFeedbackPayload,
  PredictionHistorySession,
  PredictionSessionItem,
  RelationshipCacheStatusResponse,
  PredictionTask,
  TaskListResponse,
} from '../types/prediction'
import type {
  FollowingUsersResponse,
  AutomationAction,
  AutomationActionsResponse,
  AutomationActionResult,
  SafelistResponse,
  AutomationCacheEfficiencyResponse,
  AutomationCacheSizeResponse,
  AlternativeAccountLinksResponse,
  AddAlternativeAccountLinksResponse,
} from '../types/automation'

const http = axios.create({
  baseURL: '/api',
  // Scans can take a while – give two minutes before timing out
  timeout: 120_000,
})

export const getScanStatus = () =>
  http.get<ScanStatus>('/scan/status', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

let activeInstagramUserId = ''

export const setActiveInstagramUserForApi = (instagramUserId: string) => {
  activeInstagramUserId = instagramUserId
}

export const registerAppUser = (payload: {
  name: string
  password: string
}) => http.post('/auth/register', payload).then((r) => r.data)

export const loginAppUser = (payload: {
  name: string
  password: string
}) => http.post<MeResponse>('/auth/login', payload).then((r) => r.data)

export const logout = () => http.post('/auth/logout').then((r) => r.data)

export const me = () => http.get<MeResponse | null>('/auth/me').then((r) => r.data)

export const createInstagramUser = (payload: {
  name: string
  csrf_token: string
  session_id: string
  user_id: string
}) =>
  http.post<{ instagram_user: InstagramUserRecord; me: MeResponse }>('/auth/instagram-users', payload).then((r) => r.data)

export const listInstagramUsers = () =>
  http.get<InstagramUserRecord[]>('/auth/instagram-users').then((r) => r.data)

export const getInstagramUser = (instagramUserId: string) =>
  http.get<InstagramUserRecord>(`/auth/instagram-users/${instagramUserId}`).then((r) => r.data)

export const updateInstagramUser = (
  instagramUserId: string,
  payload: { display_name?: string; cookie_string?: string },
) =>
  http
    .patch<{ instagram_user: InstagramUserRecord; me: MeResponse; message: string }>(
      `/auth/instagram-users/${instagramUserId}`,
      payload,
    )
    .then((r) => r.data)

export const selectInstagramUser = (instagramUserId: string) =>
  http.post<{ active_instagram_user: InstagramUserRecord; message: string; me: MeResponse }>(`/auth/instagram-users/${instagramUserId}/select`).then((r) => r.data)

export const deleteInstagramUser = (instagramUserId: string) =>
  http.delete<{ ok: boolean; me: MeResponse }>(`/auth/instagram-users/${instagramUserId}`).then((r) => r.data)

export const deleteAllInstagramUsers = () =>
  http.delete<{ ok: boolean; me: MeResponse }>('/auth/instagram-users').then((r) => r.data)

export const getInstagramApiUsageSummary = (instagramUserId?: string) =>
  http
    .get<InstagramApiUsageSummaryResponse>('/auth/instagram-api-usage', {
      params: instagramUserId ? { instagram_user_id: instagramUserId } : undefined,
    })
    .then((r) => r.data)

export const triggerScan = () => http.post('/scan', null, { params: { profile_id: activeInstagramUserId } })

export const getSummary = () =>
  http.get<ScanSummary | null>('/summary', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getLatestDiff = () =>
  http.get<DiffResult | null>('/diff/latest', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getHistory = () =>
  http.get<ScanMeta[]>('/history', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getAnalytics = (days: number = 30) =>
  http.get<Array<{ date: string; new_followers: number; unfollowers: number; total_followers: number }>>('/scan-analytics', { params: { profile_id: activeInstagramUserId, days } }).then((r) => r.data)

export const getDiff = (diffId: string) =>
  http.get<DiffResult>(`/diff/${diffId}`, { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const createFollowBackPrediction = (payload: {
  username?: string
  user_id?: string
  refresh?: boolean
  force_background?: boolean
  prediction_session_id?: string
}) =>
  http
    .post<FollowBackPredictionResponse>('/predictions/follow-back', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getPredictionHistory = (params?: {
  target_profile_id?: string
  limit?: number
  offset?: number
}) =>
  http
    .get<PredictionHistorySession[]>('/predictions/history', {
      params: {
        profile_id: activeInstagramUserId,
        ...(params || {}),
      },
    })
    .then((r) => r.data)

export const getPredictionSessionItems = (predictionSessionId: string) =>
  http
    .get<PredictionSessionItem[]>(`/predictions/history/sessions/${encodeURIComponent(predictionSessionId)}`, {
      params: {
        profile_id: activeInstagramUserId,
      },
    })
    .then((r) => r.data)

export const getPrediction = (predictionId: string) =>
  http
    .get<PredictionDetailResponse>(`/predictions/${predictionId}`, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const setPredictionFeedback = (
  predictionId: string,
  payload: PredictionFeedbackPayload,
) =>
  http
    .patch<PredictionAssessment>(`/predictions/${predictionId}/feedback`, payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getPredictionTaskStatus = (taskId: string) =>
  http
    .get<PredictionTask>(`/prediction-tasks/${taskId}/status`, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getLatestPredictionTask = (params?: { target_profile_id?: string }) =>
  http
    .get<PredictionTask | null>('/prediction-tasks/latest', {
      params: {
        profile_id: activeInstagramUserId,
        ...(params || {}),
      },
    })
    .then((r) => r.data)

export const getTargetRelationshipCacheStatus = (
  targetProfileId: string,
  params?: { sync_counts?: boolean },
) =>
  http
    .get<RelationshipCacheStatusResponse>(`/targets/${targetProfileId}/relationship-cache`, {
      params: {
        profile_id: activeInstagramUserId,
        ...(params || {}),
      },
    })
    .then((r) => r.data)

export const refreshTargetRelationshipCache = (
  targetProfileId: string,
  relationshipType: 'followers' | 'following',
) =>
  http
    .post<FollowBackPredictionResponse>(
      `/targets/${targetProfileId}/relationship-cache/refresh`,
      { relationship_type: relationshipType },
      {
        params: { profile_id: activeInstagramUserId },
      },
    )
    .then((r) => r.data)

export const listTasks = () =>
  http
    .get<TaskListResponse>('/tasks', {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const cancelPredictionTask = (taskId: string) =>
  http
    .post<{ task: PredictionTask }>(`/prediction-tasks/${taskId}/cancel`, null, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const cancelScan = () =>
  http
    .post<{ ok: boolean; status: string; message: string }>('/scan/cancel', null, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

// ── Automation ─────────────────────────────────────────────────────────────────

export const getAutomationFollowingUsers = () =>
  http
    .get<FollowingUsersResponse>('/automation/following-users', {
      params: { profile_id: activeInstagramUserId },
      timeout: 300_000,
    })
    .then((r) => r.data)

export const getAutomationCacheEfficiency = (instagramUserId?: string) =>
  http
    .get<AutomationCacheEfficiencyResponse>('/automation/cache-efficiency', {
      params: { profile_id: instagramUserId || activeInstagramUserId },
    })
    .then((r) => r.data)

export const getAutomationCacheSize = (instagramUserId?: string) =>
  http
    .get<AutomationCacheSizeResponse>('/automation/cache-size', {
      params: { profile_id: instagramUserId || activeInstagramUserId },
    })
    .then((r) => r.data)

export const prepareBatchFollow = (payload: {
  candidates: string[]
  do_not_follow?: string[]
  max_follow_count?: number
  skip_private?: boolean
  skip_no_recent_interaction?: boolean
}) =>
  http
    .post<AutomationActionResult>('/automation/batch-follow/prepare', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const prepareBatchUnfollow = (payload: {
  candidates?: string[]
  never_unfollow?: string[]
  max_unfollow_count?: number
  skip_mutual?: boolean
  skip_recent?: boolean
  use_auto_discovery?: boolean
}) =>
  http
    .post<AutomationActionResult>('/automation/batch-unfollow/prepare', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const prepareLeftRightCompare = (payload: {
  left_targets: string[]
  right_targets: string[]
  max_left_count?: number
  max_right_count?: number
}) =>
  http
    .post<AutomationActionResult>('/automation/left-right-compare/prepare', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const confirmAutomationAction = (actionId: string) =>
  http
    .post<AutomationAction>(`/automation/actions/${actionId}/confirm`, null, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const cancelAutomationAction = (actionId: string) =>
  http
    .post<AutomationAction>(`/automation/actions/${actionId}/cancel`, null, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getAutomationAction = (actionId: string) =>
  http
    .get<AutomationAction>(`/automation/actions/${actionId}`, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const listAutomationActions = (options?: {
  action_type?: 'batch_follow' | 'batch_unfollow' | 'left_right_compare'
  limit?: number
}) =>
  http
    .get<AutomationActionsResponse>('/automation/actions', {
      params: {
        profile_id: activeInstagramUserId,
        action_type: options?.action_type,
        limit: options?.limit,
      },
    })
    .then((r) => r.data)

export const getAutomationSafelist = (listType: 'do_not_follow' | 'never_unfollow') =>
  http
    .get<SafelistResponse>(`/automation/safelists/${listType}`, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const addToAutomationSafelist = (
  listType: 'do_not_follow' | 'never_unfollow',
  lines: string[],
) =>
  http
    .post<SafelistResponse>(`/automation/safelists/${listType}`, { lines }, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const removeFromAutomationSafelist = (
  listType: 'do_not_follow' | 'never_unfollow',
  identityKey: string,
) =>
  http
    .delete(`/automation/safelists/${listType}/${encodeURIComponent(identityKey)}`, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getAlternativeAccountLinks = (primaryIdentityKey?: string) =>
  http
    .get<AlternativeAccountLinksResponse>('/automation/alternative-account-links', {
      params: {
        profile_id: activeInstagramUserId,
        ...(primaryIdentityKey ? { primary_identity_key: primaryIdentityKey } : {}),
      },
    })
    .then((r) => r.data)

export const addAlternativeAccountLinks = (payload: {
  primary_account: string
  alternative_accounts: string[]
  linkedin_accounts?: string[]
  trigger_discovery?: boolean
}) =>
  http
    .post<AddAlternativeAccountLinksResponse>('/automation/alternative-account-links', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const removeAlternativeAccountLink = (
  primaryIdentityKey: string,
  altIdentityKey: string,
) =>
  http
    .delete(
      `/automation/alternative-account-links/${encodeURIComponent(primaryIdentityKey)}/${encodeURIComponent(altIdentityKey)}`,
      {
        params: { profile_id: activeInstagramUserId },
      },
    )
    .then((r) => r.data)
