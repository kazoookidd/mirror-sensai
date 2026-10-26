import { HashRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import { AppProvider, useApp } from "./context/AppContext.jsx";
import { AccountDialog } from "./features/account/AccountDialog.jsx";
import { LoginPage } from "./features/auth/LoginPage.jsx";
import { ChatPage } from "./features/chat/ChatPage.jsx";
import { DocumentsPage } from "./features/documents/DocumentsPage.jsx";
import { ErrorBoundary } from "./features/errors/ErrorBoundary.jsx";
import { NotFoundPage } from "./features/errors/NotFoundPage.jsx";
import { HistoryPage } from "./features/history/HistoryPage.jsx";
import { ProfilePage } from "./features/profile/ProfilePage.jsx";
import { SettingsPage } from "./features/settings/SettingsPage.jsx";
import { useMediaQuery } from "./lib/useMediaQuery.js";

const WIDE = "(min-width: 1024px)";
const DIALOG_TABS = ["settings", "profile"];

function AppRoutes() {
  const { ready, user } = useApp();
  const location = useLocation();
  const navigate = useNavigate();
  const wide = useMediaQuery(WIDE);
  const tab = location.pathname.slice(1);
  const background = wide && DIALOG_TABS.includes(tab) ? (location.state?.background ?? { pathname: "/chat" }) : null;
  const closeDialog = () => (location.state?.background ? navigate(-1) : navigate("/chat", { replace: true }));
  if (!ready) return null;
  if (!user) {
    return (
      <Routes>
        <Route path="/login" element={<LoginPage />} />
        <Route path="*" element={<Navigate to="/login" replace />} />
      </Routes>
    );
  }
  return (
    <>
      <Routes location={background ?? location}>
        <Route path="/chat/:id?" element={<ChatPage />} />
        <Route path="/documents" element={<DocumentsPage />} />
        <Route path="/history" element={<HistoryPage />} />
        <Route path="/settings" element={<SettingsPage />} />
        <Route path="/profile" element={<ProfilePage />} />
        <Route path="/" element={<Navigate to="/chat" replace />} />
        <Route path="/login" element={<Navigate to="/chat" replace />} />
        <Route path="*" element={<NotFoundPage />} />
      </Routes>
      {background && (
        <AccountDialog tab={tab} onClose={closeDialog}
          onTab={(next) => navigate(`/${next}`, { replace: true, state: location.state })} />
      )}
    </>
  );
}

function GuardedRoutes() {
  const location = useLocation();
  return (
    <ErrorBoundary resetKey={location.pathname}>
      <AppRoutes />
    </ErrorBoundary>
  );
}

export function App() {
  return (
    <HashRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <AppProvider>
        <GuardedRoutes />
      </AppProvider>
    </HashRouter>
  );
}
