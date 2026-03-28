export interface FollowerRecord {
  pk_id: string
  id: string
  fbid_v2: string
  profile_pic_id: string
  profile_pic_url: string
  username: string
  full_name: string
  is_private: boolean
  account_not_accessible?: boolean
  alt_followback_assessment?: {
    is_alt_account_following_you?: boolean
    matched_alt_usernames?: string[]
  }
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
  created_at?: string | null
}

export interface MeResponse {
  app_user_id: string
  name: string
  instagram_users: InstagramUserRecord[]
  active_instagram_user: InstagramUserRecord | null
}

export interface InstagramApiUsageCallerSummary {
  caller_service: string
  caller_method: string
  all_time_count: number
  last_24h_count: number
}

export interface InstagramApiUsageCategorySummary {
  category: string
  all_time_count: number
  last_24h_count: number
  callers: InstagramApiUsageCallerSummary[]
}

export interface InstagramApiUsageAccountSummary {
  instagram_user_id: string
  account_name?: string | null
  all_time_count: number
  last_24h_count: number
  categories: InstagramApiUsageCategorySummary[]
}

export interface InstagramApiUsageSummaryResponse {
  generated_at: string
  window_start_24h: string
  totals: {
    all_time_count: number
    last_24h_count: number
  }
  accounts: InstagramApiUsageAccountSummary[]
}
