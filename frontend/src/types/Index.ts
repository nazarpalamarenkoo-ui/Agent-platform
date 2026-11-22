export type ISODateString = string;

export interface PaginationParams {
  limit?: number;
  offset?: number;
}

export interface DetailResponse {
  detail: string;
}

export interface ValidationErrorItem {
  loc: (string | number)[];
  msg: string;
  type: string;
}

export interface ApiErrorBody {
  detail: string | ValidationErrorItem[];
}

export interface IdRef {
  id: number;
}

export type UserRole = "user" | "admin" | "super_admin";

export type AssignableRole = Extract<UserRole, "user" | "admin">;

export type DocumentType =
  | "book"
  | "architecture_doc"
  | "paper"
  | "manual"
  | "blog_post";

export type KnowledgeType = "principle" | "reference" | "example";

export type ToolAuthType = "none" | "api_key" | "bearer" | "oauth";

export type NotificationType = "skill_archived" | "tool_archived";

export type JobStatus = "pending" | "running" | "done" | "failed";

export type JobType =
  | "discovery_ingest"
  | "skill_generation"
  | "notify_skill_archived";

export type SkillVisibility = "private" | "pending_review" | "global";
export type DeviceStatus = "pending" | "approved" | "rejected" | "expired";
export type DocumentStatus = "pending" | "processing" | "indexed" | "failed";
export type DiscoveredDocumentDecision = "accept" | "reject";

export interface Token {
  access_token: string;
  token_type: string;
}

export interface SignInArgs {
  email: string;
  password: string;
}

export interface SignUpArgs {
  email: string;
  password: string;
  username: string;
}

export interface ResetPasswordArgs {
  token: string;
  new_password: string;
}

export type SignupConfirmationResponse = Token | DetailResponse;

export interface UserCreate {
  username: string;
  email: string;
  password: string;
}

export interface UserUpdate {
  username?: string | null;
  email?: string | null;
}

export interface ChangePassword {
  old_password: string;
  new_password: string;
}

export interface UserRead {
  id: number;
  username: string;
  email: string;
  role: UserRole;
  tokens_used: number;
  token_limit: number;
}

export interface AdminUserRead extends UserRead {
  created_at: ISODateString;
}

export interface RoleUpdate {
  role: AssignableRole;
}

export interface TokenLimitUpdate {
  /** >= 0 */
  token_limit: number;
}

export interface AdminUsersParams extends PaginationParams {
  // limit: 1..200 (default 50)
}

export interface AdminUserSkillsParams extends PaginationParams {
  include_archived?: boolean;
}

export interface AdminUserToolsParams {
  include_archived?: boolean;
}

export interface AdminSkillListItem {
  id: number;
  skill_name: string;
  description: string;
  archived_at: ISODateString | null;
  updated_at: ISODateString;
}

export interface AdminSkillRead extends AdminSkillListItem {
  content: string;
  owner_id: number | null;
}

export interface ArchiveForViolation {
  reason: string;
}

export interface AccessLogEntry {
  id: number;
  admin_id: number | null;
  skill_id: number | null;
  action: string;
  note: string | null;
  created_at: ISODateString;
}

export interface AdminToolItem {
  id: number;
  tool_name: string;
  description: string;
  url_masked: string;
  archived_at: ISODateString | null;
}

export interface UserOverview {
  user_id: number;
  private_skills: number;
  private_tools: number;
  bundles: number;
  token_events: number;
  tokens_used: number;
  token_limit: number;
}

export interface DomainCreate {
  slug: string;
  name: string;
  description: string;
  parent_domain_id?: number | null;
}

export interface DomainRead {
  id: number;
  slug: string;
  name: string;
  description: string;
  parent_domain_id: number | null;
  children: DomainRead[];
}

export interface SkillCreate {
  skill_name: string;
  description: string;
  content: string;
  domain_ids?: number[];
}

export interface SkillUpdate {
  description?: string | null;
  content?: string | null;
}

export interface SkillRead {
  id: number;
  skill_name: string;
  description: string;
  skill_selected_freq: number;
  visibility?: SkillVisibility;
}
export interface SkillSummary {
  id: number;
  skill_name: string;
  description: string;
}

export interface SkillsParams extends PaginationParams {
  domain_id?: number;
  include_archived?: boolean;
}

export interface ToolCreate {
  tool_name: string;
  description: string;
  url: string;
  auth_type?: ToolAuthType;
  auth_description?: string | null;
  domain_ids?: number[];
}

export interface ToolUpdate {
  /** max 255 */
  description?: string | null;
  /** max 2048 */
  url?: string | null;
  auth_type?: ToolAuthType | null;
  /** max 255 */
  auth_description?: string | null;
}

export interface ToolRead {
  id: number;
  tool_name: string;
  description: string;
  url: string;
  auth_type: ToolAuthType;
  auth_description: string | null;
  tool_selected_freq: number;
}

export interface ToolSummary {
  id: number;
  tool_name: string;
  description: string;
}

export interface ToolsParams extends PaginationParams {
  domain_id?: number;
  include_archived?: boolean;
}

export interface MyToolCreate {
  /** 1..100 */
  tool_name: string;
  /** 1..255 */
  description: string;
  /** 1..2048 */
  url: string;
  auth_type?: ToolAuthType;
  /** max 255 */
  auth_description?: string | null;
  domain_ids?: number[];
}

export interface MyToolUpdate {
  /** 1..255 */
  description?: string | null;
  /** 1..2048 */
  url?: string | null;
  auth_type?: ToolAuthType | null;
  /** max 255 */
  auth_description?: string | null;
}

export interface MyToolRead {
  id: number;
  tool_name: string;
  description: string;
  url: string;
  auth_type: ToolAuthType;
  auth_description: string | null;
  archived_at: ISODateString | null;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface MyToolResponse {
  tool: MyToolRead;
  warnings: string[];
}

export interface MyToolsParams extends PaginationParams {
  include_archived?: boolean;
}


export interface AgentCreate {
  name: string;
  description: string;
  skill_ids: number[];
  tool_ids: number[];
}

export interface AgentUpdate {
  /** max 255 */
  description?: string | null;
  skill_ids?: number[] | null;
  tool_ids?: number[] | null;
}

export interface AgentRead {
  id: number;
  agent_name: string;
  description: string;
  skills: SkillSummary[];
  tools: ToolSummary[];
}

export interface AgentsParams extends PaginationParams {
  include_archived?: boolean;
}

export interface CustomAgentCreate {
  name: string;
  description?: string;
  skill_ids?: number[];
  tool_ids?: number[];
  knowledge_pack_ids?: number[];
}

export interface CustomAgentRead {
  id: number;
  name: string;
  description: string;
  agent_id: number;
  skills: IdRef[];
  tools: IdRef[];
  knowledge_packs: IdRef[];
}

export interface KnowledgePackCreate {
  name: string;
  domain_id: number;
  description: string;
  slug: string;
}

export interface KnowledgePackRead {
  id: number;
  name: string;
  slug: string;
  domain_id: number;
  description: string;
  version: number;
}

export interface KnowledgePacksParams extends PaginationParams {
  include_archived?: boolean;
}

export interface AgentProfileBriefRead {
  id: number;
  agent_name: string;
  description: string;
}

export interface ConfigBundleCreate {
  agent_id?: number | null;
  agent_ids?: number[];
  name: string;
  description: string;
  skill_ids: number[];
  tool_ids: number[];
  knowledge_pack_ids?: number[];
}

export interface ConfigBundleFromAgent {
  agent_id?: number | null;
  agent_ids?: number[];
  name: string;
  description: string;
}

export interface ConfigBundleClone {
  name: string;
  description?: string | null;
}

export interface ConfigBundleUpdate {
  /** 1..100 */
  name?: string | null;
  /** max 255 */
  description?: string | null;
}

export interface ConfigBundleRead {
  id: number;
  user_id: number;
  agent_id: number | null;
  agent_profiles?: AgentProfileBriefRead[];
  name: string;
  description: string;
  skills: SkillSummary[];
  tools: ToolSummary[];
  knowledge_packs: KnowledgePackRead[];
}

export interface BundleItems {
  agent_ids?: number[];
  skill_ids?: number[];
  tool_ids?: number[];
  knowledge_pack_ids?: number[];
}

export interface ConfigBundlesParams extends PaginationParams {
  agent_id?: number;
  user_id?: number;
}

export interface EffectiveSkillRead {
  id: number;
  name: string;
  content_hash: string;
  archived: boolean;
}

export interface EffectiveToolRead {
  id: number;
  name: string;
  url: string;
  auth_type: ToolAuthType;
  archived: boolean;
}

export interface EffectivePackRead {
  id: number;
  slug: string;
  version: number;
  archived: boolean;
}

export interface EffectiveBundleRead {
  bundle_id: number;
  agent_id: number;
  agent_name: string;
  agent_profiles?: AgentProfileBriefRead[];
  skills: EffectiveSkillRead[];
  tools: EffectiveToolRead[];
  packs: EffectivePackRead[];
  version_hash: string;
}

export interface IngestFileRequest {
  source: string;
  document_type: DocumentType;
  knowledge_type: KnowledgeType;
  knowledge_pack_id: number;
}

export interface IngestWebRequest {
  query: string;
  document_type: DocumentType;
  knowledge_type: KnowledgeType;
  knowledge_pack_id: number;
}

export interface CorpusBuilderResult {
  succeeded: number[];
  skipped_duplicates: string[];
  failed: Record<string, unknown>[];
}

export interface JobCreatedResponse {
  job_id: number;
  status: JobStatus;
}

export interface JobStatusResponse {
  id: number;
  job_type: JobType;
  status: JobStatus;
  result: Record<string, unknown> | null;
  error: string | null;
  created_at: ISODateString;
  started_at: ISODateString | null;
  finished_at: ISODateString | null;
}

export interface SearchRequest {
  query: string;
  /** default 20 */
  limit?: number;
  /** default 5 */
  top_n?: number;
  /** default 60 */
  k?: number;
  config_bundle_id: number;
}

export interface SearchResultResponse {
  id: string;
  score: number;
  payload: Record<string, unknown>;
}

export interface SearchAgenticRequest {
  query: string;
  config_bundle_id: number;
}

export interface AgenticEvidenceResponse {
  query: string;
  chunk_id: string;
  score: number;
  text: string;
  metadata: Record<string, unknown>;
}

export interface EvaluationResponse {
  sufficient: boolean;
  coverage: number;
  confidence: number;
  redundancy: number;
  missing_topics: string[];
  retry_queries: string[];
}

export interface IterationResponse {
  iteration: number;
  subqueries: string[];
  new_evidence_count: number;
  total_evidence_count: number;
  evaluation: EvaluationResponse;
}

export interface SearchAgenticResponse {
  initial_subqueries: string[];
  reasoning: string;
  evidence: AgenticEvidenceResponse[];
  iterations: IterationResponse[];
  degraded_to_hybrid: boolean;
}

export interface HintRequest {
  intent: string;
}

export interface HintRef {
  id: number;
  name: string;
}

export interface HintItem extends HintRef {
  description: string | null;
}

export interface HintProfile extends HintItem {
  base_skills: HintRef[];
  base_tools: HintRef[];
}

export type HintGapKind = "skill" | "tool" | "pack";

export interface HintGap {
  kind: HintGapKind;
  name: string;
  description: string;
  reason: string;
}

export interface HintResponse {
  agent_profile: HintProfile | null;
  skills: HintItem[];
  tools: HintItem[];
  knowledge_packs: HintItem[];
  reasoning: string;
  gaps?: HintGap[];
  generated_skill?: SkillDraftResult | null;
}

export interface NotificationRead {
  id: number;
  type: NotificationType;
  skill_id: number | null;
  tool_id: number | null;
  item_name: string | null;
  read_at: ISODateString | null;
  created_at: ISODateString;
}

export interface UnreadCount {
  unread: number;
}

export interface MarkedRead {
  updated: number;
}

export interface NotificationsParams extends PaginationParams {
  unread_only?: boolean;
}

export interface DeviceTokenCreate {
  scope: string;
  name?: string;
  config_bundle_id?: number | null;
}

export interface DeviceRead {
  id: number;
  name: string;
  config_bundle_id: number | null;
  expires_at: ISODateString;
}

export interface DeviceTokenIssued extends DeviceRead {
  access_token: string;
  token_type: string;
}

export interface DevicesParams extends PaginationParams {
  active_only?: boolean;
}

export interface MySkillCreate {
  /** 1..100 */
  skill_name: string;
  /** 1..255 */
  description: string;
  /** 1..50 000 */
  content: string;
  domain_ids?: number[];
}

export interface MySkillImport {
  /** 1..60 000 */
  markdown: string;
  /** max 100 */
  skill_name?: string | null;
  /** max 255 */
  description?: string | null;
  domain_ids?: number[];
}

export interface MySkillUpdate {
  /** 1..100 */
  skill_name?: string | null;
  /** 1..255 */
  description?: string | null;
  /** 1..50 000 */
  content?: string | null;
}

export interface MySkillSummary {
  id: number;
  skill_name: string;
  description: string;
  content_hash: string;
  visibility: SkillVisibility;
  archived_at: ISODateString | null;
}

export interface MySkillRead extends MySkillSummary {
  content: string;
  created_at: ISODateString;
  updated_at: ISODateString;
}

export interface MySkillsParams extends PaginationParams {
  include_archived?: boolean;
}


export interface SkillDraftRequest {
  intent: string;
  /** max 100 */
  skill_name?: string | null;
  /** max 255 */
  description?: string | null;
  source_text?: string | null;
  config_bundle_id?: number | null;
  /** max 10*/
  knowledge_pack_ids?: number[];
  /** max 3 */
  search_queries?: string[];
  /** default false */
  auto_packs?: boolean;
}

export interface SkillDraftJobResponse {
  job_id: number;
  status: JobStatus;
}

export interface UsedPack {
  id: number | null;
  slug: string;
  name: string;
  domain_id: number | null;
  chunks: number;
}

export interface SkillDraftResult {
  skill_name: string;
  description: string;
  content: string;
  grounded: boolean;
  sources: string[];
  used_packs: UsedPack[];
  warnings: string[];
}

export interface SkillDraftStatus {
  job_id: number;
  status: JobStatus;
  error: string | null;
  draft: SkillDraftResult | null;
}

export interface SkillDraftConfirm {
  /** 1..100 */
  skill_name?: string | null;
  /** 1..255 */
  description?: string | null;
  /** 1..50 000 */
  content?: string | null;
  domain_ids?: number[];
}

export interface PackRef {
  id: number;
  slug: string;
  name: string;
  description: string;
}

export interface PackSuggestion {
  packs: PackRef[];
  queries: string[];
}

export interface SuggestPacksRequest {
  /** 1..2000 */
  intent: string;
}

export interface AttachPacksRequest {
  config_bundle_id: number;
}

export interface AttachPacksResponse {
  bundle_id: number;
  knowledge_pack_ids: number[];
}