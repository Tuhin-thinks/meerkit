export interface FollowingUser {
  user_id: string
  username: string
  full_name: string
  is_private: boolean
  profile_pic_url: string
}

export interface FollowingUsersResponse {
  users: FollowingUser[]
  total: number
}

export type AutomationStatus =
  | 'draft'
  | 'staged'
  | 'queued'
  | 'running'
  | 'completed'
  | 'error'
  | 'cancelled'

export interface AutomationActionItem {
  item_id: string
  display_username: string | null
  raw_input: string
  status: string
  exclusion_reason: string | null
  error: string | null
  executed_at: string | null
}

export interface AutomationAction {
  action_id: string
  app_user_id: string
  reference_profile_id: string
  action_type: 'batch_follow' | 'batch_unfollow'
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

export interface AutomationActionResult {
  action_id: string
  action_type: string
  status: string
  selected_count: number
  excluded_count: number
  selected_items: { raw_input: string; display_username: string | null }[]
  excluded_items: { raw_input: string; exclusion_reason: string | null }[]
}

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
