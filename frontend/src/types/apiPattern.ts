export interface CurlField {
  key: string
  value: string
  selected: boolean
  reason: string
}

export interface CurlSuggestions {
  cookies: CurlField[]
  headers: CurlField[]
  data: CurlField[]
  variables: CurlField[]
}

export interface CurlParseResult {
  url: string
  http_method: string
  cookies: Record<string, string>
  headers: Record<string, string>
  data: Record<string, string>
  variables: Record<string, unknown> | null
  suggestions: CurlSuggestions
}

export interface ApiCurlPattern {
  id: number
  app_user_id: string
  internal_name: string
  display_name: string
  curl_command: string
  url: string
  http_method: string
  selected_cookies: string[]
  selected_headers: string[]
  selected_data: string[]
  selected_variables: string[]
  generated_script: string | null
  is_active: number
  created_at: string
  updated_at: string
}

export interface PatternTestResult {
  status_code: number | null
  elapsed_ms: number
  response_text: string
  success: boolean
}

export interface ProjectedField {
  name: string
  kind: "constant" | "runtime" | "session"
  value: string
  omitted: boolean
  nested?: ProjectedField[]
}

export interface ProjectedCase {
  runtime_values: Record<string, string | boolean>
  url: string
  headers: Record<string, string>
  cookies: Record<string, string>
  query_params: ProjectedField[]
  body: string | null
  body_fields: ProjectedField[]
}

export interface PatternProjection {
  internal_name: string
  display_name: string
  http_method: string
  runtime_keys: string[]
  defaults: Record<string, string | boolean>
  cases: ProjectedCase[]
}


