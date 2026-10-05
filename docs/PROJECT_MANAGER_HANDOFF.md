# JARVIS - Handoff de Proyecto para Nueva IA

**Actualizado:** 2026-10-04  
**Estado:** Prototipo ejecutable. El navegador abrió correctamente y Whisper funciona en CUDA, pero el usuario aún reporta falsos descartes de wake word, demoras variables y respuestas incoherentes. No declarar resuelto el audio real hasta instrumentar/probar el micrófono.

> Este handoff complementa [PROJECT_CONTEXT.md](PROJECT_CONTEXT.md), que contiene la arquitectura vigente. Las secciones de cronología más abajo son históricas; cuando contradigan este resumen, prevalece este resumen y el código actual.

## Objetivo Para La Nueva IA

Investigar y corregir la experiencia real de voz con evidencia, no seguir agregando aliases al azar. Separar cuatro etapas: captura/segmentación del micrófono, transcripción y wake word, selección/generación de respuesta, y TTS. Añadir tiempos/ruta/provider a eventos visibles para identificar exactamente dónde se gastan 3–19 segundos. El usuario quiere hablar naturalmente en español e inglés, recibir respuestas coherentes y controlar aplicaciones; el navegador ya se abrió una vez.

## Entorno Verificado

- Windows, Python 3.13.7 en `.venv`; el proyecto conserva compatibilidad objetivo Python 3.10+.
- Ejecutar desde la raíz: `$env:PYTHONPATH = "src"; .\.venv\Scripts\python.exe -m jarvis.app`.
- `faster-whisper` 1.2.1; Whisper `base`, CTranslate2 ve 1 GPU y `AudioEngine._get_whisper_model()` se verificó en `cuda`/`float16` (cargas observadas 1.3–5.1 s).
- `nvidia-cublas-cu12` 12.9.2.10 y `nvidia-cudnn-cu12` 9.27.0.42 instalados en `.venv`; DLL bajo `site-packages/nvidia/*/bin`, registradas con `os.add_dll_directory`.
- Ollama responde; `llama3.1:8b` está instalado. `ollama ps` reportó el modelo residente al 100% GPU, contexto 4096.
- Gemini usa `google-genai`, modelo default `gemini-3.8-flash`, timeout 10 s, sin retry automático. Se observó HTTP 503 por alta demanda.
- `pyttsx3` está instalado y es el TTS actual por defecto. `JARVIS_CLOUD_TTS=1` reactiva edge-tts.
- `.env` se encontró anteriormente bajo `src/.env`; `app.py` busca raíz y luego `src/.env`. `.gitignore` ignora `.env`. Nunca imprimir, copiar ni incluir la clave en handoff; hubo una exposición anterior y se recomienda rotarla.
- `python -m compileall -q src` y `pip check` pasaron en verificaciones recientes. No hay suite automatizada visible en el árbol actual; las pruebas previas fueron inline con mocks.

## Árbol Actual

```text
JARVIS/
	.github/
	.gitignore
	.venv/                         # entorno, no versionar
	README.md
	requirements.txt
	docs/
		PROJECT_CONTEXT.md           # contexto técnico vigente
		PROJECT_MANAGER_HANDOFF.md   # este archivo; logs y estado para transferencia
	ollama/                        # carpeta actualmente vacía
	src/jarvis/
		__init__.py
		app.py                       # carga dotenv; arranque CTk
		audio_engine.py              # audio worker, ASR, wake, TTS y eventos
		gui.py                       # UI, permisos y polling de queue con after()
		orchestrator.py              # fast intents, Ollama, Gemini y fallback
		skills/
			__init__.py
			system_ops.py              # start allowlisted + pyautogui.typewrite
			vision.py                  # captura Pillow en BytesIO y Gemini
```

## Hallazgos En Logs

| Síntoma | Evidencia del usuario | Lectura correcta |
|---|---|---|
| Falsos descartes de voz/wake | Estados “no detectó voz” o “no se detectó Jarvis”; idioma reportado `en`, `de`, `pl`, `fr` incluso en intentos en español; RMS desde -34 hasta -94 dBFS | El modelo recibe clips, pero parte son silencio/nivel bajo y parte se transcribe mal. No está demostrado que sea solamente el umbral ni solamente Whisper; falta identificar índice de micrófono y revisar waveform por segmento. |
| Reconoce wake pero pierde petición | Log 14:24 detectó `Jarvis` aislado; el usuario apagó 3 s después. Otro log dio wake-only y luego petición en segmento separado. | Existe ventana de continuación de 8 s con acuse; se probó con worker simulado, no con hardware. |
| Variantes fonéticas y repeticiones | Whisper emitió `Narvis`, `Llarbis, Ybis, Llarbis`, `Yarbis`, `Lervis`, `Arvís` | El matcher acepta aproximaciones y quita todos los wake tokens. Se eliminó el sesgo de aliases múltiples como hotwords; solo la pasada de recuperación usa `Jarvis`. |
| Respuestas lentas | Orquestador: 3.0–19.0 s y hasta 12.6 s; previamente TTS 19.1 s con edge-tts | La voz posterior en los logs nuevos baja a 0.2–2.4 s con pyttsx3. El orquestador aún puede hacer dos llamadas secuenciales a `llama3.1:8b` (clasificación + generación). La UI no expone la ruta/provider, así que el origen de cada demora aún no está probado. |
| Respuestas incoherentes | `Ablame` -> pidió contexto del supuesto término; `que ahora es` -> “El momento de la verdad”; pregunta sobre qué es JARVIS -> afirmó ser un modelo open-source | ASR corrupta y generación sin validación; también se debe evitar presentar auto-descripciones del modelo como hechos. |
| Fallo cloud sin respuesta | `503 UNAVAILABLE`, mensaje de Gemini “currently experiencing high demand” | Se implementó timeout 10 s y fallback Ollama; esto está probado con excepción simulada, todavía no con una caída real de Gemini. |
| Acción de navegador | El usuario confirma “sí logró abrir el navegador”; log mostró “Navegador abierto.” | Éxito comprobado del fast path y del permiso Navegación. No romperlo al refactorizar. |

## Log Completo Más Reciente Del Usuario

Transcripción literal del bloque enviado para el turno 15:50–15:55 del 2026-10-04. Se conserva para que la siguiente IA vea tanto éxitos como fallos:

```text
[15:50:58] Interfaz iniciada. El motor de audio está apagado.
[15:51:12] Encendiendo asistente...
[15:51:12] Cargando modelo local Whisper (base) en CUDA...
[15:51:14] Whisper cargado en 1.3 s (cuda); se reutilizará mientras la app esté abierta.
[15:51:14] Preparando micrófono...
[15:51:16] Sistema en línea. Escuchando...
[15:51:18] Transcribiendo audio localmente...
[15:51:19] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:51:20] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: en; nivel de entrada -45 dBFS); sigo escuchando.
[15:51:26] Transcribiendo audio localmente...
[15:51:26] Whisper transcribió en 0.4 s.
[15:51:26] Narvis
[15:51:29] Sistema en línea. Wake word detectado; di tu solicitud en los próximos 8 segundos.
[15:51:35] Transcribiendo audio localmente...
[15:51:36] Sistema en línea. Wake word detectado; procesando la frase siguiente.
[15:51:36] Whisper transcribió en 0.5 s.
[15:51:36] Lervis como estás.
[15:51:36] Enrutando solicitud...
[15:51:40] El orquestador respondió en 4.0 s.
[15:51:40] Estoy bien, gracias.
[15:51:40] Generando respuesta de voz...
[15:51:40] Síntesis y reproducción de voz: 0.2 s.
[15:51:40] Sistema en línea. Escuchando...
[15:51:51] Transcribiendo audio localmente...
[15:51:52] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: es; nivel de entrada -36 dBFS); sigo escuchando.
[15:51:56] Transcribiendo audio localmente...
[15:51:57] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:51:57] Whisper transcribió en 0.6 s.
[15:51:57] Jarvis Ablame.
[15:51:57] Enrutando solicitud...
[15:52:15] El orquestador respondió en 18.5 s.
[15:52:15] Lo siento, pero no entiendo a qué te refieres con "Ablame". ¿Podrías proporcionar más contexto o explicar qué significa?
[15:52:15] Generando respuesta de voz...
[15:52:15] Síntesis y reproducción de voz: 0.2 s.
[15:52:15] Sistema en línea. Escuchando...
[15:52:20] Transcribiendo audio localmente...
[15:52:21] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:52:21] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -74 dBFS); sigo escuchando.
[15:52:31] Transcribiendo audio localmente...
[15:52:32] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:52:33] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: en; nivel de entrada -45 dBFS); sigo escuchando.
[15:52:39] Transcribiendo audio localmente...
[15:52:39] Whisper transcribió en 0.5 s.
[15:52:39] Jarvis, oblamy.
[15:52:39] Enrutando solicitud...
[15:52:47] El orquestador respondió en 8.0 s.
[15:52:47] Dígame, señor, estoy a su completa disposición.
[15:52:47] Generando respuesta de voz...
[15:52:47] Síntesis y reproducción de voz: 0.2 s.
[15:52:47] Sistema en línea. Escuchando...
[15:52:52] Transcribiendo audio localmente...
[15:52:52] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:52:55] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: en; nivel de entrada -39 dBFS); sigo escuchando.
[15:52:57] Transcribiendo audio localmente...
[15:52:58] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:52:58] Whisper transcribió en 0.9 s.
[15:52:58] Arvís a hablarme.
[15:52:58] Enrutando solicitud...
[15:53:01] El orquestador respondió en 3.2 s.
[15:53:01] ¡Claro! ¿En qué puedo ayudarte hoy?
[15:53:01] Generando respuesta de voz...
[15:53:01] Síntesis y reproducción de voz: 0.2 s.
[15:53:01] Sistema en línea. Escuchando...
[15:53:14] Transcribiendo audio localmente...
[15:53:15] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: es; nivel de entrada -35 dBFS); sigo escuchando.
[15:53:23] Transcribiendo audio localmente...
[15:53:24] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:53:24] Whisper transcribió en 0.7 s.
[15:53:24] Jarvis puedes ejecutar un comando sencillo.
[15:53:24] Enrutando solicitud...
[15:53:27] El orquestador respondió en 3.1 s.
[15:53:27] Navegador abierto.
[15:53:27] Generando respuesta de voz...
[15:53:27] Síntesis y reproducción de voz: 0.2 s.
[15:53:27] Sistema en línea. Escuchando...
[15:53:32] Transcribiendo audio localmente...
[15:53:33] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:53:34] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -41 dBFS); sigo escuchando.
[15:53:40] Transcribiendo audio localmente...
[15:53:40] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:53:43] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -49 dBFS); sigo escuchando.
[15:54:08] Transcribiendo audio localmente...
[15:54:08] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:09] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -94 dBFS); sigo escuchando.
[15:54:15] Transcribiendo audio localmente...
[15:54:15] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:15] Whisper transcribió en 0.7 s.
[15:54:15] Jarvis puedes ejecutar otro comando.
[15:54:15] Enrutando solicitud...
[15:54:20] El orquestador respondió en 4.4 s.
[15:54:20] ¡Claro! ¿Qué comando necesitas ejecutar?
[15:54:20] Generando respuesta de voz...
[15:54:20] Síntesis y reproducción de voz: 0.2 s.
[15:54:20] Sistema en línea. Escuchando...
[15:54:27] Transcribiendo audio localmente...
[15:54:27] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:27] Sistema en línea. Frase descartada: no se detectó 'Jarvis' (idioma: en; nivel de entrada -34 dBFS); sigo escuchando.
[15:54:34] Transcribiendo audio localmente...
[15:54:34] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:35] Whisper transcribió en 0.7 s.
[15:54:35] Jarvis, el que quieras, solo quiero saber qué funcionas.
[15:54:35] Enrutando solicitud...
[15:54:47] El orquestador respondió en 12.6 s.
[15:54:47] Soy un modelo de lenguaje de código abierto que puede responder preguntas, proporcionar información y realizar tareas de procesamiento de texto.
[15:54:47] Generando respuesta de voz...
[15:54:47] Síntesis y reproducción de voz: 0.2 s.
[15:54:47] Sistema en línea. Escuchando...
[15:54:51] Transcribiendo audio localmente...
[15:54:52] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:52] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -45 dBFS); sigo escuchando.
[15:54:55] Transcribiendo audio localmente...
[15:54:55] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:56] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -50 dBFS); sigo escuchando.
[15:54:58] Transcribiendo audio localmente...
[15:54:58] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:54:59] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -44 dBFS); sigo escuchando.
[15:55:08] Transcribiendo audio localmente...
[15:55:09] No detecté 'Jarvis' con el filtro normal; reintentando el audio corto.
[15:55:09] Sistema en línea. Whisper no detectó voz (idioma: en; nivel de entrada -93 dBFS); sigo escuchando.
[15:55:14] Apagando asistente; espera a que termine la operación en curso...
[15:55:15] Motor de audio detenido.
```

## Código Importante (Estado Actual)

### ASR y Wake Retry

En `src/jarvis/audio_engine.py`, la pasada normal es automática; clips cortos sin wake match se repiten en español e inglés:

```python
transcription_options = {
		"language": language,
		"vad_filter": not wake_word_retry,
		"beam_size": 3,
		"condition_on_previous_text": False,
		"no_speech_threshold": None if wake_word_retry else 0.6,
		"log_prob_threshold": -2.0 if wake_word_retry else -1.0,
		"hotwords": "Jarvis" if wake_word_retry else None,
}
```

El worker mide duración/nivel RMS, evita guardar audio persistente (usa WAV temporal y lo elimina), y solo enruta después de `_remove_wake_word()`. Las frases sin wake no se muestran como transcripción, pero sí registran motivo/idioma/RMS. Hay ventana de 8 s cuando el wake aparece separado.

### Orquestación

En `src/jarvis/orchestrator.py`, las rutas directas que evitan modelos son check-in (“me escuchas”, “can you hear me”), hora (incluye ASR typo “que ahora es”), frases de apertura permitidas, visión explícita y escritura con permiso. Para el resto se llama `_classify()` a Ollama; ruta local de charla llama luego `_respond_with_ollama()` (dos llamadas seriales). Una ruta nube llama Gemini; `_respond_with_gemini_or_local()` intenta Ollama en caso de error.

Orden de decisión actual (extracto representativo):

```python
check_in = self._detect_check_in(transcript)
if check_in is not None:
	return AssistantResponse(check_in, "local")
local_time = self._detect_time_request(transcript)
if local_time is not None:
	return AssistantResponse(local_time, "local")
decision = self._classify(transcript)
if decision.destino == "nube":
	return self._respond_with_gemini_or_local(transcript)
return AssistantResponse(self._respond_with_ollama(transcript), "local")
```

### Voz

En `AudioEngine._speak()`, `pyttsx3` es el camino por defecto; `JARVIS_CLOUD_TTS=1` opta por edge-tts. En logs posteriores a este cambio se observaron 0.2 s la mayoría de las veces, con una respuesta local de 2.4 s.

```python
use_cloud_voice = os.getenv("JARVIS_CLOUD_TTS", "").strip().lower() in {"1", "true", "yes"}
if source == "gemini" and use_cloud_voice:
	self._speak_cloud(text, stop_event)
else:
	self._speak_local(text)
```

## Sesiones Anteriores (Síntesis De Logs)

- **14:05–14:06:** múltiples capturas terminaban en “Transcribiendo” y volvían a “Escuchando”; sin transcripción visible. El motor no se apagó.
- **14:14:** después de varios descartes apareció una sola transcripción `Jarvis` y nada más; motivó ventana de continuación.
- **14:23:** idiomas detectados `en/de/es/fr` y muchas frases descartadas.
- **14:27:** misma intermitencia; detección de `Jarvis` aislado.
- **14:58:** `Llarbis, Ybis, Llarbis` y `Yarbis, Llarbis, Llarbis` se enviaron a Ollama y produjeron respuestas absurdas sobre nombres antiguos. Causa confirmada: aliases de wake como hotwords y quitar solo el primer token; ambos corregidos.
- **15:43–15:45:** wake funcionó a veces (`Jarvis me escuchas`, `Jarvis que ahora es`); Gemini reportó `503 UNAVAILABLE`/alta demanda. Una pregunta mal transcrita produjo respuesta incoherente. En una versión anterior edge-tts tardó 19.1 s; luego speech cae a 0.2 s tras poner pyttsx3 por defecto.
- **15:50–15:55:** log completo arriba. Confirma descartes repetidos pero también reconocimiento, respuesta inmediata “Sí, te escucho”, apertura del navegador, comandos escuchados, respuestas absurdas, y demoras 3.1–18.5 s del orquestador.

## Próximo Diagnóstico Recomendado

1. Añadir eventos estructurados visibles: `language`, duración del clip, RMS, resultado normal/retry, texto reconocido tras wake, ruta (fast/Ollama/Gemini), tiempos separados de clasificación y generación, fuente de respuesta, fallback/error y motor TTS. No enviar frases descartadas al log.
2. Verificar índice/dispositivo de entrada real (`sr.Microphone.list_microphone_names()`), frecuencia/canales y audio RMS por captura. RMS -90 dBFS se parece a silencio; -34 dBFS puede ser voz usable según micrófono. No cambiar threshold sin ver captura y `energy_threshold` después de calibrar.
3. Medir separadamente primera llamada de Ollama (clasificación) y segunda llamada (generación). Considerar atajo determinista para intents frecuentes, una sola llamada para clase+respuesta o modelo local menor, con prueba de calidad y seguridad. Ollama `llama3.1:8b` ha tardado 13.4 s en frío y 6.64 s caliente en una medición anterior.
4. Probar en host real: “Jarvis, me escuchas”, “Jarvis, ¿qué hora es?”, “Jarvis, abre el navegador” con permiso Navegación activo; navegador ya está confirmado como exitoso.
5. Simular 503/timeout de Gemini y verificar que el fallback Ollama sí se reproduce por pyttsx3, no solo comprobar el valor retornado.
6. No diagnosticar una respuesta incoherente sin guardar la transcripción reconocida: diferenciar ASR corrupta de salida del LLM. En la UI de usuario sí aparecen transcripciones con wake word; las descartadas no.

## Límites De Seguridad Y Datos

- No incluir `.env`, API keys, capturas ni WAV de micrófono en commits/handoffs.
- Gemini recibe consultas complejas y capturas explícitas de pantalla. La imagen de visión es in-memory, pero sí se transmite al servicio.
- Navegador requiere switch Navegación; Notepad/Explorer/tecleo requieren Comandos. El sistema no debe aceptar shell libre generado por LLM.
- La clave Gemini fue expuesta anteriormente en un historial; rotarla si no se ha hecho. No imprimir su valor durante diagnóstico.

## Actualización de arquitectura (2026-10-03)

- Ollama ahora clasifica acciones con etiquetas cerradas; `src/jarvis/skills/system_ops.py` permite abrir Edge, Bloc de notas y Explorador mediante comandos Windows fijos. No se ejecuta texto libre generado por el modelo.
- Los switches de navegación/comandos son permisos reales, desactivados por defecto. Navegador requiere navegación; Bloc de notas y Explorador requieren comandos.
- `Orchestrator.respond_with_source()` devuelve texto y origen sin romper `respond()`, que sigue entregando texto para compatibilidad.
- `pyttsx3` sintetiza localmente todas las respuestas por defecto; `edge-tts` es opcional vía `JARVIS_CLOUD_TTS=1`. Ambos se ejecutan en el worker de audio, no en el hilo CustomTkinter.
- Actualizar dependencias con `python -m pip install -r requirements.txt`. Validar la sintaxis con `python -m compileall -q src`; se requiere prueba manual en Windows para comprobar las voces SAPI, permisos y apertura de aplicaciones.

## Diagnóstico del entorno (2026-10-04)

- La clave estaba en `src/.env`, pero el punto de entrada solo leía `.env` desde la raíz. `app.py` ahora admite ambas ubicaciones sin imprimir la clave.
- `nvidia-cublas-cu12` y `nvidia-cudnn-cu12` están instalados en `.venv`; sus DLL existen bajo `site-packages/nvidia/*/bin`. `AudioEngine` ahora registra esas carpetas en el buscador de DLL de Windows antes del preflight CUDA.
- Ollama responde y `llama3.1:8b` está instalado. `ctranslate2` detectó una GPU y `AudioEngine._get_whisper_model()` cargó Whisper con `device=cuda` en 4.71 s. Falta validar una ronda de transcripción con micrófono y audio real.
- Los switches de permisos siguen apagados por defecto. Para abrir Bloc de notas hay que activar **Comandos**; para Edge, **Navegación**.
- La clasificación en vivo de “Abre el bloc de notas” tardó 13.40 s con Ollama. Las solicitudes explícitas de abrir aplicaciones ahora usan un fast path determinista de allowlist; las frases ambiguas siguen enrutándose con Ollama.
- Los lanzamientos de Notepad y Explorer usan `start` para que `subprocess.run` no espere a que el usuario cierre la ventana y agote el timeout.

## Sprint 3 (2026-10-04)

- `AudioEngine` calibra el ruido ambiente durante 1.5 s en cada arranque, inicializa energy threshold en 300 y solo enruta transcripciones con wake word; admite variantes fonéticas como `Yarbis` y `Llarbis`. Si Whisper separa el wake word de la petición, acepta la siguiente frase durante 8 s. Whisper autodetecta español/inglés y aplica VAD/filtros de silencio y probabilidad.
- `skills/vision.py` captura una imagen con Pillow en memoria y la envía a Gemini solo ante una petición explícita de pantalla con wake word. No se crea archivo de captura.
- `pyautogui.typewrite()` escribe texto dictado únicamente con el permiso **Comandos** activo. La app y la captura siguen ejecutándose en el worker, no en Tkinter.
- Gemini recibe una instrucción de respuesta en una sola oración breve. Añadidos `pyautogui` y `Pillow` a `requirements.txt`; instalar con `python -m pip install -r requirements.txt`.

## Ajuste bilingüe y diagnóstico de wake word (2026-10-04)

- Los logs de uso mostraban que el worker seguía escuchando, pero descartaba frases antes de enrutarlas; no era un apagado del motor. Se añadieron estados no sensibles para distinguir silencio de falta de wake word, sin imprimir la frase descartada.
- Whisper ahora usa autodetección de idioma; los prompts de Ollama/Gemini y los detectores de acciones/visión/escritura admiten español e inglés. `Jarvis` se normaliza sin acentos antes de comprobarlo.
- Se verificó el caso de Whisper entregando `Jarvis` y `me escuchas` como frases separadas; la segunda ahora se enruta dentro de la ventana de 8 s.
- Un wake word aislado recibe acuse audible; las preguntas “me escuchas” y “can you hear me” responden directamente en el idioma correspondiente sin esperar al clasificador Ollama.
- Para mejorar la detección, Whisper recibe hotwords `Jarvis/Yarbis/Llarbis`, usa beam size 3 y reintenta clips de hasta 5 s sin wake word (incluyendo salida vacía) con idioma forzado `es` y `en`, sin VAD/no-speech suppression. Solo acepta el clip si encuentra el wake word; clips más largos evitan decodificaciones extra. El descarte reporta nivel RMS en dBFS, idioma y motivo, nunca el audio ni el texto.
- Regresión reproducida con `Llarbis, Ybis, Llarbis`: los aliases como hotwords en la pasada normal sesgaban la transcripción y el matcher quitaba solo el primero. La pasada normal ahora no tiene hotwords, el reintento solo usa `Jarvis` y elimina todas las variantes reconocidas; frases compuestas únicamente por aliases no se enrutan a Ollama.
- Logs 15:43-15:45: edge-tts tardó 19.1 s y Gemini devolvió 503 sin respuesta; “qué hora es” se transcribió como “que ahora es”. El habla ahora usa `pyttsx3` offline por defecto (`JARVIS_CLOUD_TTS=1` habilita edge-tts), Gemini tiene timeout 10 s y falla a Ollama local, y preguntas de hora/check-in usan respuestas directas.
- Pendiente: probar frases habladas en ambos idiomas y confirmar en consola el idioma detectado y el reconocimiento del wake word.

## Resumen ejecutivo

La aplicación Windows usa un worker para calibrar/capturar micrófono, Whisper con autodetección español/inglés en CUDA, wake word `Jarvis` y llamadas locales/remotas. Captura pantalla en memoria ante una petición explícita. El navegador se confirmó abierto por el usuario; la detección de wake word y las respuestas generales siguen intermitentes/lentas. Acciones de app y escritura requieren el permiso correspondiente; Tkinter consume eventos desde una cola.

Estado actual verificado: Whisper cargó en CUDA en 1.3–5.1 s; CUDA no es el bloqueo actual. El usuario ha completado rondas de micrófono y habla, pero la transcripción/wake es intermitente, las respuestas del orquestador varían de 3 a 19 s y existen respuestas incoherentes. La voz posterior al cambio a pyttsx3 suele tardar 0.2 s. Una respuesta Gemini falló con HTTP 503; el fallback local está implementado pero solo probado con mocks.

## Alcance implementado

- GUI CustomTkinter oscura con botón de encendido/apagado, consola de eventos y switches de permisos.
- `src/jarvis/app.py`: arranque de la aplicación.
- `src/jarvis/gui.py`: ventana, cola de eventos, estado del asistente y protección contra clics repetidos mientras detiene.
- `src/jarvis/audio_engine.py`: calibración ambiente, wake word, faster-whisper, fallback CUDA/CPU, orquestación y TTS híbrido.
- `src/jarvis/skills/system_ops.py`: apertura allowlisted de aplicaciones y escritura directa bajo permiso explícito.
- `src/jarvis/skills/vision.py`: captura Pillow en memoria y descripción vía Gemini.
- `src/jarvis/orchestrator.py`: clasificación, intents rápidos, respuestas Ollama/Gemini y fallback.
- `requirements.txt`, instrucciones de instalación y documentación de arquitectura/contexto.
- El modelo Whisper se conserva en memoria durante la vida de la app; usa beam size 3 y loguea tiempo de transcripción.
- El audio sin wake word no se muestra ni se enruta. Los permisos de GUI gatean acciones; texto dictado se escribe solo cuando está activo **Comandos**.

## Historial (Hechos Históricos, No Estado Actual)

1. **Scaffolding:** el workspace estaba vacío. Se creó una estructura modular y documentación para futuros colaboradores.
2. **Instalación inicial:** se intentó instalar desde Python 3.14 global; el usuario canceló cuando pip preparaba PyAudio desde fuente.
3. **Entorno aislado:** se creó `.venv` con Python 3.13.7. PyAudio tuvo wheel precompilado y se instalaron los requisitos. Pylance quedó configurado para ese intérprete.
4. **Whisper/CUDA, estado histórico:** faster-whisper reportó `Library cublas64_12.dll is not found or cannot be loaded`; entonces se añadió fallback CPU. Después se instalaron los wheels NVIDIA y se registraron los directorios DLL. Estado actual: CTranslate2 ve una GPU y Whisper carga en `cuda`; no reinstalar CUDA sin nueva evidencia.
5. **Apagado durante inferencia:** el evento `threading.Event` no puede interrumpir una inferencia nativa ya iniciada. Se modificó la GUI para mostrar “Deteniendo…” y desactivar el botón hasta que termine el worker; al volver, se descarta la transcripción pendiente. No existe cancelación inmediata segura de la inferencia.
6. **Cuota Gemini:** los logs del nivel gratuito reportaron primero límite de 5 solicitudes/minuto y luego 20 solicitudes/día para `gemini-3.8-flash`; las consultas devolvieron HTTP 429. Un log posterior todavía mostró el mensaje fatal anterior porque la ventana activa no había recargado el código.
7. **Manejo cloud actual:** Gemini timeout 10 s y sin reintentos; al fallar Ollama se usa como respuesta local. El log reciente mostró HTTP 503 por alta demanda. La ruta de fallback pasó una prueba simulada; falta prueba live.

## Decisiones y dependencias externas

- Se solicitó Gemini 1.5 Pro, pero ese modelo ya no está listado/disponible en Gemini API. El default actual es `gemini-3.8-flash`; puede cambiarse con `GEMINI_MODEL`.
- El cliente Gemini actual usa `google-genai`.
- Gemini requiere internet, una clave válida y cuota/proyecto con acceso. El código no puede eludir límites de API.
- CUDA requiere CUDA 12 cuBLAS y cuDNN 9; ambas DLL cargan en el `.venv` verificado y Whisper ya inicia en GPU.
- pyttsx3 usa voces instaladas en Windows y es el TTS por defecto. edge-tts requiere internet, es opcional, y fue la fuente de una demora previa de 19.1 s.
- Whisper `base` se descarga/carga en la primera activación; las posteriores reutilizan el modelo solo mientras el proceso de la app permanezca abierto.

## Seguridad y privacidad

La clave Gemini fue expuesta previamente en el historial visible y actualmente se carga desde `.env` local (ignorado por Git). No se reproduce aquí. **Acción recomendada:** revocar la clave expuesta, crear otra y mantenerla solo en `.env` o en el entorno local. Las consultas complejas y las capturas de pantalla solicitadas explícitamente se envían a Gemini; informar al usuario antes de habilitar el flujo de visión.

## Verificación realizada

- `python -m compileall -q src`: pasó en el entorno virtual después de los cambios.
- Imports de dependencias/aplicación: pasaron en `.venv`.
- Pruebas simuladas: caché/configuración CUDA, fallback CPU, cancelación posterior a inferencia, timeout y tratamiento recuperable de HTTP 429.
- Logs de usuario: el micrófono completó rondas y produjo respuestas habladas; algunas capturas se descartaron y algunas transcripciones fueron corruptas. El usuario confirma que el navegador se abrió.
- Verificación Sprint 3: calibración/wake-word y acciones de visión/escritura probadas con periféricos, pantalla y API simulados; las dos dependencias nuevas están instaladas en `.venv`.
- **Pendiente:** medir dispositivo/waveform real, instrumentar provider/tiempos internos, mejorar latencia/calidad Ollama, probar fallback 503 contra servicio real y validar wake word ES/EN sin mocks.

## Bloqueos y acciones recomendadas

| Prioridad | Acción | Criterio de cierre |
|---|---|---|
| P0 | Revocar la clave expuesta y reemplazarla localmente | La clave anterior deja de ser válida y la nueva no aparece en repositorio, chat ni historial compartido |
| P1 | Añadir logs de provider y tiempos por etapa | Por solicitud se identifica fast path/Ollama/Gemini, clasificación, generación, fallback y TTS |
| P1 | Confirmar micrófono real y su waveform | Índice de dispositivo conocido y energía/nivel de voz comprobados |
| P1 | Reducir latencia y errores del doble llamado Ollama | Medición por stage y evaluación de salida coherente |
| P2 | Validar fallback Gemini 503 en vivo | Respuesta Ollama local se sintetiza con pyttsx3 durante fallo cloud |
| P2 | Validar wake word hablado en español e inglés | Reproducible con el dispositivo del usuario y sin pérdida de la petición |
| P2 | Validar visión y escritura con permisos | Petición de pantalla obtiene respuesta Gemini y texto autorizado aparece en la ventana activa |
| P3 | Añadir tests automatizados de worker/GUI | Pruebas reproducibles para errores API, shutdown y eventos de estado |

## Comando de ejecución local

Desde la raíz del proyecto, con una clave nueva configurada en la sesión local:

```powershell
$env:PYTHONPATH = "src"
.\.venv\Scripts\python.exe -m jarvis.app
```

No pegar la clave en documentación, código, chat ni commits.
