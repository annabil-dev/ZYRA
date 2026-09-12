import os
import asyncio
import tempfile
from PySide6.QtCore import QThread, Signal
import edge_tts

class TTSWorker(QThread):
    audio_ready = Signal(str)
    error_occurred = Signal(str)
    
    def __init__(self, text: str, voice: str = "id-ID-GadisNeural", parent=None):
        super().__init__(parent)
        self.text = text
        self.voice = voice
        self.is_running = True
        
    def run(self):
        try:
            # We must run asyncio in a new event loop for this thread
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            loop.run_until_complete(self._generate_audio())
        except Exception as e:
            self.error_occurred.emit(str(e))
            
    async def _generate_audio(self):
        try:
            # Clean up markdown artifacts before speaking
            import re
            clean_text = re.sub(r'```.*?```', 'Kode disembunyikan.', self.text, flags=re.DOTALL)
            clean_text = re.sub(r'[*#_`~]', '', clean_text)
            
            # Avoid speaking if no text
            if not clean_text.strip():
                return
                
            communicate = edge_tts.Communicate(clean_text, self.voice)
            
            # Save to temp file
            fd, path = tempfile.mkstemp(suffix=".mp3", prefix="zyra_tts_")
            os.close(fd)
            
            await communicate.save(path)
            
            if self.is_running:
                self.audio_ready.emit(path)
        except Exception as e:
            self.error_occurred.emit(str(e))
            
    def stop(self):
        self.is_running = False
