# Official MediaKit Verification - 2026-07-25

- MediaKit archive: `mediakit-cli_0.2.0_windows_amd64.zip`
- MediaKit SHA-256: `d69a22ce1e28f69db5f0048f6bbe6a4186f32412a4bdbc00bf0e8f8ab2caf14d`
- MediaKit version: `0.2.0`
- FFmpeg version: `8.1.2-full_build-www.gyan.dev`
- FFmpeg archive SHA-256: `b8cdefab5f50590a076c27c2b56b0294a0e6154faded28ba1ba05ebc4f801f57`
- Input: `官方 MediaKit 样例 with spaces.mp4`, 320x180, 25 fps, AAC audio, 3 seconds

Results:

- `video probe-video-metadata`: succeeded with format, video stream, and audio stream metadata.
- `editing trim-video --start-time 0.4 --end-time 1.8`: succeeded; output MP4 duration `1.411995` seconds, size `90037` bytes.
- `editing extract-audio --format mp3`: succeeded; output MP3 duration `3.018594` seconds, size `24776` bytes.
- Both derived files passed independent `ffprobe` validation.

MediaKit 0.2.0 rejected the machine's newer nightly FFmpeg because its version starts with `N-*`. The provider therefore supports `VIDEOFORGE_MEDIAKIT_FFMPEG_DIR`, which prepends a stable FFmpeg directory only for MediaKit and verification subprocesses.
