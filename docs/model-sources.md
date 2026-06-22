# Model Sources

PrepperGPT separates routing from model licensing and distribution.

- Ollama models are pulled by the local Ollama runtime when available.
- OpenWebUI STT models are downloaded by OpenWebUI/faster-whisper.
- Hugging Face vision models are downloaded by the local vision sidecar.
- Very large GLM, Slopcode, and Flux assets are marked as manual or external
  until a license-compatible public download source is configured.

Manual routes are still added to OpenWebUI. They become live when their local
endpoint or files are present.
