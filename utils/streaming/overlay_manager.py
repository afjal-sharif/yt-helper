import os

class OverlayManager:
    def __init__(self, config, stream_id, stream_sha):
        self.config = config
        self.stream_id = stream_id
        self.stream_sha = stream_sha
        
    def get_filter_complex(self, inputs_start_idx=1):
        overlays = self.config.get('overlays', {})
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
        
        channel_name = self.config.get("channel_name", "Channel").replace("'", "").replace(":", "\\:")
        company_name = self.config.get("company_name", "Company").replace("'", "").replace(":", "\\:")
        
        filter_str = ""
        inputs_count = inputs_start_idx
        
        has_logo = overlays.get("logo") and os.path.exists("logo.png")
        has_qr = overlays.get("qr") and os.path.exists("qr.png")
        has_banner = overlays.get("banner") and os.path.exists("banner.png")
        
        current_v = "[0:v]"
        
        if has_logo:
            filter_str += f"[{inputs_count}:v]scale=250:-1,format=rgba,colorchannelmixer=aa=0.30[logo];"
            filter_str += f"{current_v}[logo]overlay=x='mod(t*100,W+250)-250':y=H-h-20[v_logo];"
            current_v = "[v_logo]"
            inputs_count += 1
            
        if has_qr:
            filter_str += f"[{inputs_count}:v]scale=180:180[qr];"
            filter_str += f"{current_v}[qr]overlay=x=20:y=H-h-20[v_qr];"
            current_v = "[v_qr]"
            inputs_count += 1
            
        if has_banner:
            filter_str += f"[{inputs_count}:v]format=rgba[banner];"
            filter_str += f"{current_v}[banner]overlay=x=(W-w)/2:y=(H-h)/2[v_ban];"
            current_v = "[v_ban]"
            inputs_count += 1
            
        if overlays.get("text"):
            filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':text='{channel_name}':fontsize=36:fontcolor=white:box=1:boxcolor=black@0.5:x=20:y=20[v_t1];"
            filter_str += f"[v_t1]drawtext=fontfile='{font_ffmpeg}':text='© {company_name}':fontsize=26:fontcolor=yellow:box=1:boxcolor=black@0.5:x=20:y=70[v_t2];"
            filter_str += f"[v_t2]drawtext=fontfile='{font_ffmpeg}':text='STREAM ID\: {self.stream_id}':fontsize=24:fontcolor=red:box=1:boxcolor=black@0.5:x=w-tw-20:y=20[v_t3];"
            current_v = "[v_t3]"
            
        if overlays.get("timestamp"):
            filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':text='%{{localtime\:%Y-%m-%d %H\\\:%M\\\:%S}}':fontsize=24:fontcolor=white:box=1:boxcolor=black@0.5:x=w-tw-20:y=60[v_ts];"
            current_v = "[v_ts]"
            
        if overlays.get("watermark"):
            filter_str += f"{current_v}drawtext=fontfile='{font_ffmpeg}':textfile=forensic.txt:reload=1:fontsize=22:fontcolor=cyan:box=1:boxcolor=black@0.5:x=(w-tw)/2:y=h-50[v_wm];"
            current_v = "[v_wm]"
            
        if current_v != "[0:v]":
            filter_str += f"{current_v}copy[out]"
        else:
            filter_str = "[0:v]copy[out]"
            
        return filter_str
