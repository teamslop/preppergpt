# Model Sources

PrepperGPT separates routing from model licensing and distribution.

- Ollama models are pulled by the local Ollama runtime when available.
- Whisper Base STT is installer-cached from `Systran/faster-whisper-base`
  under the local PrepperGPT model directory and mounted into OpenWebUI.
- Hugging Face vision models are downloaded by the local vision sidecar.
- Very large GLM Q8/Q4, Slopcode, and Flux assets are marked as manual or external
  until a license-compatible public download source is configured.

Manual routes are still added to OpenWebUI. They become live when their local
endpoint or files are present.
