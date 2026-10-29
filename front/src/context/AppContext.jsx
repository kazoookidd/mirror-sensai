import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import { auth } from "../api/auth.js";
import { conversations as conversationsApi } from "../api/conversations.js";
import { models as modelsApi, status as statusApi } from "../api/ollama.js";
import { personas as personasApi } from "../api/personas.js";
import { settings as settingsApi } from "../api/settings.js";
import { whenUnauthorized } from "../api/http.js";

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
  const [personas, setPersonas] = useState([]);
  const [persona, setPersona] = useState("");
  const [hrDocuments, setHrDocuments] = useState(true);

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

  const refreshPersonas = useCallback(async () => {
    try {
      const data = await personasApi.list();
      setPersonas(data.personas);
      setPersona(data.current);
    } catch {
      setPersonas([]);
    }
  }, []);

  const choosePersona = useCallback(async (id) => {
    setPersona((await personasApi.select(id)).current);
  }, []);

  const chooseModel = useCallback(async (name) => {
    const data = await modelsApi.select(name);
    setModel(data.current);
    setModelInstalled(true);
  }, []);

  const loadSettings = useCallback(async () => {
    try {
      const data = await settingsApi.get();
      setContext((current) => ({ ...current, budget: data.context_budget }));
      setHrDocuments(data.hr_documents);
    } catch {
      // The gauge stays hidden until the first answer reports it.
    }
  }, []);

  const switchHrDocuments = useCallback(async (on) => {
    await settingsApi.set("documents", on ? "on" : "off");
    setHrDocuments(on);
  }, []);

  const startSession = useCallback(async (account) => {
    setUser(account);
    setModel(account.model);
    loadSettings();
    refreshPersonas();
    if (await refreshStatus()) await refreshModels();
  }, [loadSettings, refreshModels, refreshPersonas, refreshStatus]);

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
    ready, user, ollama, models, model, modelInstalled, context, conversations, personas, persona, hrDocuments,
    setContext, setModel, refreshStatus, refreshModels, refreshConversations, refreshPersonas,
    chooseModel, choosePersona, switchHrDocuments, startSession, logout,
  }), [ready, user, ollama, models, model, modelInstalled, context, conversations, personas, persona, hrDocuments,
    refreshStatus, refreshModels, refreshConversations, refreshPersonas, chooseModel, choosePersona, switchHrDocuments,
    startSession, logout]);

  return <AppContext.Provider value={value}>{children}</AppContext.Provider>;
}

export function useApp() {
  return useContext(AppContext);
}
