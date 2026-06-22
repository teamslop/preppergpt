# PrepperGPT Local Parity Map

PrepperGPT packages the local ChatGPT-like stack around OpenWebUI for resilient
local use when hosted AI services are unavailable:

- OpenWebUI UI at `http://127.0.0.1:8080`
- Ollama fast local models at `http://127.0.0.1:11434`
- Optional GLM 5.2 Q8 route at `http://127.0.0.1:11446/v1`
- Optional GLM 5.2 Q4 route at `http://127.0.0.1:11441/v1`
- Optional Slopcode/Qwen route at `http://127.0.0.1:11438/v1`
- Deep research sidecar at `http://127.0.0.1:18041/v1`
- Local scheduler connector at `http://127.0.0.1:18042`
- Local agent and auto-router at `http://127.0.0.1:18043/v1`
- Local vision sidecar at `http://127.0.0.1:18044/v1`
- SearXNG, Tika, Jupyter, and ComfyUI support services

The local goal is functional local parity for common ChatGPT workflows, not
hosted frontier-model quality or cloud account continuity.
