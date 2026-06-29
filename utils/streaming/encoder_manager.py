import subprocess
import os
from .source_manager import SourceManager
from .overlay_manager import OverlayManager
from .watermark_manager import WatermarkManager
from .notification_manager import NotificationManager
from datetime import datetime
import threading
import time

class EncoderManager:
    def __init__(self, config):
        self.config = config
        self.process = None
        self.running = False
        
        self.stream_id = datetime.now().strftime("%Y%m%d-%H%M%S")
        self.watermark = None
        
        self.notifier = NotificationManager(
            config.get("bot_token"),
            config.get("chat_id")
        )
        
        self.stats = {
            "status": "stopped",
            "fps": 0,
            "bitrate": "0k",
            "uptime": "00:00:00",
            "stream_id": self.stream_id
        }

    def start(self):
        if self.running:
            return False
            
        source = self.config.get("source")
        if not source:
            raise ValueError("No source provided")
            
        resolved_source = SourceManager.resolve_source(source)
        
        self.watermark = WatermarkManager(
            self.stream_id,
            resolved_source,
            self.config.get("channel_name", "")
        )
        self.watermark.start()
        
        overlay = OverlayManager(self.config, self.stream_id, self.watermark.stream_sha)
        
        cmd = ["ffmpeg", "-thread_queue_size", "1024", "-re", "-i", resolved_source]
        
        inputs_count = 1
        
        has_bg_music = os.path.exists("bg_music.mp3")
        bg_music_idx = -1
        if has_bg_music:
            cmd.extend(["-stream_loop", "-1", "-i", "bg_music.mp3"])
            bg_music_idx = inputs_count
            inputs_count += 1
        
        overlays = self.config.get("overlays", {})
        
        # Determine the start idx for overlays inputs
        overlays_start_idx = inputs_count
        
        if overlays.get("logo") and os.path.exists("logo.png"):
            cmd.extend(["-loop", "1", "-i", "logo.png"])
            inputs_count += 1
        if overlays.get("qr") and os.path.exists("qr.png"):
            cmd.extend(["-loop", "1", "-i", "qr.png"])
            inputs_count += 1
        if overlays.get("banner") and os.path.exists("banner.png"):
            cmd.extend(["-loop", "1", "-i", "banner.png"])
            inputs_count += 1
            
        filter_str = overlay.get_filter_complex(inputs_start_idx=overlays_start_idx)
        
        probe = subprocess.run(
            ["ffprobe", "-v", "error", "-select_streams", "a:0",
             "-show_entries", "stream=codec_name",
             "-of", "default=noprint_wrappers=1:nokey=1", resolved_source],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE
        )
        has_audio = bool(probe.stdout.strip())
        
        audio_filter = ""
        a_out = "0:a?"
        if has_bg_music:
            if has_audio:
                audio_filter = f"[0:a]volume=1.0[a_main];[{bg_music_idx}:a]volume=0.3[a_bg];[a_main][a_bg]amix=inputs=2:duration=first,volume=2[out_a]"
                a_out = "[out_a]"
            else:
                audio_filter = f"[{bg_music_idx}:a]volume=0.3[out_a]"
                a_out = "[out_a]"
            
        if filter_str and filter_str != "[0:v]copy[out]":
            if audio_filter:
                filter_str += ";" + audio_filter
            cmd.extend(["-filter_complex", filter_str, "-map", "[out]", "-map", a_out])
        else:
            if audio_filter:
                cmd.extend(["-filter_complex", audio_filter, "-map", "0:v", "-map", a_out])
            else:
                cmd.extend(["-map", "0:v", "-map", "0:a?"])
            
        hw_accel = self.config.get("hw_accel", "none")
        vcodec = "libx264"
        if hw_accel == "nvenc": vcodec = "h264_nvenc"
        elif hw_accel == "qsv": vcodec = "h264_qsv"
        elif hw_accel == "amf": vcodec = "h264_amf"
        elif hw_accel == "vaapi": vcodec = "h264_vaapi"
        
        vbitrate = self.config.get("video_bitrate", "5000k")
        abitrate = self.config.get("audio_bitrate", "128k")
        fps = self.config.get("fps", "30")
        
        cmd.extend([
            "-c:v", vcodec,
            "-preset", "veryfast",
            "-profile:v", "high",
            "-pix_fmt", "yuv420p",
            "-b:v", vbitrate,
            "-maxrate", vbitrate,
            "-bufsize", str(int(vbitrate.replace("k",""))*2)+"k",
            "-g", str(int(fps)*2),
            "-r", str(fps),
            "-c:a", "aac",
            "-b:a", abitrate,
            "-ar", "48000",
            "-ac", "2"
        ])
        
        channel = self.config.get("channel_name", "")
        company = self.config.get("company_name", "")
        cmd.extend([
            "-metadata", f"title={channel}",
            "-metadata", f"author={company}",
            "-metadata", f"copyright={company}",
            "-metadata", f"comment=Protected Broadcast",
            "-metadata", f"stream_id={self.stream_id}",
            "-metadata", f"sha256={self.watermark.stream_sha}"
        ])
        
        if has_bg_music:
            cmd.append("-shortest")
        
        outputs = []
        yt_key = self.config.get("youtube_key", "").strip()
        fb_key = self.config.get("facebook_key", "").strip()
        
        if yt_key:
            outputs.append(f"rtmp://a.rtmp.youtube.com/live2/{yt_key}")
        if fb_key:
            outputs.append(f"rtmps://live-api-s.facebook.com:443/rtmp/{fb_key}")
            
        if not outputs:
            raise ValueError("No outputs defined (Please provide YouTube or Facebook stream key)")
            
        tee_outputs = []
        for out in outputs:
            tee_outputs.append(f"[f=flv]{out}")
            
        cmd.extend(["-f", "tee", "|".join(tee_outputs)])
        
        self.notifier.send(f"🟢 Encoder Started\nChannel: {channel}\nStream ID: {self.stream_id}")
        
        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, bufsize=1, universal_newlines=True)
        self.running = True
        self.stats["status"] = "running"
        
        threading.Thread(target=self._monitor, daemon=True).start()
        
        return True
        
    def stop(self):
        if self.running and self.process:
            self.process.terminate()
            self.process = None
        self.running = False
        if self.watermark:
            self.watermark.stop()
        self.stats["status"] = "stopped"
        self.notifier.send(f"🔴 Encoder Stopped\nStream ID: {self.stream_id}")
            
    def _monitor(self):
        while self.running and self.process:
            line = self.process.stdout.readline()
            if not line:
                break
            if "fps=" in line and "bitrate=" in line:
                try:
                    parts = line.split()
                    for p in parts:
                        if p.startswith("fps="):
                            self.stats["fps"] = p.split("=")[1]
                        elif p.startswith("bitrate="):
                            self.stats["bitrate"] = p.split("=")[1]
                        elif p.startswith("time="):
                            self.stats["uptime"] = p.split("=")[1]
                except:
                    pass
                    
        if self.running:
            self.stats["status"] = "error"
            self.notifier.send(f"⚠️ Encoder Crashed!\nStream ID: {self.stream_id}\nAttempting reconnect...")
            self.stop()
            time.sleep(5)
            self.start()
