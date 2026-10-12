import { useState } from "react";
import { Navigate, Route, Routes } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { api, clearAuth, isAuthed } from "./lib/api";
import type { Profile } from "./types";
import { AppShell } from "./components/AppShell";
import { LoginPage } from "./pages/LoginPage";
import { Onboarding } from "./pages/Onboarding";
import { TodayPage } from "./pages/TodayPage";
import { CoachPage } from "./pages/CoachPage";
import { TrainingPage } from "./pages/TrainingPage";
import { ExerciseTrendPage } from "./pages/ExerciseTrendPage";
import { MePage } from "./pages/MePage";
import { ProfileSettingsPage } from "./pages/ProfileSettingsPage";
import { RecapPage } from "./pages/RecapPage";
import { DebugPage } from "./pages/DebugPage";

export default function App() {
  const [authed, setAuthed] = useState(() => isAuthed());

  const { data, isLoading, isError, refetch, error } = useQuery({
    queryKey: ["profile", authed],
    queryFn: () => api<Profile | null>("/api/profile"),
    enabled: authed,
    retry: false,
  });

  if (!authed) {
    return (
      <LoginPage
        onDone={() => {
          setAuthed(true);
        }}
      />
    );
  }

  if (isLoading) {
    return (
      <div className="noise flex h-dvh items-center justify-center bg-bg text-muted">加载中…</div>
    );
  }

  if (isError) {
    const msg = String(error);
    const authFail = msg.startsWith("401") || msg.startsWith("403");
    return (
      <div className="noise flex h-dvh flex-col items-center justify-center gap-3 bg-bg px-6 text-center">
        <p className="font-display text-xl text-ink">
          {authFail ? "登录已失效" : "后端还没连上"}
        </p>
        <p className="text-sm text-muted">
          {authFail ? "请重新输入访问口令。" : "先确认 api 的 uvicorn 在跑，再点重试。"}
        </p>
        <div className="flex gap-2">
          {authFail && (
            <button
              className="rounded-md border border-line px-4 py-2 text-sm font-bold"
              onClick={() => {
                clearAuth();
                setAuthed(false);
              }}
            >
              重新登录
            </button>
          )}
          <button
            className="rounded-md bg-accent px-4 py-2 font-display font-bold text-accent-ink"
            onClick={() => refetch()}
          >
            重试
          </button>
        </div>
      </div>
    );
  }

  if (!data) {
    return <Onboarding onDone={() => refetch()} />;
  }

  return (
    <Routes>
      <Route element={<AppShell />}>
        <Route path="/" element={<TodayPage />} />
        <Route path="/coach" element={<CoachPage profile={data} />} />
        <Route path="/training" element={<TrainingPage />} />
        <Route path="/training/exercise/:name" element={<ExerciseTrendPage />} />
        <Route path="/recap" element={<RecapPage />} />
        <Route
          path="/me"
          element={
            <MePage
              profile={data}
              onUpdated={() => refetch()}
              onLogout={() => {
                clearAuth();
                setAuthed(false);
              }}
            />
          }
        />
        <Route
          path="/me/settings"
          element={
            <ProfileSettingsPage
              profile={data}
              onUpdated={() => refetch()}
              onResetOnboarding={() => refetch()}
            />
          }
        />
        <Route path="/debug" element={<DebugPage />} />
      </Route>
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}
