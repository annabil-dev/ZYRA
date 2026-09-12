import os
import queue
import threading
import sounddevice as sd
import numpy as np
import scipy.io.wavfile as wav
import whisper

class VoiceAssistant:
    def __init__(self):
        self.is_recording = False
        self.audio_queue = queue.Queue()
        self.sample_rate = 16000
        self.model = None
        self.model_lock = threading.Lock()
        
    def _load_model_if_needed(self):
        with self.model_lock:
            if self.model is None:
                # Load the tiny model by default to keep it fast
                print("Loading Whisper model...")
                self.model = whisper.load_model("base")
                print("Whisper model loaded.")
                
    def audio_callback(self, indata, frames, time, status):
        """This is called (from a separate thread) for each audio block."""
        if status:
            print(status, flush=True)
        if self.is_recording:
            self.audio_queue.put(indata.copy())

    def start_recording(self):
        """Starts recording audio from the microphone."""
        self.is_recording = True
        # Clear queue
        while not self.audio_queue.empty():
            self.audio_queue.get()
            
        self.stream = sd.InputStream(
            samplerate=self.sample_rate, 
            channels=1, 
            callback=self.audio_callback,
            dtype='float32'
        )
        self.stream.start()

    def stop_recording(self) -> str:
        """Stops recording, processes the audio with Whisper, and returns transcribed text."""
        self.is_recording = False
        if hasattr(self, 'stream'):
            self.stream.stop()
            self.stream.close()
            
        # Collect all audio chunks
        audio_data = []
        while not self.audio_queue.empty():
            audio_data.append(self.audio_queue.get())
            
        if not audio_data:
            return ""
            
        audio_np = np.concatenate(audio_data, axis=0)
        
        # Save to temp wav file
        temp_wav = os.path.join(os.environ.get("TEMP", "."), "temp_zyra_voice.wav")
        wav.write(temp_wav, self.sample_rate, audio_np)
        
        # Make sure model is loaded
        self._load_model_if_needed()
        
        try:
            # Transcribe
            result = self.model.transcribe(temp_wav, language="id") # Default to Indonesian for ZYRA
            text = result.get("text", "").strip()
            
            # Clean up
            if os.path.exists(temp_wav):
                os.remove(temp_wav)
                
            return text
        except Exception as e:
            print(f"Error transcribing audio: {e}")
            return ""
