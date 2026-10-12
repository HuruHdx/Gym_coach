import { useEffect, useRef } from "react";
import * as echarts from "echarts/core";
import { LineChart } from "echarts/charts";
import { GridComponent, TooltipComponent } from "echarts/components";
import { CanvasRenderer } from "echarts/renderers";

echarts.use([LineChart, GridComponent, TooltipComponent, CanvasRenderer]);

export type TrendPoint = {
  date: string;
  weight: number;
  reps: number | null;
};

function cssVar(name: string, fallback: string) {
  const v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  return v || fallback;
}

/** 重量走势：纵轴公斤、横轴日期、面积填充。 */
export function WeightTrendChart({ points }: { points: TrendPoint[] }) {
  const host = useRef<HTMLDivElement>(null);
  const chart = useRef<echarts.ECharts | null>(null);

  useEffect(() => {
    const el = host.current;
    if (!el) return;
    const inst = echarts.init(el);
    chart.current = inst;
    const ro = new ResizeObserver(() => inst.resize());
    ro.observe(el);
    return () => {
      ro.disconnect();
      inst.dispose();
      chart.current = null;
    };
  }, []);

  useEffect(() => {
    const inst = chart.current;
    if (!inst || points.length === 0) return;

    const ink = cssVar("--ink", "#12140f");
    const muted = cssVar("--ink-muted", "#6b7164");
    const line = cssVar("--line", "#d8dbd0");
    const accent = cssVar("--accent", "#c8f000");
    const bg = cssVar("--bg-elevated", "#ffffff");

    const labels = points.map((p) => p.date.slice(5));
    const values = points.map((p) => p.weight);

    inst.setOption({
      animationDuration: 480,
      grid: { left: 8, right: 12, top: 28, bottom: 8, containLabel: true },
      tooltip: {
        trigger: "axis",
        backgroundColor: ink,
        borderWidth: 0,
        textStyle: { color: bg, fontSize: 12 },
        formatter: (raw: unknown) => {
          const item = Array.isArray(raw) ? raw[0] : raw;
          const idx = (item as { dataIndex?: number }).dataIndex ?? 0;
          const p = points[idx];
          if (!p) return "";
          const reps = p.reps != null ? ` × ${p.reps}` : "";
          return `${p.date}<br/><b>${p.weight} kg${reps}</b>`;
        },
      },
      xAxis: {
        type: "category",
        data: labels,
        boundaryGap: false,
        axisLine: { lineStyle: { color: line } },
        axisTick: { show: false },
        axisLabel: { color: muted, fontSize: 11, margin: 12 },
      },
      yAxis: {
        type: "value",
        scale: true,
        splitNumber: 3,
        axisLabel: {
          color: muted,
          fontSize: 11,
          formatter: (v: number) => (Number.isInteger(v) ? String(v) : v.toFixed(1)),
        },
        splitLine: { lineStyle: { color: line, type: "dashed" } },
      },
      series: [
        {
          type: "line",
          data: values,
          smooth: 0.25,
          symbol: "circle",
          symbolSize: 9,
          showSymbol: true,
          lineStyle: { width: 2.5, color: ink },
          itemStyle: {
            color: accent,
            borderColor: ink,
            borderWidth: 2,
          },
          areaStyle: {
            color: new echarts.graphic.LinearGradient(0, 0, 0, 1, [
              { offset: 0, color: hexAlpha(accent, 0.45) },
              { offset: 1, color: hexAlpha(accent, 0.02) },
            ]),
          },
          label: {
            show: points.length <= 6,
            position: "top",
            color: ink,
            fontSize: 11,
            fontWeight: 700,
            formatter: (p: { value?: number }) => `${p.value ?? ""}`,
          },
        },
      ],
    });
  }, [points]);

  if (points.length === 0) return null;
  return <div ref={host} className="h-[220px] w-full" />;
}

function hexAlpha(color: string, alpha: number) {
  const hex = color.replace("#", "");
  if (hex.length !== 6) return `rgba(200,240,0,${alpha})`;
  const r = parseInt(hex.slice(0, 2), 16);
  const g = parseInt(hex.slice(2, 4), 16);
  const b = parseInt(hex.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${alpha})`;
}
