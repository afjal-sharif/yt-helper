import os
import subprocess
import tempfile

def crop_to_aspect_ratio(clip, target_w, target_h):
    """
    Crops a video clip from its center to match the target aspect ratio,
    then resizes it to the target dimensions.
    (Kept for any remaining moviepy usage, but concatenate_clips no longer uses this.)
    """
    from moviepy.editor import VideoFileClip
    w, h = clip.size
    target_aspect = target_w / target_h
    current_aspect = w / h
    
    if current_aspect > target_aspect:
        new_w = int(h * target_aspect)
        x1 = (w - new_w) // 2
        x2 = x1 + new_w
        clip_cropped = clip.crop(x1=x1, y1=0, x2=x2, y2=h)
    else:
        new_h = int(w / target_aspect)
        y1 = (h - new_h) // 2
        y2 = y1 + new_h
        clip_cropped = clip.crop(x1=0, y1=y1, x2=w, y2=y2)
        
    return clip_cropped.resize(newsize=(target_w, target_h))

def concatenate_clips(video_paths, aspect_ratio="vertical", output_path=None):
    """
    Concatenates multiple video files using pure FFmpeg (no moviepy).
    Each clip is normalized to the target resolution before joining.
    Returns the total duration in seconds.
    """
    if not video_paths:
        raise ValueError("No video paths provided to concatenate.")

    existing = [p for p in video_paths if os.path.exists(p) and os.path.getsize(p) > 0]
    if not existing:
        raise ValueError("None of the provided video paths exist or could be loaded.")

    target_w, target_h = (1080, 1920) if aspect_ratio == "vertical" else (1920, 1080)

    # ── Step 1: Normalize every clip to target resolution ────────────
    norm_dir = tempfile.mkdtemp(prefix="concat_norm_")
    normalized = []

    for i, path in enumerate(existing):
        norm_path = os.path.join(norm_dir, f"norm_{i}.mp4")
        # scale+pad to target size, keep audio, re-encode to uniform codec
        vf = (
            f"scale={target_w}:{target_h}:force_original_aspect_ratio=decrease,"
            f"pad={target_w}:{target_h}:-1:-1:color=black,"
            f"fps=30"
        )
        cmd = [
            "ffmpeg", "-y", "-i", path,
            "-vf", vf,
            "-c:v", "libx264", "-preset", "fast",
            "-c:a", "aac", "-ar", "44100", "-ac", "2",
            norm_path
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode == 0 and os.path.exists(norm_path) and os.path.getsize(norm_path) > 0:
            normalized.append(norm_path)
        else:
            print(f"[concat] Warning: failed to normalize {path}, skipping.")

    if not normalized:
        raise RuntimeError("All clips failed to normalize — cannot concatenate.")

    # ── Step 2: Write concat list file ───────────────────────────────
    concat_list = os.path.join(norm_dir, "concat.txt")
    with open(concat_list, "w") as f:
        for p in normalized:
            f.write(f"file '{p}'\n")

    # ── Step 3: Get total duration via ffprobe ────────────────────────
    total_duration = 0.0
    for p in normalized:
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "default=noprint_wrappers=1:nokey=1", p],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        try:
            total_duration += float(probe.stdout.strip())
        except Exception:
            pass

    # ── Step 4: Concatenate ───────────────────────────────────────────
    if output_path:
        cmd = [
            "ffmpeg", "-y",
            "-f", "concat", "-safe", "0", "-i", concat_list,
            "-c", "copy",
            output_path
        ]
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if r.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
            err = r.stderr.decode("utf-8", errors="ignore")[-500:]
            raise RuntimeError(f"FFmpeg concat failed: {err}")

    # ── Cleanup temp normalized clips ─────────────────────────────────
    for p in normalized:
        try:
            os.remove(p)
        except Exception:
            pass
    try:
        os.remove(concat_list)
        os.rmdir(norm_dir)
    except Exception:
        pass

    return total_duration


def pitch_shift_audio(input_audio_path, output_audio_path, semitones=0.8):
    """
    Pitch shifts an audio file using FFmpeg's asetrate and atempo filters.
    semitones: shift amount (positive = higher, negative = lower).
    """
    multiplier = 2.0 ** (semitones / 12.0)
    sample_rate = 44100
    new_rate = int(sample_rate * multiplier)
    tempo = 1.0 / multiplier
    
    cmd = [
        "ffmpeg", "-y", "-i", input_audio_path,
        "-filter_complex", f"asetrate={new_rate},atempo={tempo}",
        output_audio_path
    ]
    subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)

def apply_copyright_filters(input_path, output_path, options):
    """
    Applies visual and audio transformations to bypass copyright filters.
    Uses pure FFmpeg subprocess for reliability — no moviepy silent failures.

    Filters applied:
    - Aspect Ratio (vertical 9:16, horizontal 16:9, or original)
    - Horizontal mirror (hflip)
    - 5% center zoom-in (crop + scale)
    - Speed adjustment (setpts + atempo)
    - Audio pitch shift (asetrate + atempo correction)
    """
    aspect       = options.get("aspect_ratio", "original")
    do_mirror    = options.get("mirror", True)
    do_zoom      = options.get("zoom", True)
    do_color_grading = options.get("color_grading", False)
    speed_factor = float(options.get("speed", 1.04))
    pitch_semi   = float(options.get("pitch_shift", 0.8))

    # ── Check if the source has an audio stream ──────────────────────
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    has_audio = bool(probe.stdout.strip())

    # ── Build video filter chain ──────────────────────────────────────
    vf = []

    if aspect == "vertical":
        # Center crop to 9:16 (1080×1920)
        vf.append("scale=1080:1920:force_original_aspect_ratio=increase,"
                  "crop=1080:1920")
    elif aspect == "horizontal":
        vf.append("scale=1920:1080:force_original_aspect_ratio=decrease,"
                  "pad=1920:1080:-1:-1:color=black")

    if do_mirror:
        vf.append("hflip")

    if do_zoom:
        # Scale up 5%, then crop center back to original size
        vf.append("scale=iw*1.05:ih*1.05,crop=iw/1.05:ih/1.05")

    if do_color_grading:
        vf.append("eq=contrast=1.05:saturation=1.15:gamma=0.95:brightness=0.01")

    if speed_factor != 1.0:
        vf.append(f"setpts=PTS/{speed_factor:.4f}")

    # ── Build audio filter chain ──────────────────────────────────────
    af = []

    if has_audio:
        if speed_factor != 1.0:
            af.append(f"atempo={speed_factor:.4f}")

        if pitch_semi != 0.0:
            # asetrate shifts pitch; atempo corrects back to original speed
            multiplier = 2.0 ** (pitch_semi / 12.0)
            new_rate   = int(44100 * multiplier)
            tempo_corr = 1.0 / multiplier
            af.append(f"asetrate={new_rate},atempo={tempo_corr:.6f}")

    # ── Assemble FFmpeg command ───────────────────────────────────────
    cmd = ["ffmpeg", "-y", "-i", input_path]
    
    bg_music = options.get("bg_music")
    has_bg_music = bool(bg_music and os.path.exists(bg_music))
    
    # Process overlays (add as extra inputs and use filter_complex)
    overlays = options.get("overlays", {})
    has_logo = overlays.get("logo") and os.path.exists("logo.png")
    has_qr = overlays.get("qr") and os.path.exists("qr.png")
    has_banner = overlays.get("banner") and os.path.exists("banner.png")
    
    inputs_count = 1
    
    bg_music_idx = -1
    if has_bg_music:
        cmd.extend(["-stream_loop", "-1", "-i", bg_music])
        bg_music_idx = inputs_count
        inputs_count += 1
        
    if has_logo:
        cmd.extend(["-i", "logo.png"])
        inputs_count += 1
    if has_qr:
        cmd.extend(["-i", "qr.png"])
        inputs_count += 1
    if has_banner:
        cmd.extend(["-i", "banner.png"])
        inputs_count += 1

    channel_name = options.get("channel_name", "Channel").replace("'", "").replace(":", "\\:")
    company_name = options.get("company_name", "Company").replace("'", "").replace(":", "\\:")
    
    # Windows/Linux font path logic
    import shutil
    base_font = "C:/Windows/Fonts/arial.ttf"
    if not os.path.exists(base_font):
        base_font = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        if not os.path.exists(base_font):
            base_font = "arial.ttf"
            
    local_font = "local_font.ttf"
    if os.path.exists(base_font) and not os.path.exists(local_font):
        try:
            shutil.copy(base_font, local_font)
        except Exception:
            pass
            
    font_ffmpeg = local_font if os.path.exists(local_font) else "arial.ttf"

    if vf:
        current_v = "[0:v]"
        filter_str = f"{current_v}{','.join(vf)}[v_base];"
        current_v = "[v_base]"
    else:
        current_v = "[0:v]"
        filter_str = ""

    current_input_idx = 2 if has_bg_music else 1
    if has_logo:
        filter_str += f"[{current_input_idx}:v]scale=250:-1,format=rgba,colorchannelmixer=aa=0.30[logo];"
        filter_str += f"{current_v}[logo]overlay=x='mod(t*100,W+250)-250':y=H-h-20[v_logo];"
        current_v = "[v_logo]"
        current_input_idx += 1
        
    if has_qr:
        filter_str += f"[{current_input_idx}:v]scale=180:180[qr];"
        filter_str += f"{current_v}[qr]overlay=x=20:y=H-h-20[v_qr];"
        current_v = "[v_qr]"
        current_input_idx += 1
        
    if has_banner:
        filter_str += f"[{current_input_idx}:v]format=rgba[banner];"
        filter_str += f"{current_v}[banner]overlay=x=(W-w)/2:y=(H-h)/2[v_ban];"
        current_v = "[v_ban]"
        current_input_idx += 1
        
    if overlays.get("text"):
        filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':text='{channel_name}':fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5:x=20:y=20[v_t1];"
        filter_str += f"[v_t1]drawtext=fontfile='{font_ffmpeg}':text='© {company_name}':fontsize=26:fontcolor=yellow:box=1:boxcolor=black@0.5:x=20:y=70[v_t2];"
        current_v = "[v_t2]"
        
    if overlays.get("timestamp"):
        filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':text='%{{localtime\:%Y-%m-%d %H\\\:%M\\\:%S}}':fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:x=w-tw-20:y=60[v_ts];"
        current_v = "[v_ts]"
        
    if overlays.get("watermark") and os.path.exists("forensic.txt"):
        filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':textfile=forensic.txt:reload=1:fontsize=22:fontcolor=cyan:box=1:boxcolor=black@0.5:x=(w-tw)/2:y=h-50[v_wm];"
        current_v = "[v_wm]"

    if filter_str:
        # Final output pad rename
        if current_v != "[0:v]":
            filter_str += f"{current_v}copy[out_v]"
            cmd += ["-filter_complex", filter_str, "-map", "[out_v]"]
        else:
            cmd += ["-map", "0:v"]
    else:
        cmd += ["-map", "0:v"]

    # Handle Audio
    if has_audio or has_bg_music:
        a_filter = ""
        a_out = ""
        
        if has_audio:
            if af:
                af_str = ",".join(af)
                a_filter += f"[0:a]{af_str}[a_main];"
                a_out = "[a_main]"
            else:
                a_filter += "[0:a]anull[a_main];"
                a_out = "[a_main]"
                
        if has_bg_music:
            if has_audio:
                a_filter += f"[{bg_music_idx}:a]volume=0.3[a_bg]; {a_out}[a_bg]amix=inputs=2:duration=first,volume=2[out_a]"
                a_out = "[out_a]"
            else:
                a_filter += f"[{bg_music_idx}:a]volume=0.3[out_a]"
                a_out = "[out_a]"
                
        if a_filter.endswith(";"):
            a_filter = a_filter[:-1]
            
        if a_filter and a_filter != "[0:a]anull[a_main]":
            if "-filter_complex" in cmd:
                cmd[cmd.index("-filter_complex") + 1] += f";{a_filter}"
                cmd += ["-map", a_out]
            else:
                cmd += ["-filter_complex", a_filter, "-map", a_out]
        else:
            cmd += ["-map", "0:a"]
            
        cmd += ["-c:a", "aac"]
        
        abitrate = str(options.get("abitrate", "")).strip()
        if abitrate:
            if abitrate.isdigit(): abitrate += "k"
            cmd += ["-b:a", abitrate]
    else:
        cmd += ["-an"]

    # Video codec & HW accel
    hw_accel = options.get("hw_accel", "none")
    vcodec = "libx264"
    if hw_accel == "nvenc": vcodec = "h264_nvenc"
    elif hw_accel == "qsv": vcodec = "h264_qsv"
    elif hw_accel == "amf": vcodec = "h264_amf"
    elif hw_accel == "vaapi": vcodec = "h264_vaapi"
    
    cmd += ["-c:v", vcodec, "-preset", "fast", "-movflags", "+faststart"]
    
    vbitrate = str(options.get("vbitrate", "")).strip()
    if vbitrate:
        if vbitrate.isdigit(): vbitrate += "k"
        cmd += ["-b:v", vbitrate, "-maxrate", vbitrate, "-bufsize", str(int(vbitrate.replace("k","") or 0)*2)+"k"]
        
    fps = options.get("fps", "")
    if fps:
        cmd += ["-r", str(fps)]
        
    if has_bg_music:
        cmd += ["-shortest"]

    cmd.append(output_path)

    # ── Run ───────────────────────────────────────────────────────────
    result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    if result.returncode != 0 or not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        err = result.stderr.decode("utf-8", errors="ignore")[-2000:]
        raise RuntimeError(f"FFmpeg filter failed for {os.path.basename(input_path)}: {err}")


def slice_video(input_path, output_dir, mode="auto", intervals=8, custom_ranges=None):
    """
    Slices a video into multiple segments.
    mode: "auto" (split every N seconds) or "timestamps" (split by custom list of ranges).
    intervals: number of seconds per slice in auto mode.
    custom_ranges: list of tuples/lists e.g. [[10, 20], [35, 45]] (in seconds).
    Returns a list of created file paths.
    """
    probe = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", input_path],
        stdout=subprocess.PIPE, stderr=subprocess.PIPE
    )
    try:
        duration = float(probe.stdout.strip())
    except ValueError:
        duration = 0.0
    
    slices = []
    if mode == "auto":
        start = 0
        idx = 1
        while start < duration:
            end = min(start + intervals, duration)
            # Avoid tiny trailing clips less than 1 second
            if duration - end < 1.0:
                end = duration
            slices.append((start, end, f"clip_{idx}.mp4"))
            idx += 1
            if end == duration:
                break
            start = end
    elif mode == "timestamps" and custom_ranges:
        for idx, r in enumerate(custom_ranges, 1):
            start = r[0]
            end = min(r[1], duration)
            if start < duration:
                slices.append((start, end, f"clip_{idx}.mp4"))
                
    output_files = []
    for start, end, filename in slices:
        out_path = os.path.join(output_dir, filename)
        # Use FFmpeg directly for fast lossless seeking and cutting
        cmd = [
            "ffmpeg", "-y", "-ss", str(start), "-to", str(end),
            "-i", input_path, "-c", "copy", out_path
        ]
        subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if os.path.exists(out_path) and os.path.getsize(out_path) > 0:
            output_files.append(out_path)
            
    return output_files
