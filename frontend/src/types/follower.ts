export interface FollowerRecord {
  pk_id: string
  id: string
  fbid_v2: string
  profile_pic_id: string
  profile_pic_url: string
  username: string
  full_name: string
  is_private: boolean
}

export interface ScanStatus {
  status: 'idle' | 'running' | 'cancelled' | 'error'
  started_at: string | null
  last_scan_id: string | null
  last_scan_at: string | null
  error: string | null
}

export interface ScanMeta {
  scan_id: string
  timestamp: string
  follower_count: number
  diff_id: string | null
}

export interface ScanSummary extends ScanMeta {
  new_count?: number
  unfollow_count?: number
}

export interface DiffResult {
  diff_id: string
  scan_id: string
  timestamp: string
  new_followers: FollowerRecord[]
  unfollowers: FollowerRecord[]
  new_count: number
  unfollow_count: number
}

export interface InstagramUserRecord {
  instagram_user_id: string
  name: string
  username?: string | null
  csrf_token: string
  session_id: string
  user_id: string
  csrf_token_added_at?: string | null
  session_id_added_at?: string | null
  created_at: string
}

export interface MeResponse {
  app_user_id: string
  name: string
  instagram_users: InstagramUserRecord[]
  active_instagram_user: InstagramUserRecord | null
}
