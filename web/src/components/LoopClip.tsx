import { useEffect, useRef, useState } from "react";

type Props = {
  src: string;
  poster?: string | null;
  alt?: string;
  className?: string;
  /** 列表场景：进入视口再播，离开暂停 */
  lazy?: boolean;
};

function isLoopVideo(url: string) {
  return /\.(mp4|webm)(\?|$)/i.test(url);
}

/**
 * 动作示范：静音循环小 MP4；存量 jpg/png/gif/webp 自动回退 img。
 */
export function LoopClip({ src, poster, alt = "", className = "", lazy = false }: Props) {
  const videoRef = useRef<HTMLVideoElement>(null);
  const [inView, setInView] = useState(!lazy);

  useEffect(() => {
    if (!lazy || !isLoopVideo(src)) return;
    const el = videoRef.current;
    if (!el) return;
    const io = new IntersectionObserver(
      (entries) => {
        const hit = entries.some((e) => e.isIntersecting);
        setInView(hit);
      },
      { rootMargin: "40px", threshold: 0.15 },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [lazy, src]);

  useEffect(() => {
    const el = videoRef.current;
    if (!el || !isLoopVideo(src)) return;
    if (inView) {
      void el.play().catch(() => {
        /* 自动播放被拒时静默，用户点开详情仍可看 */
      });
    } else {
      el.pause();
    }
  }, [inView, src]);

  if (!isLoopVideo(src)) {
    return <img src={src} alt={alt} className={className} loading="lazy" />;
  }

  return (
    <video
      ref={videoRef}
      src={src}
      poster={poster || undefined}
      className={className}
      muted
      loop
      playsInline
      autoPlay={!lazy}
      preload="metadata"
      aria-label={alt || undefined}
    />
  );
}
