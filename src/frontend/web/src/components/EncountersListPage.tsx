import { useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { createEncounter, getEncounters } from "../api/client";
import { EncounterSummary } from "../api/types";

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
      try {
        const list = await getEncounters();
        setEncounters(list);
      } catch (e) {
        setError((e as Error).message);
      } finally {
        setLoading(false);
      }
    })();
  }, []);

  const handleCreate = async () => {
    setCreating(true);
    setError(null);
    try {
      const enc = await createEncounter({
        patient_id: patientId || undefined,
        title: title || undefined,
      });
      setEncounters((prev) => [enc, ...prev]);
      setPatientId("");
      setTitle("");
      navigate(`/encounters/${enc.id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setCreating(false);
    }
  };

  return (
    <div className="p-4 max-w-4xl mx-auto space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-xl font-semibold">Encounters</h1>
        <Link to="/settings" className="text-sm text-blue-600 hover:underline">
          API settings
        </Link>
      </div>

      <div className="border rounded p-3 flex gap-2 items-end">
        <div className="flex-1">
          <label className="block text-sm font-medium mb-1">Patient ID / alias</label>
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            value={patientId}
            onChange={(e) => setPatientId(e.target.value)}
          />
        </div>
        <div className="flex-1">
          <label className="block text-sm font-medium mb-1">Title</label>
          <input
            className="w-full border rounded px-2 py-1 text-sm"
            value={title}
            onChange={(e) => setTitle(e.target.value)}
          />
        </div>
        <button
          onClick={handleCreate}
          disabled={creating}
          className="px-3 py-1 text-sm rounded bg-blue-600 text-white"
        >
          {creating ? "Creating..." : "New encounter"}
        </button>
      </div>

      {error && (
        <div className="text-sm text-red-600">{error}</div>
      )}

      {loading ? (
        <div className="text-sm text-gray-600">Loading...</div>
      ) : encounters.length === 0 ? (
        <div className="text-sm text-gray-600">No encounters yet.</div>
      ) : (
        <table className="w-full text-sm border-collapse">
          <thead>
            <tr className="border-b bg-gray-50">
              <th className="text-left py-2 px-2">Patient</th>
              <th className="text-left py-2 px-2">Title</th>
              <th className="text-left py-2 px-2">Status</th>
              <th className="text-left py-2 px-2">Created</th>
            </tr>
          </thead>
          <tbody>
            {encounters.map((e) => (
              <tr
                key={e.id}
                className="border-b hover:bg-gray-50 cursor-pointer"
                onClick={() => navigate(`/encounters/${e.id}`)}
              >
                <td className="py-2 px-2">{e.patient_id ?? "N/A"}</td>
                <td className="py-2 px-2">{e.title ?? "Untitled encounter"}</td>
                <td className="py-2 px-2">
                  <span className="inline-block px-2 py-0.5 rounded text-xs bg-gray-100">
                    {e.status}
                  </span>
                </td>
                <td className="py-2 px-2 text-xs text-gray-600">
                  {new Date(e.created_at).toLocaleString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </div>
  );
}
