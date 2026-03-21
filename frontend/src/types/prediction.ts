export type PredictionStatus = 'queued' | 'running' | 'completed' | 'error' | 'cancelled'

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

export interface PredictionDetailResponse {
  prediction: PredictionRecord
  task: PredictionTask | null
  assessments: PredictionAssessment[]
}

export interface PredictionFeedbackPayload {
  assessment_status: 'correct' | 'wrong' | 'pending_review' | 'ignored'
  notes?: string
  observed_at?: string
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
  source: 'prediction' | 'scan'
  status: PredictionStatus
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
