# Bundles

PrepperGPT keeps npm lightweight but installs small always-on local assets
during setup.

## Whisper Base

`preppergpt install` downloads the MIT-licensed `Systran/faster-whisper-base`
CTranslate2 model into:

```text
~/.preppergpt/data/models/whisper/base
```

OpenWebUI receives:

```text
WHISPER_MODEL=/models/whisper/base
WHISPER_MODEL_DIR=/models/whisper
WHISPER_MODEL_AUTO_UPDATE=False
```

To repair or refresh the bundle:

```bash
preppergpt bundle whisper
preppergpt bundle whisper --force
```

Source: https://huggingface.co/Systran/faster-whisper-base
