import { Route, Routes } from "react-router-dom";

import { RequireAuth } from "./auth/AuthContext";
import { Layout } from "./components/Layout";
import { Card } from "./components/Card";
import { LoginPage } from "./pages/LoginPage";
import { DashboardPage } from "./pages/DashboardPage";
import { TierlistPage } from "./pages/TierlistPage";
import { SearchPage } from "./pages/SearchPage";
import { CompetitorsPage } from "./pages/CompetitorsPage";
import { ControlPage } from "./pages/ControlPage";
import { SettingsPage } from "./pages/SettingsPage";

function NotFound() {
  return (
    <div className="mx-auto max-w-3xl space-y-4">
      <h2 className="text-xl font-semibold text-fg">Not found</h2>
      <Card title="Not found">
        <p className="text-sm text-muted">This page does not exist.</p>
      </Card>
    </div>
  );
}

export default function App() {
  return (
    <Routes>
      <Route path="/login" element={<LoginPage />} />

      <Route
        element={
          <RequireAuth>
            <Layout />
          </RequireAuth>
        }
      >
        <Route index element={<DashboardPage />} />
        <Route path="tierlist" element={<TierlistPage />} />
        <Route path="search" element={<SearchPage />} />
        <Route path="competitors" element={<CompetitorsPage />} />
        <Route path="control" element={<ControlPage />} />
        <Route path="settings" element={<SettingsPage />} />
      </Route>

      <Route path="*" element={<NotFound />} />
    </Routes>
  );
}
