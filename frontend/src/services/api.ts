import axios from 'axios'
import type {
  ScanStatus,
  ScanSummary,
  DiffResult,
  ScanMeta,
  MeResponse,
  InstagramUserRecord,
} from '../types/follower'
import type {
  FollowBackPredictionResponse,
  PredictionAssessment,
  PredictionDetailResponse,
  PredictionFeedbackPayload,
  PredictionRecord,
  RelationshipCacheStatusResponse,
  PredictionTask,
  TaskListResponse,
} from '../types/prediction'

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

export const triggerScan = () => http.post('/scan', null, { params: { profile_id: activeInstagramUserId } })

export const getSummary = () =>
  http.get<ScanSummary | null>('/summary', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getLatestDiff = () =>
  http.get<DiffResult | null>('/diff/latest', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getHistory = () =>
  http.get<ScanMeta[]>('/history', { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const getDiff = (diffId: string) =>
  http.get<DiffResult>(`/diff/${diffId}`, { params: { profile_id: activeInstagramUserId } }).then((r) => r.data)

export const createFollowBackPrediction = (payload: {
  username?: string
  user_id?: string
  refresh?: boolean
  force_background?: boolean
}) =>
  http
    .post<FollowBackPredictionResponse>('/predictions/follow-back', payload, {
      params: { profile_id: activeInstagramUserId },
    })
    .then((r) => r.data)

export const getPredictionHistory = (params?: { target_profile_id?: string; limit?: number }) =>
  http
    .get<PredictionRecord[]>('/predictions/history', {
      params: {
        profile_id: activeInstagramUserId,
        ...(params || {}),
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
