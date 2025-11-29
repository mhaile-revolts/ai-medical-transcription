import { BrowserRouter, Routes, Route, Navigate } from "react-router-dom";
import { SettingsPage } from "./components/SettingsPage";
import { EncountersListPage } from "./components/EncountersListPage";
import { EncounterDetailPage } from "./components/EncounterDetailPage";
import { loadApiKeyFromStorage } from "./api/client";

loadApiKeyFromStorage();

export function App() {
  return (
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<Navigate to="/encounters" replace />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/encounters" element={<EncountersListPage />} />
        <Route path="/encounters/:id" element={<EncounterDetailPage />} />
      </Routes>
    </BrowserRouter>
  );
}
