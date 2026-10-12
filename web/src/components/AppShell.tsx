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
  const onMeSettings = pathname.startsWith("/me/settings");
  const onExercise = pathname.startsWith("/training/exercise");

  return (
    <div className="noise mx-auto flex h-dvh max-w-md flex-col bg-bg">
      <main className="relative z-10 min-h-0 flex-1 overflow-y-auto overscroll-contain">
        <Outlet />
      </main>

      {/* 非教练页：左侧悬浮入口（右侧留给重量 +/-，避免挡操作） */}
      {!onCoach && !onRecap && !onMeSettings && !onExercise && (
        <NavLink
          to="/coach"
          className="pressable fixed bottom-[calc(72px+env(safe-area-inset-bottom))] left-4 z-20 grid h-11 w-11 place-items-center rounded-full bg-ink font-display text-[11px] font-extrabold leading-tight text-accent shadow-[0_8px_24px_rgba(18,20,15,0.28)]"
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
                  "pressable relative px-1 py-3.5 text-center text-[13px] transition-colors duration-150",
                  isActive ? "font-bold text-ink" : "font-medium text-muted",
                ].join(" ")
              }
            >
              {({ isActive }) => (
                <>
                  {t.label}
                  <span
                    className={[
                      "absolute bottom-0 left-1/2 h-[2px] -translate-x-1/2 rounded-full bg-ink transition-all duration-200",
                      isActive ? "w-6 opacity-100" : "w-0 opacity-0",
                    ].join(" ")}
                  />
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
