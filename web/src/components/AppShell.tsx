import { NavLink, Outlet, useLocation } from "react-router-dom";

const tabs = [
  { to: "/", label: "今日", end: true },
  { to: "/coach", label: "教练", end: false },
  { to: "/training", label: "训练", end: false },
  { to: "/me", label: "我的", end: false },
];

export function AppShell() {
  const { pathname } = useLocation();
  const onCoach = pathname.startsWith("/coach");
  const onRecap = pathname.startsWith("/recap");
  const onProfileEdit = pathname.startsWith("/me/edit") || pathname.startsWith("/me/settings");
  const onExercise = pathname.startsWith("/training/exercise");

  return (
    <div className="noise mx-auto flex h-dvh max-w-md flex-col bg-bg">
      <main
        className={[
          "relative z-10 min-h-0 flex-1 overscroll-contain",
          // 教练页自己管滚动，避免套两层滑不动
          onCoach ? "overflow-hidden" : "overflow-y-auto",
        ].join(" ")}
      >
        <Outlet />
      </main>

      {!onCoach && !onRecap && !onProfileEdit && !onExercise && (
        <NavLink
          to="/coach"
          className="pressable fixed bottom-[calc(72px+env(safe-area-inset-bottom))] left-4 z-20 grid h-11 w-11 place-items-center rounded-full bg-ink font-display text-micro font-semibold leading-tight text-accent-ink shadow-float"
          aria-label="打开 AI 教练"
        >
          AI
        </NavLink>
      )}

      {!onRecap && !onExercise && (
        <footer className="relative z-20 shrink-0 border-t border-line bg-bg/95 pb-[max(8px,env(safe-area-inset-bottom))] pt-1 backdrop-blur-sm">
          <nav className="grid grid-cols-4 bg-elevated">
            {tabs.map((t) => (
              <NavLink
                key={t.to}
                to={t.to}
                end={t.end}
                className={({ isActive }) =>
                  [
                    "pressable relative px-1 py-3.5 text-center text-meta transition-colors duration-state",
                    isActive ? "font-semibold text-ink" : "font-medium text-muted",
                  ].join(" ")
                }
              >
                {({ isActive }) => (
                  <>
                    {t.label}
                    <span className={`tab-indicator ${isActive ? "on" : ""}`} aria-hidden />
                  </>
                )}
              </NavLink>
            ))}
          </nav>
        </footer>
      )}
    </div>
  );
}
