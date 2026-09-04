import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createEncounter, getEncounters } from "../api/client";
import { EncounterSummary } from "../api/types";

function StatusBadge({ status }: { status: string }) {
  return <span className={`status-badge ${status.toLowerCase()}`}>{status.replaceAll("_", " ")}</span>;
}

export function EncountersListPage() {
  const [encounters, setEncounters] = useState<EncounterSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [creating, setCreating] = useState(false);
  const [patientId, setPatientId] = useState("");
  const [title, setTitle] = useState("");
  const [error, setError] = useState<string | null>(null);
  const navigate = useNavigate();

  useEffect(() => {
    (async () => {
      setLoading(true);
      setError(null);
      try { setEncounters(await getEncounters()); }
      catch (e) { setError((e as Error).message); }
      finally { setLoading(false); }
    })();
  }, []);

  const handleCreate = async () => {
    setCreating(true); setError(null);
    try {
      const enc = await createEncounter({ patient_id: patientId || undefined, title: title || undefined });
      setEncounters((prev) => [enc, ...prev]);
      setPatientId(""); setTitle(""); navigate(`/encounters/${enc.id}`);
    } catch (e) { setError((e as Error).message); }
    finally { setCreating(false); }
  };

  return (
    <div className="app-frame">
      <header className="topbar">
        <Link to="/encounters" className="wordmark">
          <span className="wordmark-mark">CS</span>
          <span>Clinic Scribe<small>Clinical workspace</small></span>
        </Link>
        <div className="topbar-actions"><Link to="/settings" className="topbar-link">Account settings</Link><Link to="/settings" className="account-pill">Your account</Link></div>
      </header>
      <main className="workspace">
        <div className="page-heading">
          <div><div className="eyebrow">Documentation desk / 01</div><h1>Encounters</h1><p>Review, refine, and deliver today’s clinical record.</p></div>
        </div>
        <section className="create-panel">
          <div className="create-panel-header"><div><h2>Start a new encounter</h2><p>Create a workspace for audio, transcript, and SOAP documentation.</p></div><span className="eyebrow" style={{ color: "#a7d2c9" }}>New record</span></div>
          <div className="create-grid">
            <div className="field"><label htmlFor="patient-id">Patient ID / alias</label><input id="patient-id" className="input" placeholder="e.g. PT-2048" value={patientId} onChange={(e) => setPatientId(e.target.value)} /></div>
            <div className="field"><label htmlFor="encounter-title">Encounter title</label><input id="encounter-title" className="input" placeholder="e.g. Annual review" value={title} onChange={(e) => setTitle(e.target.value)} /></div>
            <button onClick={handleCreate} disabled={creating} className="button button-primary">{creating ? "Creating…" : "New encounter"}</button>
          </div>
        </section>
        {error && <div className="alert alert-error" role="alert">{error}</div>}
        <section className="table-card" aria-label="Encounter list">
          <div className="table-toolbar"><strong>Recent encounters</strong><span>{loading ? "SYNCING" : `${encounters.length} RECORD${encounters.length === 1 ? "" : "S"}`}</span></div>
          {loading ? <div aria-label="Loading encounters"><div className="skeleton" /><div className="skeleton" /><div className="skeleton" /></div> :
            encounters.length === 0 ? <div className="empty-state"><strong>Your desk is clear.</strong><span>Create an encounter above to begin documentation.</span></div> :
            <table className="encounter-table"><thead><tr><th>Patient</th><th>Encounter</th><th>Status</th><th>Created</th></tr></thead><tbody>
              {encounters.map((encounter) => <tr className="encounter-row" key={encounter.id} onClick={() => navigate(`/encounters/${encounter.id}`)} tabIndex={0} onKeyDown={(e) => { if (e.key === "Enter") navigate(`/encounters/${encounter.id}`); }}>
                <td><span className="patient-id">{encounter.patient_id ?? "NO ID"}</span></td>
                <td><span className="encounter-title">{encounter.title ?? "Untitled encounter"}</span></td>
                <td><StatusBadge status={encounter.status} /></td>
                <td><span className="date-text">{new Date(encounter.created_at).toLocaleString([], { dateStyle: "medium", timeStyle: "short" })}</span></td>
              </tr>)}
            </tbody></table>}
        </section>
      </main>
    </div>
  );
}