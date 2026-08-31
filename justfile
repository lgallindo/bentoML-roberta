# Justfile for BentoML tasks
# SERVICE variable points to the BentoML service declaration in service.py
SERVICE := "service:QAService"
SERVICE_PDF := "service_pdf:QAService"
SERVICE_INVENTARIO := "service_inventario:QAService"

# Default task
default: serve

# Serve the original BentoML service (development)
serve:
	@echo "Serving BentoML service (SERVICE={{SERVICE}})"
	BENTOML_LOG_LEVEL=info uv run --no-active bentoml serve {{SERVICE}}

# Serve the PDF-based variant
serve-pdf:
	@echo "Serving PDF-based BentoML service (SERVICE={{SERVICE_PDF}})"
	BENTOML_LOG_LEVEL=info uv run --no-active bentoml serve {{SERVICE_PDF}}

# Serve the inventory-based variant
serve-inventario:
	@echo "Serving inventory-based BentoML service (SERVICE={{SERVICE_INVENTARIO}})"
	BENTOML_LOG_LEVEL=info uv run --no-active bentoml serve {{SERVICE_INVENTARIO}}

# Build a bento bundle (requires a valid BentoML build configuration)
build:
	@echo "Building Bento bundle"
	uv run --no-active bentoml build

# List Bento artifacts
list:
	uv run --no-active bentoml list

# Install/refresh the local .venv from pyproject.toml + uv.lock
sync:
	uv sync --no-active

# Run the Python module directly (useful for quick debug; may not start Bento server)
run:
	@echo "Running service.py directly"
	uv run --no-active python service.py

# ---------- Documentação: Swagger & curl para o modelo de QA ----------
# Observação: por padrão o `bentoml serve` roda em http://127.0.0.1:3000
# Swagger UI: / (raiz)   |   OpenAPI JSON: /docs.json

# Abrir a Swagger UI (navegador) para inspecionar a API e testar interativamente
swagger:
	@echo "Abra a Swagger UI em http://127.0.0.1:3000/"
	@echo "(rodar 'just serve' em outro terminal se o servidor não estiver ativo)"
	@echo "Tentando abrir no navegador padrão..."
	xdg-open http://127.0.0.1:3000/ >/dev/null 2>&1 || true

# Exemplo curl: consulta direta ao endpoint /answer usando JSON
# Formato do payload (exemplo em pt_BR):
# { "question": "Qual é a cor do céu?", "context": "O céu é geralmente azul durante o dia devido à dispersão da luz." }
curl-qa:
	@echo "Exemplo: consulta QA para deepset/roberta-base-squad2 (endpoint: /answer)"
	@echo "Certifique-se de que o servidor esteja em http://127.0.0.1:3000 (rodar 'just serve')"
	curl -s -X POST \
		-H 'Content-Type: application/json' \
		-d '{"question":"Qual é a cor do céu?","context":"O céu é geralmente azul durante o dia devido à dispersão da luz."}' \
		http://127.0.0.1:3000/answer | jq || true

# Variante: sem jq (raw)
curl-qa-raw:
	@echo "Mesma chamada sem jq (output bruto)"
	curl -s -X POST \
		-H 'Content-Type: application/json' \
		-d '{"question":"Qual é a cor do céu?","context":"O céu é geralmente azul durante o dia devido à dispersão da luz."}' \
		http://127.0.0.1:3000/answer || true

# Exemplo de arquivo JSON para reuso (gera um arquivo tmp/payload.json e usa curl)
curl-qa-file:
	@mkdir -p tmp
	@printf '%s\n' '{"question":"Quem escreveu \"Dom Casmurro\"?","context":"Machado de Assis é um dos maiores escritores brasileiros. Ele escreveu Dom Casmurro em 1899."}' > tmp/payload.json
	@echo "Enviando tmp/payload.json para http://127.0.0.1:3000/answer"
	curl -s -X POST -H 'Content-Type: application/json' --data-binary @tmp/payload.json http://127.0.0.1:3000/answer | jq || true

# Nota: se o endpoint expõe outro path (p.ex. /api/answer), ajuste as URLs acima.
# Para inspecionar a especificação OpenAPI em JSON: curl http://127.0.0.1:3000/docs.json

# ---------------------------------------------------------------------
