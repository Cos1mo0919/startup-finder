export type Source = {
  url: string;
  publisher: string;
  kind: string;
  published_at: string;
  quotes: string[];
};
export type Component = {
  label: string;
  score: number;
  max: number;
  reason?: string;
  fact_index?: number;
};
export type Project = {
  id: string;
  name: string;
  creator: string;
  organization: string;
  city: string;
  event: string;
  country: string;
  category: string;
  primary_sector: string;
  sectors: string[];
  real_project_confidence: number;
  detection_signals?: { type: string; label: string; urls: string[] }[];
  evidence?: {
    id: number;
    source_id: string;
    url: string;
    evidence_type: string;
    label: string;
    confidence: number;
    quote: string;
    notes: string;
    discovered_at: string;
  }[];
  audience: string;
  rating: number;
  confidence: number;
  summary_uz: string;
  audience_groups: string[];
  first_seen: string;
  last_seen: string;
  published_at: string;
  images: { url: string; source_url: string; publisher: string }[];
  source_count: number;
  analysis_mode: string;
  rating_method: string;
  main_url?: string;
  aliases?: string[];
  sources?: Source[];
  rating_components?: Record<string, Component>;
  confidence_components?: Record<string, Component>;
  content?: {
    summary_uz: string;
    university: string;
    what_uz: string;
    how_uz: string;
    problem_uz: string;
    why_now_uz?: string;
    problem_analysis?: {
      affected_groups_uz: string;
      severity_uz: string;
      frequency_uz: string;
      solution_scope_uz: string;
      problem_severity_score: number | null;
      basis_fact_indexes: number[];
    };
    individual_benefit_uz: string;
    business_benefit_uz: string;
    advantages_uz: string[];
    limitations_uz: string[];
    facts: { text_uz: string; quote: string; source_url: string }[];
    ai_analysis_uz: string;
    links: Record<string, string>;
  };
};
export type Run = {
  details?: {
    mode?: string;
    window?: string[];
    summary?: {
      source_errors: number;
      parser_errors: number;
      event_errors: number;
      configuration_errors: number;
      ai_unavailable: boolean;
      pending: number;
    };
  };
  id: number;
  started_at: string;
  finished_at: string | null;
  status: string;
  counts: Record<string, number>;
  errors: { source: string; code: string }[];
  duration_seconds: number | null;
};
export type Status = {
  processing_summary: Record<string, number>;
  pending_reason_stats: Record<string, number>;
  language_stats: Record<string, number>;
  reject_reason_stats: { reason: string; label: string; count: number }[];
  origin_stats: ({ origin: string; label: string } & Record<
    string,
    string | number
  >)[];
  historical_counts: Record<string, number>;

  timezone: string;
  scheduler_enabled: boolean;
  next_run: string | null;
  last_run: Run | null;
  runs: Run[];
  total_projects: number;
  today_projects: number;
  pending_candidates: number;
  ai_enabled: boolean;
  search_enabled: boolean;
  sources: RegistrySource[];
  source_summary: {
    total: number;
    active: number;
    failed: number;
    priority_5: number;
    last_check: string | null;
  };
  event_summary: { total: number; today: number; projects_found: number };
  candidate_summary: {
    total: number;
    accepted: number;
    stop_filtered: number;
    ecosystem_signals: number;
    duplicates: number;
  };
  evidence_summary: {
    average: number;
    low_confidence: number;
    single_source: number;
    multiple_sources: number;
    hidden_projects: number;
    threshold: number;
  };
  events: {
    id: string;
    name: string;
    event_type: string;
    city: string;
    status: string;
    source_url: string;
    official_url: string | null;
    last_checked_at: string | null;
    last_error: string;
    projects_found: number;
    start_date: string | null;
    end_date: string | null;
    organizer: string;
  }[];
  rejected_candidates: {
    url: string;
    title: string;
    reason_labels: string[];
    evidence_score: number;
  }[];
  ecosystem_signals: {
    url: string;
    title: string;
    signal_type: string;
    published_at: string;
  }[];
  project_debug: {
    id: string;
    name: string;
    visible: boolean;
    confidence: number;
    real_project_confidence: number;
    signals: { label: string; urls: string[] }[];
    stop_reasons: string[];
  }[];
};

export type RegistrySource = {
  id: string;
  name: string;
  url: string;
  source_type: string;
  region: string;
  priority: number;
  check_frequency: number;
  reliability_score: number;
  enabled: boolean;
  collection_method: string;
  status: string;
  last_checked_at: string | null;
  last_success_at: string | null;
  next_check_at: string | null;
  consecutive_errors: number;
  candidates_found: number;
  new_projects: number;
  last_error: string;
  notes: string;
};
export type SectorStats = {
  period_days: number;
  total_projects: number;
  items: { sector: string; label: string; count: number; today: number }[];
};
