export type EncounterStatus = "CREATED" | "IN_PROGRESS" | "READY_FOR_REVIEW" | "FINALIZED";

export interface ClinicalEncounter {
  id: string;
  created_at: string;
  clinician_id: string | null;
  patient_id: string | null;
  status: EncounterStatus;
  title: string | null;
  transcription_job_ids: string[];
}

export interface EncounterSummary {
  id: string;
  created_at: string;
  clinician_id: string | null;
  patient_id: string | null;
  status: EncounterStatus;
  title: string | null;
}

export interface TranscriptJob {
  id: string;
  created_at: string;
  status: "PENDING" | "PROCESSING" | "COMPLETED" | "FAILED";
  audio_url: string;
  language_code?: string | null;
  target_language?: string | null;
  result_text?: string | null;
  translated_text?: string | null;
}

export interface ClinicalNoteSection {
  text: string;
}

export interface ClinicalNote {
  id: string;
  encounter_id: string;
  created_at: string;
  updated_at: string;
  created_by?: string | null;
  last_edited_by?: string | null;
  is_finalized: boolean;
  subjective: ClinicalNoteSection;
  objective: ClinicalNoteSection;
  assessment: ClinicalNoteSection;
  plan: ClinicalNoteSection;
}

export interface EncounterDetailResponse {
  encounter: ClinicalEncounter;
  jobs: TranscriptJob[];
  note: ClinicalNote | null;
}

export interface IngestAudioResponse {
  job: TranscriptJob;
  encounter_id: string | null;
}
