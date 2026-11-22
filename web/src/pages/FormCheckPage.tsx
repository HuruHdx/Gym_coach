import { Link } from "react-router-dom";

/** 动作分析：二期功能入口壳，上传/姿态管线尚未开工 */
export function FormCheckPage() {
  return (
    <div className="flex min-h-full flex-col px-4 pb-6 pt-3">
      <div className="flex items-center justify-between gap-2">
        <div>
          <Link to="/training" className="text-[12px] font-bold text-muted">
            ‹ 训练
          </Link>
          <h1 className="mt-1 font-display text-[26px] font-bold tracking-tight">动作分析</h1>
          <p className="mt-1 text-[12px] text-muted">练后上传侧视视频，看次数、节奏与速度衰减</p>
        </div>
        <span className="shrink-0 rounded-md border border-line bg-elevated px-2.5 py-1.5 text-[11px] font-extrabold text-muted">
          即将推出
        </span>
      </div>

      <div className="mt-8 rounded-2xl border border-dashed border-line bg-elevated px-4 py-10 text-center">
        <p className="text-sm font-bold">分析管线还在路上</p>
        <p className="mt-2 text-[12px] leading-relaxed text-muted">
          二期会支持侧视视频上传与速度衰减复盘。
          <br />
          现在可以从训练记录回顾这场组次与重量。
        </p>
        <Link
          to="/training/records"
          className="pressable mt-4 inline-flex rounded-md border border-line bg-bg px-3 py-2 text-[12px] font-bold"
        >
          先看训练记录
        </Link>
      </div>
    </div>
  );
}
