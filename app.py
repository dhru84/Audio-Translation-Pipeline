from flask import Flask, request, jsonify, render_template
from flask_cors import CORS
import os
import requests
import json
from pydub import AudioSegment
from pydub.utils import make_chunks
from pydub.effects import normalize
import time
from pathlib import Path
import librosa
import soundfile as sf
import noisereduce as nr
import numpy as np
import threading
from werkzeug.utils import secure_filename

app = Flask(__name__)
CORS(app)

# Configuration
UPLOAD_FOLDER = 'uploads'
ALLOWED_EXTENSIONS = {'wav', 'mp3', 'flac', 'aac', 'm4a'}

os.makedirs(UPLOAD_FOLDER, exist_ok=True)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 100 * 1024 * 1024  # 100MB max file size

# Global variables to store processing status
processing_status = {}

class AudioTranslationPipeline:
    def __init__(self, api_key):
        self.api_key = api_key
        self.headers = {
            "API-Subscription-Key": api_key,
            "Content-Type": "application/json"
        }

    def verify_chunk_size(self, chunk_file, max_size_mb=25):
        """
        Verify chunk size before processing (Sarvam AI has file size limits)
        """
        file_size_mb = os.path.getsize(chunk_file) / (1024 * 1024)
        print(f"Chunk {chunk_file}: {file_size_mb:.2f} MB")

        if file_size_mb > max_size_mb:
            print(f"Warning: Chunk exceeds {max_size_mb}MB limit. Compressing...")
            # Compress audio if too large
            audio = AudioSegment.from_wav(chunk_file)
            # Reduce sample rate and bit depth
            audio = audio.set_frame_rate(16000).set_sample_width(2)
            compressed_file = chunk_file.replace('.wav', '_compressed.wav')
            audio.export(compressed_file, format="wav")

            new_size_mb = os.path.getsize(compressed_file) / (1024 * 1024)
            print(f"Compressed to: {new_size_mb:.2f} MB")
            return compressed_file

        return chunk_file

    def reduce_noise(self, audio_file):
        """
        Reduce noise in audio file using noisereduce
        """
        print(f"Reducing noise in: {audio_file}")

        # Load audio with librosa
        y, sr = librosa.load(audio_file, sr=None)

        # Reduce noise
        reduced_noise = nr.reduce_noise(y=y, sr=sr, stationary=False, prop_decrease=0.8)

        # Save the denoised audio
        denoised_file = audio_file.replace('.wav', '_denoised.wav')
        sf.write(denoised_file, reduced_noise, sr)

        print(f"Denoised audio saved: {denoised_file}")
        return denoised_file

    def calculate_optimal_speech_rate(self, text, target_duration_ms):
        """
        Calculate optimal speech rate to match target duration without trimming
        """
        # Estimate speaking time based on text characteristics
        word_count = len(text.split())
        char_count = len(text)

        # Average speaking rates (words per minute)
        # Kannada typically spoken at 140-160 WPM
        base_wpm = 150

        # Calculate target WPM based on duration
        target_minutes = target_duration_ms / 60000
        if target_minutes > 0:
            target_wpm = word_count / target_minutes

            # Calculate pace adjustment (1.0 = normal, 0.5 = slow, 2.0 = fast)
            pace_multiplier = target_wpm / base_wpm

            # Limit pace to reasonable bounds (0.6 to 1.8)
            pace_multiplier = max(0.6, min(1.8, pace_multiplier))

            print(f"Text: {word_count} words, Target: {target_minutes:.2f} min")
            print(f"Target WPM: {target_wpm:.1f}, Pace multiplier: {pace_multiplier:.2f}")

            return pace_multiplier

        return 1.0  # Default pace

    def match_speech_timing(self, generated_audio_file, target_duration_ms):
        """
        Adjust speech timing to match original without trimming content
        Only adds silence if significantly shorter, but preserves all speech
        """
        print(f"Matching speech timing to target: {target_duration_ms/1000:.2f}s")

        # Load generated audio
        generated_audio = AudioSegment.from_wav(generated_audio_file)
        generated_duration = len(generated_audio)

        print(f"Generated duration: {generated_duration/1000:.2f}s")
        print(f"Target duration: {target_duration_ms/1000:.2f}s")

        # If generated audio is significantly shorter, add some silence at the end
        # This helps maintain natural pauses between chunks
        if generated_duration < (target_duration_ms * 0.8):  # If less than 80% of target
            silence_duration = target_duration_ms - generated_duration
            silence = AudioSegment.silent(duration=silence_duration)
            matched_audio = generated_audio + silence

            matched_file = generated_audio_file.replace('.wav', '_timed.wav')
            matched_audio.export(matched_file, format="wav")

            print(f"Added {silence_duration/1000:.2f}s silence for natural timing")
            return matched_file
        else:
            print("Duration is acceptable, no timing adjustment needed")
            return generated_audio_file

    def split_audio(self, input_file, chunk_length_ms=30000, output_dir="chunks"):
        """
        Split audio file into chunks of specified length (default 30 seconds)
        """
        print(f"Loading audio file: {input_file}")
        audio = AudioSegment.from_wav(input_file)

        # Normalize audio before splitting
        audio = normalize(audio)
        print("Audio normalized")

        # Create output directory
        os.makedirs(output_dir, exist_ok=True)

        # Create chunks
        chunks = make_chunks(audio, chunk_length_ms)

        chunk_files = []
        chunk_durations = []

        for i, chunk in enumerate(chunks):
            chunk_name = f"{output_dir}/chunk_{i:03d}.wav"
            # Export with consistent quality
            chunk.export(chunk_name, format="wav", parameters=["-ac", "1", "-ar", "22050"])
            chunk_files.append(chunk_name)
            chunk_durations.append(len(chunk))
            print(f"Created chunk: {chunk_name} (Duration: {len(chunk)/1000:.2f}s)")

        return chunk_files, chunk_durations

    def speech_to_text(self, audio_file_path, source_language='en-IN'):
        """
        Convert speech to text using Sarvam AI
        """
        print(f"Converting speech to text: {audio_file_path}")

        url = "https://api.sarvam.ai/speech-to-text"

        with open(audio_file_path, 'rb') as audio_file:
            files = {
                'file': ('audio.wav', audio_file, 'audio/wav')
            }
            headers = {
                "API-Subscription-Key": self.api_key
            }
            data = {
                'language_code': source_language
            }

            response = requests.post(url, files=files, headers=headers, data=data)

            if response.status_code == 200:
                result = response.json()
                transcript = result.get('transcript', '')
                print(f"Transcript: {transcript}")
                return transcript
            else:
                print(f"STT Error: {response.status_code} - {response.text}")
                return None

    def translate_text(self, text, source_language='en-IN', target_language='kn-IN'):
        """
        Translate text using Sarvam AI
        """
        print(f"Translating text: {text[:50]}...")

        url = "https://api.sarvam.ai/translate"

        payload = {
            "input": text,
            "source_language_code": source_language,
            "target_language_code": target_language,
            "speaker_gender": "Male",
            "mode": "formal",
            "model": "mayura:v1",
            "enable_preprocessing": True
        }

        response = requests.post(url, json=payload, headers=self.headers)

        if response.status_code == 200:
            result = response.json()
            translated_text = result.get('translated_text', '')
            print(f"Translated: {translated_text}")
            return translated_text
        else:
            print(f"Translation Error: {response.status_code} - {response.text}")
            return None

    def text_to_speech(self, text, output_file, target_language='kn-IN', target_duration_ms=None):
        """
        Convert text to speech with natural speed matching
        """
        print(f"Converting text to speech: {output_file}")

        url = "https://api.sarvam.ai/text-to-speech"

        # Calculate optimal speech rate to match timing naturally
        speech_pace = 1.0
        if target_duration_ms:
            speech_pace = self.calculate_optimal_speech_rate(text, target_duration_ms)

        payload = {
            "inputs": [text],
            "target_language_code": target_language,
            "speaker": "meera",  # Kannada female voice
            "pitch": 0,
            "pace": speech_pace,  # Dynamically adjusted pace
            "loudness": 1.2,
            "speech_sample_rate": 22050,
            "enable_preprocessing": True,
            "model": "bulbul:v1"
        }

        print(f"Using speech pace: {speech_pace:.2f}x")

        response = requests.post(url, json=payload, headers=self.headers)

        if response.status_code == 200:
            result = response.json()
            audio_data = result.get('audios', [])

            if audio_data:
                # The audio data is base64 encoded
                import base64
                audio_bytes = base64.b64decode(audio_data[0])

                # Save initial audio
                temp_file = output_file.replace('.wav', '_temp.wav')
                with open(temp_file, 'wb') as f:
                    f.write(audio_bytes)

                # Reduce noise in generated audio
                denoised_file = self.reduce_noise(temp_file)

                # Use match_speech_timing instead of match_audio_duration
                if target_duration_ms:
                    final_file = self.match_speech_timing(denoised_file, target_duration_ms)
                    # Copy final file to output location
                    if final_file != denoised_file:
                        os.rename(final_file, output_file)
                        if os.path.exists(denoised_file):
                            os.remove(denoised_file)
                    else:
                        os.rename(denoised_file, output_file)
                else:
                    os.rename(denoised_file, output_file)

                # Clean up temp files
                if os.path.exists(temp_file):
                    os.remove(temp_file)

                print(f"High-quality speech-matched audio saved: {output_file}")
                return output_file
            else:
                print("No audio data received")
                return None
        else:
            print(f"TTS Error: {response.status_code} - {response.text}")
            return None

    def process_chunk(self, chunk_file, chunk_duration_ms, output_dir="translated_chunks", source_language='en-IN', target_language='kn-IN'):
        """
        Process a single audio chunk through the complete pipeline with quality improvements
        """
        os.makedirs(output_dir, exist_ok=True)

        chunk_name = Path(chunk_file).stem
        output_file = f"{output_dir}/{chunk_name}_{target_language.split('-')[0]}.wav"

        # Step 1: Verify chunk size
        verified_chunk = self.verify_chunk_size(chunk_file)

        # Step 2: Speech to Text
        transcript = self.speech_to_text(verified_chunk, source_language)
        if not transcript:
            return None

        # Step 3: Translate
        translated_text = self.translate_text(transcript, source_language, target_language)
        if not translated_text:
            return None

        # Step 4: Text to Speech with duration matching
        target_audio = self.text_to_speech(translated_text, output_file, target_language, target_duration_ms=chunk_duration_ms)

        # Clean up compressed file if created
        if verified_chunk != chunk_file:
            os.remove(verified_chunk)

        # Add small delay to avoid rate limiting
        time.sleep(1)

        return target_audio

    def merge_audio_chunks(self, chunk_files, output_file="final_output.wav"):
        """
        Merge translated audio chunks into final output with quality enhancement
        """
        print("Merging audio chunks...")

        # Filter out None values and non-existent files
        valid_chunks = [f for f in chunk_files if f and os.path.exists(f)]

        if not valid_chunks:
            print("No valid audio chunks to merge")
            return None

        combined = AudioSegment.empty()

        for chunk_file in valid_chunks:
            try:
                chunk_audio = AudioSegment.from_wav(chunk_file)
                # Normalize each chunk before merging
                chunk_audio = normalize(chunk_audio)
                combined += chunk_audio
                print(f"Added chunk: {chunk_file}")
            except Exception as e:
                print(f"Error processing chunk {chunk_file}: {e}")

        # Apply final normalization and export with high quality
        combined = normalize(combined)
        combined.export(output_file, format="wav", parameters=["-ac", "1", "-ar", "22050", "-b:a", "256k"])

        print(f"Final merged audio saved: {output_file}")
        return output_file

    def process_complete_pipeline(self, input_audio_file, output_directory, source_language='en-IN', target_language='kn-IN', task_id=None):
        """
        Complete pipeline: Split -> Translate each chunk -> Merge with quality enhancements
        """
        print("Starting complete audio translation pipeline...")

        try:
            if task_id:
                processing_status[task_id] = {"status": "processing", "progress": "Splitting audio..."}

            # Step 1: Split audio into 30-second chunks with duration tracking
            chunk_files, chunk_durations = self.split_audio(input_audio_file)

            if task_id:
                processing_status[task_id]["progress"] = "Processing audio chunks..."

            # Step 2: Process each chunk with duration matching
            translated_chunks = []
            for i, (chunk_file, chunk_duration) in enumerate(zip(chunk_files, chunk_durations)):
                print(f"\n{'='*60}")
                print(f"Processing chunk {i+1}/{len(chunk_files)}: {chunk_file}")
                print(f"Original duration: {chunk_duration/1000:.2f}s")
                print(f"{'='*60}")

                if task_id:
                    processing_status[task_id]["progress"] = f"Processing chunk {i+1}/{len(chunk_files)}"

                translated_chunk = self.process_chunk(chunk_file, chunk_duration, "translated_chunks", source_language, target_language)
                translated_chunks.append(translated_chunk)

            if task_id:
                processing_status[task_id]["progress"] = "Merging audio chunks..."

            # Step 3: Merge translated chunks
            final_output_path = os.path.join(output_directory, f"translated_audio_{target_language.split('-')[0]}.wav")
            final_output = self.merge_audio_chunks(translated_chunks, final_output_path)

            # Step 4: Match audio duration with original
            if final_output:
                matched_output_path = os.path.join(output_directory, f"final_translated_audio_{target_language.split('-')[0]}.wav")
                self.match_audio_duration(input_audio_file, final_output, matched_output_path)
                
                if task_id:
                    processing_status[task_id] = {"status": "completed", "output_file": matched_output_path}
                
                return matched_output_path
            
            if task_id:
                processing_status[task_id] = {"status": "failed", "error": "Failed to merge audio chunks"}

        except Exception as e:
            print(f"Pipeline error: {str(e)}")
            if task_id:
                processing_status[task_id] = {"status": "failed", "error": str(e)}
            return None

    @staticmethod
    def match_audio_duration(english_audio_path, kannada_audio_path, output_path):
        # Load English audio
        eng_audio, eng_sr = librosa.load(english_audio_path, sr=None)
        eng_duration = librosa.get_duration(y=eng_audio, sr=eng_sr)

        # Load Kannada audio
        kan_audio, kan_sr = librosa.load(kannada_audio_path, sr=None)
        kan_duration = librosa.get_duration(y=kan_audio, sr=kan_sr)

        print(f"English Duration: {eng_duration:.2f}s")
        print(f"Kannada Duration: {kan_duration:.2f}s")

        # Calculate time-stretch ratio
        raw_ratio = kan_duration / eng_duration
        print(f"Raw time-stretch ratio: {raw_ratio:.3f}")

        # Define natural sounding speed limits
        MIN_SPEED = 0.9
        MAX_SPEED = 1.5

        # Clamp ratio for natural speech
        clamped_ratio = min(max(raw_ratio, MIN_SPEED), MAX_SPEED)
        print(f"Clamped time-stretch ratio: {clamped_ratio:.3f}")

        # Apply time-stretch
        adjusted_kan_audio = librosa.effects.time_stretch(kan_audio, rate=clamped_ratio)

        # Save to temp WAV
        temp_path = "temp_adjusted.wav"
        sf.write(temp_path, adjusted_kan_audio, kan_sr)

        # Reload with pydub to handle silence trimming/padding
        adjusted_segment = AudioSegment.from_wav(temp_path)
        adjusted_duration = len(adjusted_segment) / 1000.0  # in seconds

        # Final trim or pad
        target_ms = int(eng_duration * 1000)
        adjusted_ms = int(adjusted_duration * 1000)

        if adjusted_ms < target_ms:
            silence = AudioSegment.silent(duration=(target_ms - adjusted_ms))
            final_audio = adjusted_segment + silence
            print(f"Padded with {target_ms - adjusted_ms}ms silence.")
        else:
            final_audio = adjusted_segment[:target_ms]
            print(f"Trimmed excess audio by {adjusted_ms - target_ms}ms.")

        # Save final output
        final_audio.export(output_path, format="wav")
        print(f"✅ Audio saved to {output_path} with exact duration: {eng_duration:.2f}s")

        # Cleanup
        if os.path.exists(temp_path):
            os.remove(temp_path)

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def process_audio_async(input_file, output_dir, api_key, source_lang, target_lang, task_id):
    """Run audio processing in background thread"""
    pipeline = AudioTranslationPipeline(api_key)
    pipeline.process_complete_pipeline(input_file, output_dir, source_lang, target_lang, task_id)

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/convert', methods=['POST'])
def convert_audio():
    try:
        # Get form data
        api_key = request.form.get('api_key')
        source_language = request.form.get('source_language', 'en-IN')
        target_language = request.form.get('target_language', 'kn-IN')
        output_directory = request.form.get('output_directory', 'output')
        
        # Check if file was uploaded
        if 'audio_file' not in request.files:
            return jsonify({'error': 'No audio file uploaded'}), 400
            
        file = request.files['audio_file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
            
        if not allowed_file(file.filename):
            return jsonify({'error': 'Invalid file format. Allowed formats: wav, mp3, flac, aac, m4a'}), 400
            
        if not api_key:
            return jsonify({'error': 'API key is required'}), 400

        # Create output directory if it doesn't exist
        os.makedirs(output_directory, exist_ok=True)
        
        # Save uploaded file
        filename = secure_filename(file.filename)
        input_file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(input_file_path)
        
        # Convert to WAV if necessary
        if not filename.lower().endswith('.wav'):
            audio = AudioSegment.from_file(input_file_path)
            wav_filename = filename.rsplit('.', 1)[0] + '.wav'
            wav_file_path = os.path.join(app.config['UPLOAD_FOLDER'], wav_filename)
            audio.export(wav_file_path, format="wav")
            input_file_path = wav_file_path
        
        # Generate unique task ID
        import uuid
        task_id = str(uuid.uuid4())
        
        # Start processing in background thread
        thread = threading.Thread(
            target=process_audio_async, 
            args=(input_file_path, output_directory, api_key, source_language, target_language, task_id)
        )
        thread.start()
        
        return jsonify({
            'message': 'Processing started',
            'task_id': task_id
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/status/<task_id>', methods=['GET'])
def get_status(task_id):
    if task_id in processing_status:
        return jsonify(processing_status[task_id])
    else:
        return jsonify({'error': 'Task not found'}), 404

if __name__ == '__main__':
    app.run(debug=True, port=5000)