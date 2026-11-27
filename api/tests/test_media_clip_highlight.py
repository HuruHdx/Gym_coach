"""highlight 切片命令：保留音轨、不带 -an。"""

from app.services.media_clip import ffmpeg_highlight_clip_cmd, ffmpeg_loop_clip_cmd


def test_highlight_cmd_keeps_audio():
    cmd = ffmpeg_highlight_clip_cmd(
        "in.mp4",
        "out.mp4",
        start=10.0,
        duration=30.0,
    )
    assert "-an" not in cmd
    assert "-c:a" in cmd
    assert "aac" in cmd
    assert "-b:a" in cmd
    assert "64k" in cmd
    assert "-ac" in cmd
    # 精确裁切：-ss 在 -i 之后
    i_at = cmd.index("-i")
    ss_at = cmd.index("-ss")
    assert ss_at > i_at
    assert "libx264" in cmd
    assert "28" in cmd  # crf


def test_demo_cmd_strips_audio():
    cmd = ffmpeg_loop_clip_cmd("in.mp4", "out.mp4", start=1.0, duration=4.0)
    assert "-an" in cmd
    assert "-c:a" not in cmd
