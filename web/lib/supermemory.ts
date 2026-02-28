const API_BASE = "https://api.supermemory.ai";

function getApiKey() {
  const key = process.env.SUPERMEMORY_API_KEY;
  if (!key) throw new Error("SUPERMEMORY_API_KEY not set");
  return key;
}

async function smFetch<T>(path: string, body: Record<string, unknown>): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: {
      Authorization: `Bearer ${getApiKey()}`,
      "Content-Type": "application/json",
    },
    body: JSON.stringify(body),
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Supermemory ${path} failed (${res.status}): ${text}`);
  }
  return res.json() as Promise<T>;
}

// ── Types ──────────────────────────────────────────────────────────────

export interface MemoryDocument {
  id: string;
  status: "queued" | "processing" | "done";
}

export interface SearchResult {
  id: string;
  memory?: string;
  chunk?: string;
  similarity: number;
  metadata?: Record<string, unknown>;
  updatedAt?: string;
}

export interface SearchResponse {
  results: SearchResult[];
  total: number;
  timing: number;
}

export interface UnitProfile {
  profile: {
    static: string[];
    dynamic: string[];
  };
  searchResults?: SearchResponse;
}

// ── Add a memory (finding, report, etc.) ───────────────────────────────

export async function addMemory(opts: {
  content: string;
  containerTag: string;
  customId?: string;
  metadata?: Record<string, string | number | boolean>;
}): Promise<MemoryDocument> {
  return smFetch<MemoryDocument>("/v3/documents", {
    content: opts.content,
    containerTag: opts.containerTag,
    customId: opts.customId,
    metadata: opts.metadata,
  });
}

// ── Search memories (semantic) ─────────────────────────────────────────

export async function searchMemories(opts: {
  query: string;
  containerTag?: string;
  limit?: number;
}): Promise<SearchResponse> {
  return smFetch<SearchResponse>("/v4/search", {
    q: opts.query,
    containerTag: opts.containerTag,
    searchMode: "hybrid",
    limit: opts.limit ?? 10,
  });
}

// ── Get unit profile (compiled narrative) ──────────────────────────────

export async function getUnitProfile(opts: {
  containerTag: string;
  query?: string;
}): Promise<UnitProfile> {
  return smFetch<UnitProfile>("/v4/profile", {
    containerTag: opts.containerTag,
    q: opts.query,
  });
}
