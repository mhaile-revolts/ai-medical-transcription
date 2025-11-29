import { useEffect, useState } from "react";
import { loadApiKeyFromStorage, setApiKey } from "../api/client";

export function SettingsPage() {
  const [key, setKey] = useState("");

  useEffect(() => {
    loadApiKeyFromStorage();
    const stored = localStorage.getItem("apiKey");
    if (stored) setKey(stored);
  }, []);

  const handleSave = () => {
    setApiKey(key.trim());
  };

  return (
    <div className="p-4 max-w-md">
      <h1 className="text-xl font-semibold mb-4">API Settings</h1>
      <label className="block mb-2 text-sm font-medium">
        API key
        <input
          type="password"
          className="mt-1 block w-full border rounded px-2 py-1"
          value={key}
          onChange={(e) => setKey(e.target.value)}
        />
      </label>
      <button
        onClick={handleSave}
        className="mt-2 px-3 py-1 rounded bg-blue-600 text-white text-sm"
      >
        Save
      </button>
    </div>
  );
}
