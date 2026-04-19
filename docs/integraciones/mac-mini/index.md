# Mac Mini M4 — Servidor de Inferencia IA

El Mac Mini M4 es el servidor de inferencia compartida para todo el ecosistema GUIA y SciBack. Actúa como "GPU as a service" interno.

## Rol en el ecosistema

- Corre Ollama con backend MLX (ARM64 nativo, muy eficiente)
- Sirve modelos LLM para `sciback-llm-ollama` y embeddings para `sciback-embeddings-e5`
- `guia-node` le hace HTTP calls vía `OLLAMA_BASE_URL`

## Modelos instalados

| Modelo | Uso en GUIA |
|--------|-------------|
| `qwen2.5:3b` | Intent classifier (rápido, liviano) |
| `qwen2.5:7b` | Síntesis RAG en modo LOCAL |
| `deepseek-r1:distill` | Razonamiento complejo |
| `multilingual-e5-large-instruct` | Embeddings multilingüe para pgvector |

## Stack de exposición

```
Mac Mini M4
└── Ollama (puerto 11434, solo localhost)
└── Caddy (reverse proxy con API key)
    └── https://ia.guia.upeu.edu.pe  ← GUIA Node hace HTTP aquí
```

## Variables de entorno en guia-node

```env
OLLAMA_BASE_URL=http://ia.guia.upeu.edu.pe
OLLAMA_API_KEY=...
OLLAMA_DEFAULT_MODEL=qwen2.5:7b
E5_MODEL=multilingual-e5-large-instruct
```

## Principio de separación

El Mac Mini puede apagarse o reemplazarse sin afectar el resto del stack. Cambiar `OLLAMA_BASE_URL` migra la inferencia a cualquier otro servidor con Ollama.

## Estado

⏳ Pendiente setup: instalar Ollama, descargar modelos, configurar Caddy + API key, exponer `ia.guia.upeu.edu.pe`.
