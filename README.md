# JARVIS Desktop Assistant

Windows desktop assistant with a CustomTkinter interface and a background audio pipeline. It automatically detects Spanish or English with faster-whisper, routes requests through Ollama or Gemini, and uses offline `pyttsx3` for speech by default.

## Requirements

- Windows 10 or 11
- Python 3.10 or newer
- A working microphone and speakers/headphones
- Ollama installed and running locally, with the configured model downloaded
- Internet access for Gemini responses and the first faster-whisper model download
- Windows speech voices installed for offline `pyttsx3` synthesis
- NVIDIA GPU with a compatible CUDA/cuDNN runtime for Whisper's CUDA `float16` mode
- A Gemini API key (set as `GEMINI_API_KEY`)

## Setup

From the project root, create and activate a virtual environment, then install dependencies:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

If PowerShell blocks environment activation, use the environment's interpreter directly: `.\.venv\Scripts\python.exe`.

## Run

```powershell
$env:PYTHONPATH = "src"
$env:GEMINI_API_KEY = "<tu-api-key>"
python -m jarvis.app
```

También puedes guardar la clave en `.env` en la raíz del proyecto. Por compatibilidad, la aplicación busca además `src/.env` si no existe el archivo de la raíz; no subas ese archivo al repositorio.

The first activation downloads and loads the `base` Whisper model. It remains cached while the app is open, and transcription uses beam search (`beam_size=3`) to improve recognition. CUDA acceleration requires CUDA 12 cuBLAS (`cublas64_12.dll`) and cuDNN 9 (`cudnn64_9.dll`); the app adds the NVIDIA wheel DLL directories from the active Python environment before checking them. If either library is unavailable, the app logs a warning and uses CPU `int8` instead. Gemini calls have a 10-second timeout and do not retry automatically; if Gemini fails, JARVIS tries Ollama for a local fallback. Gemini requires internet. Speech uses offline `pyttsx3` by default; set `JARVIS_CLOUD_TTS=1` to opt into network-dependent edge-tts for Gemini responses. The console logs timings for model loading, transcription, Gemini, and speech. The default Gemini model is `gemini-3.8-flash`; set `GEMINI_MODEL` to another currently available model to override it. Gemini 1.5 Pro is no longer listed as an available API model. If microphone initialization fails, verify Windows microphone privacy settings and the selected default input device.

Install Ollama separately, start its local service, and download a model such as `llama3.1:8b` with `ollama pull llama3.1:8b`. The application uses Ollama for routing and brief local responses; if it is unavailable, requests fall back to Gemini. Set `OLLAMA_MODEL` or `OLLAMA_HOST` to override the local defaults. Common questions about the current time and whether JARVIS can hear you are answered locally without either model. Whisper automatically detects Spanish or English. Say “Jarvis” (also “Yarbis” or “Llarbis”) before a request; Jarvis acknowledges the wake word and accepts a separately detected follow-up phrase for 8 seconds. Speech without a wake word is discarded, and the console indicates whether voice or the wake word was not detected without logging discarded content. The system-action allowlist can open Microsoft Edge, Notepad, and File Explorer. Enable the corresponding navigation or command switch before requesting an action; the command switch also gates typing into the focused window. A screen description is captured only on an explicit wake-worded request and sent to Gemini; the screenshot is held in memory, not saved. Speech runs offline on the audio worker thread by default.

## Architecture And Known Issues

- The audio loop, CUDA Whisper inference, Gemini request, and speech playback run on a daemon thread; UI updates are polled from a thread-safe queue on Tk's main loop.
- Navigation and command switches are disabled by default and gate the allowlisted app-launch actions; arbitrary transcribed text is never executed.
- Stop requests are honored after any currently blocking microphone or model operation returns.
- Speech uses offline `pyttsx3` by default; cloud `edge-tts` is opt-in with `JARVIS_CLOUD_TTS=1`.
- User logs confirm that wake-word detection and browser launch work intermittently, but ASR misrecognition and Ollama response latency remain open issues. See [docs/PROJECT_MANAGER_HANDOFF.md](docs/PROJECT_MANAGER_HANDOFF.md) for the actual logs, measurements, and handoff instructions.
- See [docs/PROJECT_CONTEXT.md](docs/PROJECT_CONTEXT.md) for the architecture and continuation notes.
