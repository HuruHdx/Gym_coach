"""动作示范切片：静音循环小 MP4 + 抽帧封面 JPG。"""

from __future__ import annotations

import os
import shutil
import subprocess
from functools import lru_cache
from pathlib import Path

_API_ROOT = Path(__file__).resolve().parents[2]
_LOCAL_FFMPEG = _API_ROOT / "tools" / "ffmpeg" / "bin" / "ffmpeg.exe"


@lru_cache(maxsize=1)
def resolve_ffmpeg() -> str | None:
    """优先环境变量 / 项目 tools / imageio-ffmpeg 自带二进制，再退回 PATH。"""
    env = (os.environ.get("FFMPEG_BIN") or "").strip()
    if env and Path(env).exists():
        return env
    if _LOCAL_FFMPEG.exists():
        return str(_LOCAL_FFMPEG)
    try:
        import imageio_ffmpeg

        bundled = imageio_ffmpeg.get_ffmpeg_exe()
        if bundled and Path(bundled).exists():
            return bundled
    except Exception:
        pass
    return shutil.which("ffmpeg")


def ffmpeg_available() -> bool:
    return bool(resolve_ffmpeg())


def ffmpeg_loop_clip_cmd(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
) -> list[str]:
    """精确裁切：``-ss`` 放在 ``-i`` 之后，避免关键帧快切导致往前/往后多出一截。"""
    bin_path = resolve_ffmpeg() or "ffmpeg"
    return [
        bin_path,
        "-y",
        "-i",
        str(input_path),
        "-ss",
        f"{float(start):.3f}",
        "-t",
        f"{float(duration):.3f}",
        "-an",
        "-vf",
        "scale='min(540,iw)':-2,fps=24",
        "-c:v",
        "libx264",
        "-preset",
        "fast",
        "-crf",
        "26",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(output_path),
    ]


def ffmpeg_poster_cmd(
    input_path: str | Path,
    output_path: str | Path,
    *,
    at_time: float,
) -> list[str]:
    bin_path = resolve_ffmpeg() or "ffmpeg"
    return [
        bin_path,
        "-y",
        "-i",
        str(input_path),
        "-ss",
        f"{float(at_time):.3f}",
        "-frames:v",
        "1",
        "-vf",
        "scale='min(540,iw)':-2",
        "-q:v",
        "3",
        str(output_path),
    ]


def _run(cmd: list[str]) -> None:
    if not ffmpeg_available():
        raise RuntimeError(
            "未找到 ffmpeg。请安装系统 ffmpeg，或解压到 api/tools/ffmpeg/bin/ffmpeg.exe"
        )
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        raise RuntimeError((proc.stderr or proc.stdout or "ffmpeg 失败")[-2000:])


def make_loop_clip(
    input_path: str | Path,
    output_path: str | Path,
    *,
    start: float,
    duration: float,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(ffmpeg_loop_clip_cmd(input_path, out, start=start, duration=duration))
    return out


def make_poster_frame(
    input_path: str | Path,
    output_path: str | Path,
    *,
    at_time: float,
) -> Path:
    out = Path(output_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    _run(ffmpeg_poster_cmd(input_path, out, at_time=at_time))
    return out


def make_demo_pair(
    input_path: str | Path,
    *,
    start: float,
    end: float,
    out_dir: str | Path,
    stem: str = "demo",
) -> tuple[Path, Path]:
    """一次产出静音小 MP4 + 封面 JPG。

    封面取**切片成品的第 0 帧**（= 动图首帧），与 H5 循环播放起点一致；
    不再取选区中点，也不再对源片粗略 seek。
    """
    duration = max(0.5, float(end) - float(start))
    root = Path(out_dir)
    root.mkdir(parents=True, exist_ok=True)
    mp4 = make_loop_clip(input_path, root / f"{stem}_loop.mp4", start=start, duration=duration)
    jpg = make_poster_frame(mp4, root / f"{stem}_cover.jpg", at_time=0.0)
    return mp4, jpg
