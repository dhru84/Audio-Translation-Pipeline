# Audio Translation Pipeline

This project is a web-based pipeline for translating audio files from one language to another using Sarvam AI APIs. It splits audio into manageable chunks, transcribes, translates, and synthesizes speech in the target language, then merges the results into a single output file.

## Features

- **Audio Upload:** Upload audio files in WAV, MP3, FLAC, AAC, or M4A formats (up to 100MB).
- **Language Selection:** Choose source and target languages from a list of supported Indian languages.
- **Chunked Processing:** Audio is split into 30-second chunks for efficient processing and API compatibility.
- **Noise Reduction:** Each chunk undergoes noise reduction for improved transcription and synthesis quality.
- **Speech-to-Text:** Uses Sarvam AI's API to transcribe each chunk.
- **Translation:** Transcribes are translated to the target language using Sarvam AI.
- **Text-to-Speech:** Translated text is synthesized into speech, with timing matched to the original chunk.
- **Merging:** All translated chunks are merged into a single output audio file, normalized for quality.
- **Progress Tracking:** Real-time progress updates in the web UI.
- **Asynchronous Processing:** Audio processing runs in the background; users can check status via task ID.

## Requirements

- Python 3.8+
- [Sarvam AI API Key](https://sarvam.ai/)
- The following Python packages:
  - Flask
  - flask-cors
  - pydub
  - librosa
  - soundfile
  - noisereduce
  - numpy
  - requests
  - werkzeug

Install dependencies with:

```sh
pip install -r requirements.txt
```

Create a `requirements.txt` file with:

```
Flask
flask-cors
pydub
librosa
soundfile
noisereduce
numpy
requests
werkzeug
```

## Usage

1. **Clone the repository** and navigate to the project directory.

2. **Run the Flask app:**

   ```sh
   python app.py
   ```

   The server will start at `http://localhost:5000`.

3. **Open your browser** and go to [http://localhost:5000](http://localhost:5000).

4. **Fill in the form:**
   - Enter your Sarvam AI API key.
   - Upload an audio file (WAV, MP3, FLAC, AAC, or M4A).
   - Select source and target languages.
   - Specify an output directory (default is a timestamped folder).

5. **Submit the form.**
   - The UI will show progress as your audio is processed.
   - When complete, the output file path will be displayed.

## Output

- Translated audio files are saved in the specified output directory.
- Intermediate chunks and translated chunks are stored in `chunks/` and `translated_chunks/` folders.

## Notes

- Make sure your Sarvam AI API key is valid and has sufficient quota.
- The app uses background threads for processing; you can check progress via the web UI.
- For best results, use clear audio with minimal background noise.

## Project Structure

```
app.py
templates/
    index.html
static/
    style.css
    script.js
uploads/
chunks/
translated_chunks/
output/
```

## License

This project is for educational and research purposes. See Sarvam AI's terms for API usage.

---

**Powered by Sarvam AI**