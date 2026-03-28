export type PredictionStatus = 'queued' | 'running' | 'completed' | 'error' | 'cancelled'

export type TaskStatus = PredictionStatus | 'draft' | 'staged' | 'partial'

export type PredictionOutcomeStatus =
  | 'pending'
  | 'confirmed'
  | 'correct'
  | 'wrong'
  | 'ignored'
  | 'pending_review'

export interface PredictionRecord {
  prediction_id: string
  prediction_type: string
  app_user_id: string
  reference_profile_id: string
  target_profile_id: string
  target_username: string | null
  probability: number | null
  confidence: number | null
  status: PredictionStatus
  outcome_status: PredictionOutcomeStatus | null
  task_id: string | null
  result_payload: Record<string, unknown> | null
  feature_breakdown: Record<string, unknown> | null
  requested_at: string
  computed_at: string | null
  data_as_of: string | null
  expires_at: string | null
}

export interface PredictionTask {
  task_id: string
  prediction_id: string
  task_type: string
  status: PredictionStatus
  progress: number
  error: string | null
  queued_at: string
  started_at: string | null
  completed_at: string | null
}

export interface PredictionAssessment {
  assessment_id: string
  prediction_id: string
  assessment_status: 'correct' | 'wrong' | 'pending_review' | 'ignored'
  source: string
  notes: string | null
  evidence: Record<string, unknown> | null
  observed_at: string | null
  recorded_at: string
}

export interface FollowBackPredictionResponse {
  prediction: PredictionRecord
  task: PredictionTask | null
}

export interface PredictionHistorySession {
  prediction_session_id: string
  latest_prediction_id: string
  prediction_type: string
  latest_target_username: string | null
  latest_target_profile_id: string | null
  last_requested_at: string
  status: PredictionStatus
  prediction_count: number
  completed_count: number
  error_count: number
  queued_count: number
  running_count: number
  cancelled_count: number
}

export interface PredictionTargetProfileSummary {
  target_profile_id: string | null
  username: string | null
  full_name: string | null
  follower_count: number | null
  following_count: number | null
  is_private: boolean | null
  is_verified: boolean | null
  me_following_account: boolean | null
  being_followed_by_account: boolean | null
  profile_pic_url: string | null
}

export interface PredictionSessionItem extends PredictionRecord {
  target_profile_summary?: PredictionTargetProfileSummary
}

export interface PredictionDetailResponse {
  prediction: PredictionRecord
  task: PredictionTask | null
  assessments: PredictionAssessment[]
}

export interface PredictionFeedbackPayload {
  assessment_status: 'correct' | 'wrong' | 'pending_review' | 'ignored'
  notes?: string
  observed_at?: string
  expected_direction?: 'higher' | 'lower'
  expected_value?: number
}

export interface RelationshipCacheStatusItem {
  relationship_type: 'followers' | 'following'
  fetched_at: string | null
  days_since_fetch: number | null
  is_outdated: boolean
  active_file_present: boolean
  active_cache_file_path: string | null
  last_known_count: number | null
  current_count: number | null
}

export interface RelationshipCacheStatusResponse {
  followers: RelationshipCacheStatusItem
  following: RelationshipCacheStatusItem
}

export interface TaskSummary {
  task_id: string
  task_type: string
  source: 'prediction' | 'scan' | 'automation'
  status: TaskStatus
  progress: number | null
  error: string | null
  queued_at: string | null
  started_at: string | null
  completed_at: string | null
  target_profile_id: string | null
  target_username: string | null
  can_cancel: boolean
  metric_label: string | null
  metric_value: number | string | null
}

export interface TaskListResponse {
  running_count: number
  total: number
  tasks: TaskSummary[]
}
