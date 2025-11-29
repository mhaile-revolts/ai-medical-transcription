import { useEffect, useMemo, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import {
  getEncounterDetail,
  updateEncounterNote,
  uploadAudio,
  analyzeLatestJob,
} from "../api/client";
import { ClinicalNote, EncounterDetailResponse, TranscriptJob } from "../api/types";

export function EncounterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<EncounterDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);

  const [noteDraft, setNoteDraft] = useState<{
    subjective: string;
    objective: string;
    assessment: string;
    plan: string;
  }>({ subjective: "", objective: "", assessment: "", plan: "" });

  const encounter = data?.encounter ?? null;
  const note: ClinicalNote | null = data?.note ?? null;

  const latestCompletedJob: TranscriptJob | null = useMemo(() => {
    if (!data) return null;
    const completed = data.jobs.filter((j) => j.status === "COMPLETED");
    if (!completed.length) return null;
    return completed.sort(
      (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
    )[0];
  }, [data]);

  const hasInFlightJobs = useMemo(() => {
    if (!data) return false;
    return data.jobs.some((j) => j.status === "PENDING" || j.status === "PROCESSING");
  }, [data]);

  // Initial load
  useEffect(() => {
    if (!id) return;
    (async () => {
      setLoading(true);
      setError(null);
      try {
        const detail = await getEncounterDetail(id);
        setData(detail);
        const n = detail.note;
        if (n) {
          setNoteDraft({
            subjective: n.subjective.text,
            objective: n.objective.text,
            assessment: n.assessment.text,
            plan: n.plan.text,
          });
        }
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, [id]);

  // Polling for in-flight jobs
  useEffect(() => {
    if (!id) return;
    if (!hasInFlightJobs) {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    pollingRef.current = window.setTimeout(async () => {
      try {
        const detail = await getEncounterDetail(id);
        setData(detail);
      } catch (e) {
        console.error(e);
      }
    }, 5000);

    return () => {
      if (pollingRef.current) {
        clearTimeout(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [id, hasInFlightJobs]);

  const handleUpload = async () => {
    if (!id || !file) return;
    setError(null);
    try {
      await uploadAudio({ encounterId: id, file });
      const detail = await getEncounterDetail(id);
      setData(detail);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleAnalyze = async () => {
    if (!id || !latestCompletedJob) return;
    setError(null);
    try {
      await analyzeLatestJob(latestCompletedJob.id);
      const detail = await getEncounterDetail(id);
      setData(detail);
    } catch (e) {
      setError((e as Error).message);
    }
  };

  const handleSaveNote = async (finalize: boolean) => {
    if (!id) return;

    setError(null);
    setValidationError(null);

    if (finalize) {
      const missing: string[] = [];
      if (!noteDraft.subjective.trim()) missing.push("Subjective");
      if (!noteDraft.objective.trim()) missing.push("Objective");
      if (!noteDraft.assessment.trim()) missing.push("Assessment");
      if (!noteDraft.plan.trim()) missing.push("Plan");

      if (missing.length) {
        setValidationError(`Cannot finalize: please fill in ${missing.join(", ")}.`);
        return;
      }
    }

    setSaving(true);
    try {
      const updated = await updateEncounterNote(id, { ...noteDraft, finalize });
      setData((prev) => (prev ? { ...prev, note: updated } : prev));
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setSaving(false);
    }
  };

  if (loading || !id) {
    return <div className="p-4">Loading...</div>;
  }

  if (!encounter) {
    return <div className="p-4 text-red-600">Encounter not found.</div>;
  }

  const finalized = note?.is_finalized ?? false;

  const formattedNoteText = [
    `Subjective:\n${noteDraft.subjective}`,
    `Objective:\n${noteDraft.objective}`,
    `Assessment:\n${noteDraft.assessment}`,
    `Plan:\n${noteDraft.plan}`,
  ].join("\n\n");

  return (
    <div className="p-4 flex gap-6">
      <div className="w-1/3 space-y-4">
        <div className="flex items-center justify-between mb-2">
          <div>
            <h1 className="text-xl font-semibold mb-1">
              {encounter.title ?? "Encounter"}
            </h1>
            <p className="text-sm text-gray-600">
              Patient: {encounter.patient_id ?? "N/A"} • Status: {encounter.status}
            </p>
          </div>
          <button
            onClick={async () => {
              if (!id) return;
              setError(null);
              setLoading(true);
              try {
                const detail = await getEncounterDetail(id);
                setData(detail);
              } catch (e) {
                setError((e as Error).message);
              } finally {
                setLoading(false);
              }
            }}
            className="px-3 py-1 text-sm rounded border border-gray-300 bg-white hover:bg-gray-50"
          >
            Refresh
          </button>
        </div>

        {error && (
          <div className="mb-2 px-3 py-2 rounded border border-red-200 bg-red-50 text-sm text-red-700">
            {error}
          </div>
        )}

        {validationError && (
          <div className="mb-2 px-3 py-2 rounded border border-yellow-200 bg-yellow-50 text-sm text-yellow-800">
            {validationError}
          </div>
        )}

        <div>
          <h2 className="font-medium mb-2">Audio upload</h2>
          <input
            type="file"
            accept="audio/*"
            onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          />
          <button
            onClick={handleUpload}
            className="mt-2 px-3 py-1 text-sm rounded bg-blue-600 text-white"
            disabled={!file}
          >
            Upload
          </button>
        </div>

        <div>
          <h2 className="font-medium mb-2">Transcripts</h2>
          {latestCompletedJob ? (
            <>
              <p className="text-xs text-gray-500 mb-1">
                Latest job: {latestCompletedJob.id.slice(0, 8)} • status: {latestCompletedJob.status}
              </p>
              <pre className="text-xs border rounded p-2 max-h-64 overflow-auto bg-gray-50">
                {latestCompletedJob.result_text ?? "(no transcript text)"}
              </pre>
              <button
                onClick={handleAnalyze}
                className="mt-2 px-3 py-1 text-sm rounded bg-green-600 text-white"
              >
                Analyze &amp; update note
              </button>
            </>
          ) : (
            <p className="text-sm text-gray-600">No completed transcripts yet.</p>
          )}
        </div>
      </div>

      <div className="flex-1 space-y-3">
        <div className="flex items-center gap-2">
          <h2 className="font-medium text-lg">SOAP Note</h2>
          {finalized && (
            <span className="px-2 py-0.5 text-xs rounded bg-green-100 text-green-700">
              Finalized
            </span>
          )}
        </div>

        {["subjective", "objective", "assessment", "plan"].map((section) => (
          <div key={section}>
            <label className="block text-sm font-medium mb-1 capitalize">
              {section}
            </label>
            <textarea
              className="w-full border rounded px-2 py-1 text-sm min-h-[80px]"
              value={noteDraft[section as keyof typeof noteDraft]}
              onChange={(e) =>
                setNoteDraft((prev) => ({ ...prev, [section]: e.target.value }))
              }
              disabled={finalized}
            />
          </div>
        ))}

        <div className="flex gap-2 mt-2">
          <button
            onClick={() => handleSaveNote(false)}
            disabled={saving || finalized}
            className="px-3 py-1 text-sm rounded bg-gray-700 text-white"
          >
            Save draft
          </button>
          <button
            onClick={() => handleSaveNote(true)}
            disabled={saving || finalized}
            className="px-3 py-1 text-sm rounded bg-red-600 text-white"
          >
            Finalize
          </button>
          <button
            type="button"
            onClick={() => {
              navigator.clipboard.writeText(formattedNoteText).catch(() => {});
            }}
            className="px-3 py-1 text-sm rounded border border-gray-300 bg-white"
          >
            Copy note
          </button>
          <button
            type="button"
            onClick={() => {
              const w = window.open("", "_blank", "noopener,noreferrer");
              if (!w) return;
              w.document.write(
                `<pre style="font-family: system-ui, -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif; white-space: pre-wrap;">${formattedNoteText.replace(
                  /</g,
                  "&lt;"
                )}</pre>`
              );
              w.document.close();
            }}
            className="px-3 py-1 text-sm rounded border border-gray-300 bg-white"
          >
            Print view
          </button>
        </div>
      </div>
    </div>
  );
}
