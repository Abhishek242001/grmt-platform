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

function authHeaders(): Record<string, string> {
  if (typeof window === 'undefined') return {};
  const token = localStorage.getItem('grmt_access_token');
  return token ? { Authorization: `Bearer ${token}` } : {};
}

async function request<T>(
  path: string,
  options: RequestInit = {}
): Promise<T> {
  const resp = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      'Content-Type': 'application/json',
      ...authHeaders(),
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

export function resubmit(
  id: string,
  input: { title?: string; original_filename: string; original_file_url: string }
): Promise<Submission> {
  return request<Submission>(`/submissions/${id}/resubmit`, {
    method: 'POST',
    body: JSON.stringify(input),
  });
}

export function conferenceQueue(conferenceId: string): Promise<Submission[]> {
  return request<Submission[]>(`/conferences/${conferenceId}/submissions`);
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

export interface FlaggedAiChunk {
  text: string;
  start_char: number;
  end_char: number;
  word_count: number;
  ai_probability: number;
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

export function getWsTicket(): Promise<{ ticket: string; expires_in_seconds: number }> {
  return request('/ws/ticket', { method: 'POST' });
}
