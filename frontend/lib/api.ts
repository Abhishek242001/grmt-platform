const DEFAULT_API_BASE_URL = '/api';
const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL || DEFAULT_API_BASE_URL;

export type Role = 'researcher' | 'organizer' | 'reviewer' | 'platform_admin';

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: Role;
  is_email_verified: boolean;
}

export interface TokenResponse {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: User;
}

export class ApiError extends Error {
  status: number;
  detail: string;
  constructor(status: number, detail: string) {
    super(detail);
    this.status = status;
    this.detail = detail;
  }
}

async function parseErrorDetail(resp: Response): Promise<string> {
  try {
    const body = await resp.json();
    if (typeof body.detail === 'string') return body.detail;
    if (Array.isArray(body.detail)) {
      return body.detail
        .map((e: { msg: string }) => e.msg)
        .join('; ');
    }
    return `Request failed (${resp.status})`;
  } catch {
    return `Request failed (${resp.status})`;
  }
}

function authHeaders(tokenOverride?: string): Record<string, string> {
  if (tokenOverride) return { Authorization: `Bearer ${tokenOverride}` };
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('grmt_access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options: RequestInit = {},
  tokenOverride?: string
): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(tokenOverride),
      ...(options.headers || {}),
    },
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp));
  }
  if (resp.status === 204) return undefined as T;
  return resp.json() as Promise<T>;
}

// ── Auth ─────────────────────────────────────────────────────────

export function signup(input: {
  email: string;
  password: string;
  full_name: string;
  role: 'researcher' | 'organizer' | 'reviewer';
}): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/signup', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function login(input: {
  email: string;
  password: string;
}): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/login', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

// The backend's admin-login endpoint deliberately returns a differently-
// shaped response (AdminUserOut: {id, username, full_name, role} — no
// email field at all, since a real admin identifier is a plain username,
// not a real email — see backend/app/schemas/auth.py's AdminLoginRequest
// docstring for why). Mapped here into the same User/TokenResponse shape
// everything else already uses, so useAuth()'s user state and every
// existing role-gated page work identically regardless of which login
// path was actually used — that translation belongs at this API-boundary
// function, not spread across the app.
interface AdminTokenResponseRaw {
  access_token: string;
  refresh_token: string;
  token_type: string;
  user: { id: string; username: string; full_name: string; role: Role };
}

export function adminLogin(input: { username: string; password: string }): Promise<TokenResponse> {
  return request<AdminTokenResponseRaw>('/auth/admin-login', {
    method: 'POST',
    body: JSON.stringify(input),
  }).then((raw) => ({
    access_token: raw.access_token,
    refresh_token: raw.refresh_token,
    token_type: raw.token_type,
    user: {
      id: raw.user.id,
      email: raw.user.username, // mapped — see comment above
      full_name: raw.user.full_name,
      role: raw.user.role,
      is_email_verified: true, // admin accounts are seeded pre-verified, no real email to verify
    },
  }));
}

export function refreshToken(refresh_token: string): Promise<TokenResponse> {
  return request<TokenResponse>('/auth/refresh', {
    method: 'POST',
    body: JSON.stringify({ refresh_token }),
  });
}

export function getMe(accessToken: string): Promise<User> {
  return request<User>('/auth/me', {
    headers: { Authorization: `Bearer ${accessToken}` },
  });
}

// ── Conferences ──────────────────────────────────────────────────

export interface Conference {
  id: string;
  organizer_id: string;
  name: string;
  description: string | null;
  publisher_format: string;
}

export function listConferences(): Promise<Conference[]> {
  return request<Conference[]>('/conferences');
}

export function getConference(id: string): Promise<Conference> {
  return request<Conference>(`/conferences/${id}`);
}

export function createConference(input: {
  name: string;
  description?: string;
  publisher_format?: string;
}): Promise<Conference> {
  return request<Conference>('/conferences', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function updateConference(
  id: string,
  input: Partial<{ name: string; description: string; publisher_format: string }>
): Promise<Conference> {
  return request<Conference>(`/conferences/${id}`, {
    method: 'PATCH',
    body: JSON.stringify(input),
  });
}

// ── Gate rules ───────────────────────────────────────────────────

export interface GateRule {
  check_type: string;
  is_hard_gate: boolean;
  threshold: number | null;
}

export function getGateRules(conferenceId: string): Promise<GateRule[]> {
  return request<GateRule[]>(`/conferences/${conferenceId}/gate-rules`);
}

export function updateGateRules(
  conferenceId: string,
  rules: GateRule[]
): Promise<GateRule[]> {
  return request<GateRule[]>(`/conferences/${conferenceId}/gate-rules`, {
    method: 'PUT',
    body: JSON.stringify(rules),
  });
}

// ── Reviewers / co-admins ───────────────────────────────────────

export interface MemberRow {
  id: string;
  reviewer_id?: string; // present on reviewer rows specifically — the underlying user id, distinct from this row's own id
  email: string;
  full_name: string;
}

export function listReviewers(conferenceId: string): Promise<MemberRow[]> {
  return request<MemberRow[]>(`/conferences/${conferenceId}/reviewers`);
}

export function addReviewer(conferenceId: string, email: string): Promise<MemberRow> {
  return request<MemberRow>(`/conferences/${conferenceId}/reviewers`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function removeReviewer(conferenceId: string, rowId: string): Promise<void> {
  return request<void>(`/conferences/${conferenceId}/reviewers/${rowId}`, {
    method: 'DELETE',
  });
}

export function listCoAdmins(conferenceId: string): Promise<MemberRow[]> {
  return request<MemberRow[]>(`/conferences/${conferenceId}/coadmins`);
}

export function addCoAdmin(conferenceId: string, email: string): Promise<MemberRow> {
  return request<MemberRow>(`/conferences/${conferenceId}/coadmins`, {
    method: 'POST',
    body: JSON.stringify({ email }),
  });
}

export function removeCoAdmin(conferenceId: string, rowId: string): Promise<void> {
  return request<void>(`/conferences/${conferenceId}/coadmins/${rowId}`, {
    method: 'DELETE',
  });
}

// ── Submissions ──────────────────────────────────────────────────

export interface Submission {
  id: string;
  conference_id: string;
  researcher_id: string;
  title: string;
  status: string;
  previously_rejected_disclosure?: string | null;
  camera_ready_file_url?: string | null;
  copyright_transfer_file_url?: string | null;
}

export interface SubmissionVersion {
  id: string;
  version_number: number;
  original_filename: string;
  converted_pdf_url: string | null;
}

export function createSubmission(input: {
  conference_id: string;
  title: string;
  original_filename: string;
  original_file_url: string;
  previously_rejected_disclosure?: string;
}): Promise<Submission> {
  return request<Submission>('/submissions', {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function mysubmissions(): Promise<Submission[]> {
  return request<Submission[]>('/submissions/mine');
}

export function assignedSubmissions(): Promise<Submission[]> {
  return request<Submission[]>('/submissions/assigned');
}

export function getSubmission(id: string): Promise<Submission> {
  return request<Submission>(`/submissions/${id}`);
}

export function getSubmissionHistory(id: string): Promise<SubmissionVersion[]> {
  return request<SubmissionVersion[]>(`/submissions/${id}/history`);
}

export async function resubmit(id: string, file: File, title?: string): Promise<SubmissionVersion> {
  const form = new FormData();
  form.append('file', file);
  if (title) form.append('title', title);
  const resp = await fetch(`${API_BASE_URL}/submissions/${id}/resubmit`, {
    method: 'POST',
    headers: authHeaders(), // no Content-Type — browser sets the multipart boundary itself
    body: form,
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp));
  }
  return resp.json();
}

// update51 — per-submission reviewer assignment (organizer/co-admin only).
export interface ReviewerAssignment {
  id: string;
  submission_id: string;
  reviewer_id: string;
  assigned_by: string;
}

export function assignReviewer(submissionId: string, reviewerId: string): Promise<ReviewerAssignment> {
  return request<ReviewerAssignment>(`/submissions/${submissionId}/assign-reviewer`, {
    method: 'POST',
    body: JSON.stringify({ reviewer_id: reviewerId }),
  });
}

export function listAssignedReviewers(submissionId: string): Promise<ReviewerAssignment[]> {
  return request<ReviewerAssignment[]>(`/submissions/${submissionId}/assigned-reviewers`);
}

export function unassignReviewer(submissionId: string, reviewerId: string): Promise<void> {
  return request<void>(`/submissions/${submissionId}/assign-reviewer/${reviewerId}`, { method: 'DELETE' });
}

export function conferenceQueue(conferenceId: string): Promise<Submission[]> {
  return request<Submission[]>(`/conferences/${conferenceId}/submissions`);
}

// update51 — the researcher's explicit review-then-submit checkpoint.
// Fails with a real, distinct message depending on why: still processing,
// hard-failed a required check (must revise, not just retry), or already
// submitted — see ApiError.detail for exactly which.
export function submitForReview(id: string): Promise<Submission> {
  return request<Submission>(`/submissions/${id}/submit-for-review`, { method: 'POST' });
}

export async function submitCameraReady(
  id: string,
  file: File,
  copyrightTransferFile?: File
): Promise<Submission> {
  const form = new FormData();
  form.append('file', file);
  if (copyrightTransferFile) form.append('copyright_transfer_file', copyrightTransferFile);
  const resp = await fetch(`${API_BASE_URL}/submissions/${id}/camera-ready`, {
    method: 'POST',
    headers: authHeaders(),
    body: form,
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp));
  }
  return resp.json();
}

// ── AI reports ───────────────────────────────────────────────────

export interface AIReport {
  id: string;
  submission_id: string;
  check_type: string;
  status: string;
  result_json: string | null;
}

export interface GrammarCheckResult {
  status: string;
  error?: string;
  error_count: number;
  word_count?: number;
  score: number | null;
  chunks_checked?: number;
  chunks_total?: number;
  matches: {
    message: string;
    short_message: string;
    offset: number;
    length: number;
    rule_id: string;
    category: string;
    page: number | null;
  }[];
}

export interface FormatCheckResult {
  status: string;
  error?: string;
  publisher_format?: string;
  measurements?: Record<string, number | string | null>;
  checks_passed: number;
  checks_total: number;
  score: number | null;
  issues: string[];
}

export interface TableFigureCheckResult {
  status: string;
  error?: string;
  figures_found?: boolean;
  tables_found?: boolean;
  checks_passed: number;
  checks_total: number;
  score: number | null;
  issues: string[];
}

export interface HighlightBox {
  xPct: number;
  yPct: number;
  wPct: number;
  hPct: number;
}

export interface HighlightBoxesForPage {
  page: number;
  boxes: HighlightBox[];
}

export interface FlaggedAiChunk {
  text: string;
  start_char: number;
  end_char: number;
  word_count: number;
  ai_probability: number;
  highlight_boxes?: HighlightBoxesForPage[];
}

export interface AiTextDetectionResult {
  status: string;
  error?: string;
  ai_generated_percentage?: number;
  ai_word_count?: number;
  total_word_count?: number;
  overall_verdict?: 'accept' | 'reject';
  total_chunk_count?: number;
  flagged_chunk_count?: number;
  flagged_chunks?: FlaggedAiChunk[];
  chunk_probability_threshold?: number;
  max_ai_percentage?: number;
}

export interface CitationCheckResult {
  status: string;
  error?: string;
  broken_citations?: string[];
  uncited_references?: string[];
  total_citations?: number;
  total_bibliography_entries?: number;
  score: number | null;
  issues: string[];
}

export interface PlagiarismSelfMatch {
  submission_id: string;
  similarity: number; // 0-1
}

export interface PlagiarismExternalMatch {
  source_url: string | null;
  source_title: string | null;
  similarity_pct: number;
  plagiarized_word_count: number;
  can_access: boolean | null; // false = Winston found this source but couldn't fetch its full text to actually compare — a 0% here means "couldn't check", not "checked and dissimilar"
  matched_spans: Array<{ start_char: number | null; end_char: number | null; text: string | null }>;
}

export interface PlagiarismExternalResult {
  status: string; // 'complete' | 'error'
  error?: string;
  error_code?: string;
  // present when status === 'complete'
  overall_similarity_pct?: number;
  word_count?: number;
  plagiarized_word_count?: number;
  source_count?: number;
  matches?: PlagiarismExternalMatch[];
  credits_used?: number;
  credits_remaining?: number;
}

export interface PlagiarismCheckResult {
  status: string;
  error?: string;
  score: number | null; // 100 = no concerning overlap found (higher is better, same convention as citation/format)
  highest_similarity?: number; // 0-1, self-submission comparison only
  matches?: PlagiarismSelfMatch[]; // self-submission matches
  candidates_compared?: number;
  candidates_skipped_too_short?: number;
  flag_threshold?: number;
  external: PlagiarismExternalResult | null; // null = no external provider configured/active at check time
  issues: string[];
}

export interface LogicalConsistencyFinding {
  abstract_claim: string;
  conclusion_statement: string;
  explanation: string;
}

export interface LogicalConsistencyResult {
  status: string;
  error?: string;
  consistent?: boolean;
  findings?: LogicalConsistencyFinding[];
  score: number | null;
  issues: string[];
}

export function getAiReports(submissionId: string): Promise<AIReport[]> {
  return request<AIReport[]>(`/submissions/${submissionId}/ai-report`);
}

export async function uploadSubmissionFile(submissionId: string, file: File): Promise<SubmissionVersion> {
  const form = new FormData();
  form.append('file', file);
  const resp = await fetch(`${API_BASE_URL}/submissions/${submissionId}/upload`, {
    method: 'POST',
    headers: authHeaders(), // no Content-Type — browser sets the multipart boundary itself
    body: form,
  });
  if (!resp.ok) {
    throw new ApiError(resp.status, await parseErrorDetail(resp));
  }
  return resp.json();
}

// ── Reviews / decisions ──────────────────────────────────────────

export interface Review {
  id: string;
  submission_id: string;
  reviewer_id: string;
  recommendation: string;
  comments: string | null;
}

export interface Decision {
  id: string;
  submission_id: string;
  decided_by: string;
  decision: string;
  notes: string | null;
}

export function submitReview(
  submissionId: string,
  input: { recommendation: string; comments?: string }
): Promise<Review> {
  return request<Review>(`/submissions/${submissionId}/reviews`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function listReviews(submissionId: string): Promise<Review[]> {
  return request<Review[]>(`/submissions/${submissionId}/reviews`);
}

export function makeDecision(
  submissionId: string,
  input: { decision: string; notes?: string }
): Promise<Decision> {
  return request<Decision>(`/submissions/${submissionId}/decision`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function getDecision(submissionId: string): Promise<Decision | null> {
  return request<Decision>(`/submissions/${submissionId}/decision`).catch((e) => {
    if (e instanceof ApiError && e.status === 404) return null;
    throw e;
  });
}

// ── Analytics ────────────────────────────────────────────────────

export interface ConferenceAnalytics {
  conference_id: string;
  total_submissions: number;
  submissions_by_status: Record<string, number>;
  total_reviews_submitted: number;
  total_decisions_made: number;
  average_reviews_per_submission: number;
}

export function getAnalytics(conferenceId: string): Promise<ConferenceAnalytics> {
  return request<ConferenceAnalytics>(`/conferences/${conferenceId}/analytics`);
}

// ── Files / annotations ──────────────────────────────────────────

export interface SignedUrl {
  url: string;
  expires_in_seconds: number;
}

export interface Annotation {
  id: string;
  submission_version_id: string;
  reviewer_id: string;
  page_number: number;
  position_json: string;
  color: string;
  comment: string | null;
}

export interface AnnotationCreate {
  page_number: number;
  position_json: string;
  color?: string;
  comment?: string;
}

export function getPdfUrl(versionId: string): Promise<SignedUrl> {
  return request<SignedUrl>(`/submissions/versions/${versionId}/pdf-url`);
}

export function getAnnotations(versionId: string): Promise<Annotation[]> {
  return request<Annotation[]>(`/submissions/versions/${versionId}/annotations`);
}

export function createAnnotation(versionId: string, input: AnnotationCreate): Promise<Annotation> {
  return request<Annotation>(`/submissions/versions/${versionId}/annotations`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function deleteAnnotation(annotationId: string): Promise<void> {
  return request<void>(`/submissions/annotations/${annotationId}`, { method: 'DELETE' });
}

// ── WebSocket ────────────────────────────────────────────────────

export function getWsTicket(tokenOverride?: string): Promise<{ ticket: string; expires_in_seconds: number }> {
  return request('/ws/ticket', { method: 'POST' }, tokenOverride);
}

// ── Admin panel ──────────────────────────────────────────────────

export interface ApiProviderStatus {
  provider: 'gptzero' | 'winston';
  is_configured: boolean;
  is_active: boolean;
  masked_key: string | null;
}

export interface ApiUsageSummary {
  totals_by_provider: Record<string, { total_requests: number; successful_requests: number }>;
  hourly_breakdown: Array<Record<string, string | number>>;
}

export interface SystemMetrics {
  timestamp: number;
  cpu_utilization_pct: number;
  cpu_core_count: number;
  cpu_per_core_pct: number[];
  memory_used_pct: number;
  memory_used_gb: number;
  memory_total_gb: number;
  swap_used_pct: number;
  disk_used_pct: number;
  disk_used_gb: number;
  disk_total_gb: number;
  disk_read_mb_s: number;
  disk_write_mb_s: number;
  network_sent_mb_s: number;
  network_recv_mb_s: number;
  load_average_1m: number;
  load_average_5m: number;
  load_average_15m: number;
  process_count: number;
  uptime_seconds: number;
  gpu_utilization_pct: number | null;
  gpu_memory_used_mb: number | null;
  gpu_memory_total_mb: number | null;
  gpu_temperature_c: number | null;
}

// update51: every admin function below takes an explicit adminToken rather
// than relying on request()'s automatic localStorage lookup — the admin
// panel now authenticates via its own sessionStorage-based, tab-scoped
// token (see admin-auth-context.tsx), completely separate from the shared
// researcher/organizer/reviewer localStorage session. Passing the token
// explicitly here is what makes that isolation actually work end to end,
// rather than silently falling back to whichever session happens to be in
// localStorage — see the session-isolation bug this was built to fix.
export function getApiProviders(adminToken: string): Promise<ApiProviderStatus[]> {
  return request('/admin/api-keys', {}, adminToken);
}

export function setApiKey(provider: 'gptzero' | 'winston', key: string, adminToken: string): Promise<ApiProviderStatus> {
  return request(`/admin/api-keys/${provider}`, {
    method: 'PUT',
    body: JSON.stringify({ key }),
  }, adminToken);
}

export function activateApiProvider(provider: 'gptzero' | 'winston', adminToken: string): Promise<ApiProviderStatus[]> {
  return request(`/admin/api-keys/${provider}/activate`, { method: 'POST' }, adminToken);
}

export function getApiUsage(adminToken: string): Promise<ApiUsageSummary> {
  return request('/admin/api-usage', {}, adminToken);
}
