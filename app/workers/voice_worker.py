from PySide6.QtCore import QThread, Signal
from app.core.voice import VoiceAssistant

class VoiceWorker(QThread):
    transcription_complete = Signal(str)
    error_occurred = Signal(str)

    def __init__(self, voice_assistant: VoiceAssistant, parent=None):
        super().__init__(parent)
        self.voice_assistant = voice_assistant

    def run(self):
        try:
            text = self.voice_assistant.stop_recording()
            self.transcription_complete.emit(text)
        except Exception as e:
            self.error_occurred.emit(str(e))
