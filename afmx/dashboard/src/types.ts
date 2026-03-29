/* ─── All API types — mirrors afmx backend schemas exactly ─── */

export type ExecutionStatus =
  | 'QUEUED' | 'RUNNING' | 'COMPLETED' | 'FAILED'
  | 'ABORTED' | 'TIMEOUT' | 'PARTIAL'

export type NodeStatus =
  | 'RUNNING' | 'SUCCESS' | 'FAILED' | 'SKIPPED'
  | 'ABORTED' | 'TIMEOUT' | 'FALLBACK'

export interface NodeResult {
  node_id:    string
  node_name:  string
  status:     NodeStatus
  output:     unknown
  error:      string | null
  error_type: string | null
  attempt:    number
  duration_ms:  number | null
  started_at:   number | null
  finished_at:  number | null
  metadata:   Record<string, unknown>
}

export interface ExecutionRecord {
  execution_id:   string
  matrix_id:      string
  matrix_name:    string
  status:         ExecutionStatus
  total_nodes:    number
  completed_nodes:number
  failed_nodes:   number
  skipped_nodes:  number
  duration_ms:    number | null
  error:          string | null
  error_node_id:  string | null
  node_results:   Record<string, NodeResult>
  queued_at:      number
  started_at:     number | null
  finished_at:    number | null
  tags:           string[]
  triggered_by:   string | null
}

export interface ExecutionListItem {
  execution_id:   string
  matrix_name:    string
  status:         ExecutionStatus
  total_nodes:    number
  completed_nodes:number
  failed_nodes:   number
  duration_ms:    number | null
  queued_at:      number
  triggered_by:   string | null
  tags:           string[]
}

export interface ExecutionListResponse {
  count:      number
  executions: ExecutionListItem[]
}

export interface PluginEntry {
  key:         string
  type:        'tool' | 'agent' | 'function'
  description: string
  version:     string
  tags:        string[]
  enabled:     boolean
}

export interface PluginListResponse {
  tools:     PluginEntry[]
  agents:    PluginEntry[]
  functions: PluginEntry[]
}

export interface StoredMatrix {
  name:        string
  version:     string
  description: string
  tags:        string[]
  created_at:  number
  updated_at:  number
  definition:  Record<string, unknown>
}

export interface MatrixListResponse {
  count:    number
  matrices: StoredMatrix[]
}

export interface AuditEvent {
  id:            string
  timestamp:     number
  action:        string
  actor:         string
  actor_id:      string
  actor_role:    string
  tenant_id:     string
  resource_type: string
  resource_id:   string
  outcome:       'success' | 'failure' | 'denied'
  ip_address:    string | null
  user_agent:    string | null
  duration_ms:   number | null
  error:         string | null
  details:       Record<string, unknown>
}

export interface AuditListResponse {
  count:  number
  events: AuditEvent[]
}

export interface ApiKey {
  id:           string
  key:          string
  name:         string
  role:         string
  tenant_id:    string
  created_at:   number
  expires_at:   number | null
  active:       boolean
  permissions:  string[]
  description:  string
  last_used_at: number | null
  created_by:   string | null
}

export interface ApiKeyListResponse {
  count: number
  keys:  ApiKey[]
}

export interface ConcurrencyStats {
  active:           number
  max_concurrent:   number
  peak_active:      number
  utilization_pct:  number
  queue_depth:      number
}

export interface AgentabilityStatus {
  enabled:   boolean
  connected: boolean
  db_path:   string | null
  api_url:   string | null
}

export interface HealthResponse {
  status:            string
  version:           string
  environment:       string
  store_backend:     string
  uptime_seconds:    number
  concurrency:       ConcurrencyStats
  active_executions: number
  adapters:          string[]
  rbac_enabled:      boolean
  audit_enabled:     boolean
  webhooks_enabled:  boolean
  ui_enabled:        boolean
  agentability:      AgentabilityStatus
}

export interface ValidateResponse {
  valid:           boolean
  errors:          string[]
  node_count:      number
  edge_count:      number
  execution_order: string[]
}

export interface ExecuteRequest {
  matrix:       Record<string, unknown>
  input?:       unknown
  variables?:   Record<string, unknown>
  metadata?:    Record<string, unknown>
  triggered_by?: string
  tags?:        string[]
}

export interface HookEntry {
  name:        string
  type:        string
  priority:    number
  enabled:     boolean
  node_filter: string | null
}

export interface StreamEvent {
  type:          string
  execution_id?: string
  matrix_id?:    string
  data?:         Record<string, unknown>
  timestamp?:    number
}

export interface ExecStats {
  total:            number
  completed:        number
  failed:           number
  partial:          number
  running:          number
  success_rate:     number
  avg_duration_ms:  number
  p95_duration_ms:  number
  timeline:         Array<{ bucket: number; completed: number; failed: number }>
}

/** Returned by GET /afmx/admin/stats */
export interface AdminStatsResponse {
  version:              string
  uptime_seconds:       number
  store_backend:        string
  executions_in_store:  number
  audit_events:         number
  api_keys:             number
  adapters:             string[]
  handlers:             number
}

// ─── v1.2: Cognitive Execution Matrix (open column axis) ─────────────────────

/**
 * The ROW axis — fixed universal sequence, never changes.
 * Valid for every industry and domain.
 */
export type CognitiveLayer =
  | 'PERCEIVE' | 'RETRIEVE' | 'REASON'
  | 'PLAN'     | 'ACT'      | 'EVALUATE' | 'REPORT'

/**
 * The COLUMN axis — open string, domain-specific.
 *
 * v1.2 change: agent roles are now plain strings, not a fixed union.
 * Any value from any domain pack is valid:
 *   Tech:          'OPS' | 'CODER' | 'ANALYST' | ...
 *   Finance:       'QUANT' | 'TRADER' | 'RISK_MANAGER' | ...
 *   Healthcare:    'CLINICIAN' | 'PHARMACIST' | 'NURSE' | ...
 *   Legal:         'PARALEGAL' | 'PARTNER' | 'ASSOCIATE' | ...
 *   Manufacturing: 'ENGINEER' | 'QUALITY_INSPECTOR' | ...
 *   Custom:        any UPPER_SNAKE_CASE string
 */
export type AgentRole = string

export interface MatrixCell {
  node_id:     string
  node_name:   string
  status:      NodeStatus | null
  duration_ms: number | null
  model_tier:  'cheap' | 'premium' | null
  model:       string | null
  error:       string | null
  attempt:     number
}

export interface MatrixViewSummary {
  total_possible: number
  active_cells:   number
  success_cells:  number
  failed_cells:   number
  coverage_pct:   number
  success_rate:   number
}

/** Metadata for a role string, sourced from a registered domain pack. */
export interface RoleMeta {
  description: string | null   // human-readable description from domain pack
  domain:      string | null   // domain pack name, e.g. 'finance', 'healthcare'
}

export interface MatrixViewResponse {
  execution_id: string
  matrix_name:  string
  status:       ExecutionStatus
  /** ROW headers — always the 7 fixed CognitiveLayer values */
  layers:       CognitiveLayer[]
  /** COLUMN headers — dynamically discovered from this execution's node results */
  roles:        AgentRole[]
  /** Domain pack metadata per role string (may be empty if role not in any pack) */
  role_meta:    Record<string, RoleMeta>
  /** Keyed as "LAYER:ROLE", e.g. "REASON:QUANT" or "ACT:CLINICIAN" */
  cells:        Record<string, MatrixCell>
  summary:      MatrixViewSummary
}

// Domain pack types (from GET /afmx/domains)
export interface DomainPack {
  name:        string
  description: string
  roles:       Record<string, string>   // role_name → description
  tags:        string[]
  role_count:  number
}

export interface DomainListResponse {
  count:   number
  domains: DomainPack[]
}
