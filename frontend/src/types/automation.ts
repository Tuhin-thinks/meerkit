export interface FollowingUser {
  user_id: string
  username: string
  full_name: string
  is_private: boolean
  profile_pic_url: string
  follower_count: number | null
  following_count: number | null
  follows_you: boolean
}

export interface FollowingUsersResponse {
  users: FollowingUser[]
  total: number
  followers_total: number
  following_total: number
}

export interface AutomationCacheWindowMetrics {
  cache_hits: number
  api_calls: number
  total_reads: number
  efficiency_percent: number
}

export interface AutomationCacheSizeResponse {
  generated_at: string
  instagram_user_id: string
  cache_scope: string
  cache_size_bytes: number
  cache_file_count: number
}

export interface AutomationCacheCategoryMetrics {
  category: string
  all_time: AutomationCacheWindowMetrics
  last_24h: AutomationCacheWindowMetrics
}

export interface AutomationCacheEfficiencyResponse {
  generated_at: string
  instagram_user_id: string
  all_time: AutomationCacheWindowMetrics
  last_24h: AutomationCacheWindowMetrics
  cache_size: {
    cache_size_bytes: number
    cache_file_count: number
    cache_scope: string
  }
  per_category: AutomationCacheCategoryMetrics[]
}

export type AutomationStatus =
  | 'draft'
  | 'staged'
  | 'queued'
  | 'running'
  | 'partial'
  | 'completed'
  | 'error'
  | 'cancelled'

export interface AutomationPreviewItem {
  raw_input: string
  normalized_username: string | null
  normalized_user_id: string | null
  display_username: string | null
  status?: string
}

export interface AutomationActionItem extends AutomationPreviewItem {
  item_id: string
  status: string
  exclusion_reason:
    | 'invalid_input'
    | 'safelist'
    | 'cap_reached'
    | 'alternative_account_follows_you'
    | string
    | null
  error: string | null
  executed_at: string | null
}

export interface AutomationAction {
  action_id: string
  app_user_id: string
  reference_profile_id: string
  action_type: AutomationActionType
  status: AutomationStatus
  config: Record<string, unknown> | null
  total_items: number
  completed_items: number
  failed_items: number
  skipped_items: number
  error: string | null
  queued_at: string | null
  started_at: string | null
  completed_at: string | null
  create_date: string
  update_date: string
  items_by_status?: Record<string, AutomationActionItem[]>
}

export interface LeftRightCompareConnection {
  right_identity_key: string | null
  right_display: string | null
  right_user_id: string | null
  is_following: boolean
  resolved: boolean
}

export interface LeftRightCompareRow {
  left_item_id: string
  left_raw_input: string | null
  left_display: string | null
  left_user_id: string | null
  left_followers_count: number
  follows_count: number
  missing_count: number
  unresolved_count: number
  connections: LeftRightCompareConnection[]
}

export interface LeftRightCompareTarget {
  raw_input: string
  display_username: string | null
  normalized_username: string | null
  normalized_user_id: string | null
  identity_key: string | null
}

export interface LeftRightCompareResult {
  schema_version: number
  status: string
  left_rows: LeftRightCompareRow[]
  right_targets: LeftRightCompareTarget[]
  totals: {
    left_total: number
    right_total: number
    relations_total: number
    follows_total: number
    missing_total: number
    unresolved_total: number
  }
}

export interface LeftRightCompareActionConfig {
  max_left_count?: number
  max_right_count?: number
  comparison_result?: LeftRightCompareResult
  [key: string]: unknown
}

export interface AutomationActionsResponse {
  actions: AutomationAction[]
  total: number
}

export interface AutomationActionResult {
  action_id: string
  action_type: string
  status: string
  selected_count: number
  excluded_count: number
  right_selected_count?: number
  right_excluded_count?: number
  selected_items: AutomationPreviewItem[]
  excluded_items: { raw_input: string; exclusion_reason: string | null }[]
  right_excluded_items?: { raw_input: string; exclusion_reason: string | null }[]
}

export type AutomationActionType = 'batch_follow' | 'batch_unfollow' | 'left_right_compare'

export interface SafelistEntry {
  safelist_id: string
  list_type: string
  raw_input: string
  normalized_username: string | null
  normalized_user_id: string | null
  identity_key: string
  create_date: string
}

export interface SafelistResponse {
  list_type: string
  entries: SafelistEntry[]
  total: number
}

export interface AlternativeAccountLinkEntry {
  link_id: string
  app_user_id: string
  reference_profile_id: string
  primary_raw_input: string
  primary_normalized_username: string | null
  primary_normalized_user_id: string | null
  primary_identity_key: string
  alt_raw_input: string | null
  alt_normalized_username: string | null
  alt_normalized_user_id: string | null
  alt_identity_key: string | null
  linkedin_accounts?: string[]
  create_date: string
}

export interface AlternativeAccountLinksResponse {
  entries: AlternativeAccountLinkEntry[]
  total: number
}

export interface AddAlternativeAccountLinksResponse {
  primary_identity_key: string
  added: number
  skipped_invalid: number
  linkedin_accounts: string[]
  entries: AlternativeAccountLinkEntry[]
  total: number
  discovery: {
    queued_prediction_ids: string[]
    queued_task_ids: string[]
    queued_count: number
    skipped_discovery_identity_keys: string[]
  }
}
