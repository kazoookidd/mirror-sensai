import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { auth } from "../features/auth/api.js";
import { conversations as conversationsApi } from "../features/history/api.js";
import { models as modelsApi, status as statusApi } from "../features/ollama/api.js";
import { settings as settingsApi } from "../features/settings/api.js";
import { whenUnauthorized } from "../lib/http.js";

const STATUS_INTERVAL_MS = 15000;

const AppContext = createContext(null);

export function AppProvider({ children }) {
  const [ready, setReady] = useState(false);
  const [user, setUser] = useState(null);
  const [ollama, setOllama] = useState({ online: true, url: "" });
  const [models, setModels] = useState([]);
  const [model, setModel] = useState("");
  const [modelInstalled, setModelInstalled] = useState(true);
  const [context, setContext] = useState({ tokens: 0, budget: 0 });
  const [conversations, setConversations] = useState([]);

  const refreshStatus = useCallback(async () => {
    try {
      const data = await statusApi.get();
      setOllama({ online: data.ollama, url: data.url });
      return data.ollama;
    } catch {
      setOllama((current) => ({ ...current, online: false }));
      return false;
    }
  }, []);

  const refreshModels = useCallback(async () => {
    try {
      const data = await modelsApi.list();
      setModels(data.models);
      setModel(data.current);
      setModelInstalled(data.installed);
    } catch {
      setModels([]);
    }
  }, []);

  const refreshConversations = useCallback(async () => {
    try {
      setConversations((await conversationsApi.list()).conversations);
    } catch {
      // The sidebar keeps the list it had.
    }
  }, []);

  const chooseModel = useCallback(async (name) => {
    const data = await modelsApi.select(name);
    setModel(data.current);
    setModelInstalled(true);
  }, []);

  const loadBudget = useCallback(async () => {
    try {
      const data = await settingsApi.get();
      setContext((current) => ({ ...current, budget: data.context_budget }));
    } catch {
      // The gauge stays hidden until the first answer reports it.
    }
  }, []);

  const startSession = useCallback(async (account) => {
    setUser(account);
    setModel(account.model);
    loadBudget();
    if (await refreshStatus()) await refreshModels();
  }, [loadBudget, refreshModels, refreshStatus]);

  const logout = useCallback(async () => {
    try {
      await auth.logout();
    } finally {
      setUser(null);
    }
  }, []);

  useEffect(() => {
    whenUnauthorized(() => setUser(null));
    (async () => {
      try {
        const me = await auth.me();
        if (me.user_id) await startSession(me);
        else await refreshStatus();
      } catch {
        await refreshStatus();
      }
      setReady(true);
    })();
  }, [refreshStatus, startSession]);

  useEffect(() => {
    const timer = setInterval(() => {
      if (document.visibilityState === "visible") refreshStatus();
    }, STATUS_INTERVAL_MS);
    return () => clearInterval(timer);
  }, [refreshStatus]);

  const value = useMemo(() => ({
    ready, user, ollama, models, model, modelInstalled, context, conversations,
    setContext, setModel, refreshStatus, refreshModels, refreshConversations, chooseModel, startSession, logout,
  }), [ready, user, ollama, models, model, modelInstalled, context, conversations,
    refreshStatus, refreshModels, refreshConversations, chooseModel, startSession, logout]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext);
}
