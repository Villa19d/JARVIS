# JARVIS Workspace Instructions

- Read `docs/PROJECT_CONTEXT.md` before changing architecture or audio behavior.
- Keep the application compatible with Windows and Python 3.10+.
- Tkinter widgets are main-thread-only. Pass background worker events through `queue.Queue`; consume them with `after()` on the UI thread.
- Keep microphone capture, Whisper model loading/inference, edge-tts synthesis, and audio playback off the UI thread.
- Keep imports of heavyweight audio/model dependencies lazy so importing application modules does not activate hardware or load models.
- Use CUDA `float16` for the local faster-whisper model; CUDA/cuDNN runtime libraries must be installed separately from Python packages.
- Read `GEMINI_API_KEY` from the environment; never hardcode API credentials. Keep Gemini requests in the audio worker.
- The permission switches are visual only in Sprint 1. Never execute transcribed text or navigate on its basis.
- Speak the generated Gemini response; log the raw Whisper transcription separately.
- Use `requirements.txt` as the source of runtime dependencies and update `README.md` when setup/run behavior changes.
- Validate Python syntax with `python -m compileall -q src`; hardware workflows require a Windows host with microphone, speakers, and installed dependencies.
