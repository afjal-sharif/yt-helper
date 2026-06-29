import subprocess
import os

class SourceManager:
    @staticmethod
    def resolve_source(source):
        if "youtube.com" in source or "youtu.be" in source:
            try:
                cmd = ["yt-dlp", "-f", "bestvideo+bestaudio/best", "-g", source]
                result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
                if result.returncode == 0:
                    urls = result.stdout.strip().split('\n')
                    if len(urls) > 0:
                        return urls[0]
            except Exception as e:
                print(f"Error resolving youtube URL: {e}")
        
        # Check if it's a file in outputs folder
        if not source.startswith("http") and not source.startswith("rtmp"):
            output_path = os.path.join(os.getcwd(), 'Jigarrzz', 'outputs', source)
            if os.path.exists(output_path):
                return output_path
            
            # Or perhaps just from app.py root
            alt_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '..', 'outputs', source)
            if os.path.exists(alt_path):
                return alt_path

        return source
