import {
  EncounterSummary,
  EncounterDetailResponse,
  ClinicalEncounter,
  ClinicalNote,
  IngestAudioResponse,
} from "./types";

// The web client and API are deliberately same-origin. Clerk web sessions are
// cookie based; a separate API origin would not receive the secure session.
const API_BASE_URL = "";

function getHeaders(extra: Record<string, string> = {}) {
  return {
    "Content-Type": "application/json",
    ...extra,
  };
}

async function handle<T>(res: Response): Promise<T> {
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`API error ${res.status}: ${text}`);
  }
  return res.json() as Promise<T>;
}

export async function getEncounters(): Promise<EncounterSummary[]> {
  const res = await fetch(`${API_BASE_URL}/api/v1/encounters?own_only=true`, {
    headers: getHeaders(),
    credentials: "include",
  });
  return handle<EncounterSummary[]>(res);
}

export async function createEncounter(input: {
  patient_id?: string;
  title?: string;
}): Promise<ClinicalEncounter> {
  const res = await fetch(`${API_BASE_URL}/api/v1/encounters`, {
    method: "POST",
    headers: getHeaders(),
    credentials: "include",
    body: JSON.stringify(input),
  });
  return handle<ClinicalEncounter>(res);
}

export async function getEncounterDetail(id: string): Promise<EncounterDetailResponse> {
  const res = await fetch(`${API_BASE_URL}/api/v1/encounters/${id}`, {
    headers: getHeaders(),
    credentials: "include",
  });
  return handle<EncounterDetailResponse>(res);
}

export async function updateEncounterNote(
  encounterId: string,
  input: {
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
    finalize?: boolean;
  }
): Promise<ClinicalNote> {
  const res = await fetch(`${API_BASE_URL}/api/v1/encounters/${encounterId}/note`, {
    method: "PUT",
    headers: getHeaders(),
    credentials: "include",
    body: JSON.stringify({ ...input, finalize: !!input.finalize }),
  });
  return handle<ClinicalNote>(res);
}

export async function uploadAudio(params: {
  encounterId: string;
  file: File;
  languageCode?: string;
  targetLanguage?: string;
}): Promise<IngestAudioResponse> {
  const form = new FormData();
  form.append("file", params.file);
  if (params.languageCode) form.append("language_code", params.languageCode);
  if (params.targetLanguage) form.append("target_language", params.targetLanguage);
  form.append("encounter_id", params.encounterId);

  const res = await fetch(`${API_BASE_URL}/api/v1/audio/upload`, {
    method: "POST",
    credentials: "include",
    body: form,
  });
  return handle<IngestAudioResponse>(res);
}

export async function analyzeLatestJob(jobId: string): Promise<void> {
  const res = await fetch(`${API_BASE_URL}/api/v1/transcriptions/${jobId}/analyze`, {
    method: "POST",
    headers: getHeaders(),
    credentials: "include",
  });
  await handle(res);
}
