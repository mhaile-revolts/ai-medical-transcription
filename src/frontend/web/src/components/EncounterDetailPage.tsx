import { useEffect, useMemo, useRef, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { getEncounterDetail, updateEncounterNote, uploadAudio, analyzeLatestJob } from "../api/client";
import { ClinicalNote, EncounterDetailResponse, TranscriptJob } from "../api/types";

const noteSections = ["subjective", "objective", "assessment", "plan"] as const;
type NoteDraft = Record<typeof noteSections[number], string>;

function StatusBadge({ status }: { status: string }) { return <span className={`status-badge ${status.toLowerCase()}`}>{status.replaceAll("_", " ")}</span>; }

export function EncounterDetailPage() {
  const { id } = useParams<{ id: string }>();
  const [data, setData] = useState<EncounterDetailResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [analyzing, setAnalyzing] = useState(false);
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const pollingRef = useRef<number | null>(null);
  const [noteDraft, setNoteDraft] = useState<NoteDraft>({ subjective: "", objective: "", assessment: "", plan: "" });
  const encounter = data?.encounter ?? null;
  const note: ClinicalNote | null = data?.note ?? null;
  const latestCompletedJob: TranscriptJob | null = useMemo(() => {
    const completed = (data?.jobs ?? []).filter((j) => j.status === "COMPLETED");
    return completed.sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime())[0] ?? null;
  }, [data]);
  const hasInFlightJobs = useMemo(() => (data?.jobs ?? []).some((j) => j.status === "PENDING" || j.status === "PROCESSING"), [data]);

  useEffect(() => {
    if (!id) return;
    (async () => { setLoading(true); setError(null); try { const detail = await getEncounterDetail(id); setData(detail); if (detail.note) setNoteDraft({ subjective: detail.note.subjective.text, objective: detail.note.objective.text, assessment: detail.note.assessment.text, plan: detail.note.plan.text }); } catch (e) { setError((e as Error).message); } finally { setLoading(false); } })();
  }, [id]);
  useEffect(() => {
    if (!id || !hasInFlightJobs) { if (pollingRef.current) clearTimeout(pollingRef.current); return; }
    pollingRef.current = window.setTimeout(async () => { try { setData(await getEncounterDetail(id)); } catch (e) { console.error(e); } }, 5000);
    return () => { if (pollingRef.current) clearTimeout(pollingRef.current); };
  }, [id, hasInFlightJobs]);
  const refresh = async () => { if (!id) return; setLoading(true); setError(null); try { setData(await getEncounterDetail(id)); } catch (e) { setError((e as Error).message); } finally { setLoading(false); } };
  const handleUpload = async () => { if (!id || !file) return; setUploading(true); setError(null); try { await uploadAudio({ encounterId: id, file }); setFile(null); await refresh(); } catch (e) { setError((e as Error).message); } finally { setUploading(false); } };
  const handleAnalyze = async () => { if (!id || !latestCompletedJob) return; setAnalyzing(true); setError(null); try { await analyzeLatestJob(latestCompletedJob.id); await refresh(); } catch (e) { setError((e as Error).message); } finally { setAnalyzing(false); } };
  const handleSaveNote = async (finalize: boolean) => {
    if (!id) return; setError(null); setValidationError(null);
    if (finalize) { const missing = noteSections.filter((section) => !noteDraft[section].trim()); if (missing.length) { setValidationError(`Cannot finalize: please fill in ${missing.join(", ")}.`); return; } }
    setSaving(true); try { const updated = await updateEncounterNote(id, { ...noteDraft, finalize }); setData((prev) => prev ? { ...prev, note: updated } : prev); } catch (e) { setError((e as Error).message); } finally { setSaving(false); }
  };
  if (loading && !data) return <><header className="topbar"><span className="wordmark"><span className="wordmark-mark">CS</span>Clinic Scribe</span></header><main className="loading-page"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></main></>;
  if (!encounter || !id) return <main className="error-page"><div className="alert alert-error">Encounter not found. <Link to="/encounters">Return to encounters</Link></div></main>;
  const finalized = note?.is_finalized ?? false;
  const formattedNoteText = noteSections.map((section) => `${section[0].toUpperCase()}${section.slice(1)}:\n${noteDraft[section]}`).join("\n\n");
  const printNote = () => { const w = window.open("", "_blank", "noopener,noreferrer"); if (!w) return; w.document.write(`<pre style="font-family: sans-serif; white-space: pre-wrap; padding: 32px;">${formattedNoteText.replace(/</g, "&lt;")}</pre>`); w.document.close(); };
  return <div className="app-frame">
    <header className="topbar"><Link to="/encounters" className="wordmark"><span className="wordmark-mark">CS</span><span>Clinic Scribe<small>Clinical workspace</small></span></Link><div className="topbar-actions"><Link to="/encounters" className="topbar-link">All encounters</Link><Link to="/settings" className="account-pill">Your account</Link></div></header>
    <main className="workspace"><div className="eyebrow">Documentation desk / encounter</div>
      {error && <div className="alert alert-error" role="alert">{error}</div>}{validationError && <div className="alert alert-warn" role="alert">{validationError}</div>}
      <div className="detail-layout">
        <aside className="detail-sidebar"><div className="detail-heading"><div><div className="eyebrow">Patient record</div><h1>{encounter.title ?? "Encounter"}</h1><p className="detail-meta">{encounter.patient_id ?? "No patient ID"} · <StatusBadge status={encounter.status} /></p></div><button className="button button-quiet" onClick={refresh} disabled={loading}>{loading ? "…" : "Refresh"}</button></div>
          <div className="section-block"><h2>Audio capture <span>/ source</span></h2><div className="file-picker"><input type="file" accept="audio/*" onChange={(e) => setFile(e.target.files?.[0] ?? null)} /><button className="button button-primary" onClick={handleUpload} disabled={!file || uploading}>{uploading ? "Uploading…" : "Upload audio"}</button></div></div>
          <div className="section-block"><h2>Transcript <span>/ latest completed</span></h2>{latestCompletedJob ? <><p className="job-meta">JOB {latestCompletedJob.id.slice(0, 8)} · {latestCompletedJob.status}</p><pre className="transcript">{latestCompletedJob.result_text ?? "(no transcript text)"}</pre><button className="button button-light" onClick={handleAnalyze} disabled={analyzing}>{analyzing ? "Analyzing…" : "Analyze & update note"}</button></> : <p className="detail-meta">{hasInFlightJobs ? "Transcript processing in the background…" : "No completed transcript yet."}</p>}</div>
        </aside>
        <section className="note-card"><div className="note-header"><div><div className="eyebrow">Clinical note / SOAP</div><h2>Review and complete</h2></div>{finalized && <StatusBadge status="FINALIZED" />}</div>
          {noteSections.map((section, index) => <div className="note-section" key={section}><label htmlFor={`soap-${section}`}>{section}<span>0{index + 1}</span></label><textarea id={`soap-${section}`} className="textarea soap-textarea" value={noteDraft[section]} onChange={(e) => setNoteDraft((prev) => ({ ...prev, [section]: e.target.value }))} disabled={finalized} placeholder={`Document the ${section} findings…`} /> </div>)}
          <div className="note-footer"><span className="autosave-note">{saving ? "SAVING CHANGES…" : finalized ? "FINALIZED · READ ONLY" : "DRAFT · NOT YET DELIVERED"}</span><div className="note-actions"><button className="button button-quiet" onClick={() => navigator.clipboard.writeText(formattedNoteText)}>Copy note</button><button className="button button-quiet" onClick={printNote}>Print view</button><button className="button button-light" onClick={() => handleSaveNote(false)} disabled={saving || finalized}>{saving ? "Saving…" : "Save draft"}</button><button className="button button-danger" onClick={() => handleSaveNote(true)} disabled={saving || finalized}>Finalize note</button></div></div>
        </section>
      </div>
    </main>
  </div>;
}