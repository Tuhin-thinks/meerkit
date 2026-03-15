import axios from 'axios'
import type {
  ScanStatus,
  ScanSummary,
  DiffResult,
  ScanMeta,
  MeResponse,
  InstagramUserRecord,
} from '../types/follower'

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
