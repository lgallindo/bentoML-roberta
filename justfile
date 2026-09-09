# =============================================================================
# Projeto: 14 serviços BentoML, do QA extrativo mais simples ao chat com UI
#
# Cada variante mora numa pasta independente, na raiz do projeto.
# Todas usam o MESMO ambiente Python (o .venv da raiz), então um único
# `just sync` serve para todas.
#
#   QA extrativo -- o modelo GRIFA um trecho do contexto:
#     basico/        pergunta + contexto vêm na requisição
#     pdf/           contexto = todos os PDFs em context/ (dá errado, de propósito)
#     inventario/    contexto = 25 produtos de um CSV (dá certo)
#     api/           contexto = feriados buscados na BrasilAPI (muda sozinho)
#
#   doc_stride -- como o modelo lê um texto que não cabe nele:
#     inventario_stride/                as janelas explícitas (e já eram o padrão)
#     inventario_stride_usage/          mede uma pergunta: 9 janelas, 3.410 tokens
#     inventario_stride_session_usage/  acumula métricas + histograma da sessão
#     pdf_stride/                       os mesmos PDFs: não conserta o contexto
#     pdf_stride_usage/                 mede o estrago: 40 janelas, 15.182 tokens
#
#   LLM generativo -- o modelo ESCREVE a resposta:
#     falcon90m/       Falcon-H1-Tiny-90M Instruct (~91M)
#     gemma3/          Gemma 3 270M Instruct (gated no HF)
#     falcon90m_apps/  4 sample apps (JSON / rota / template / e-mail)
#     gemma3_gradio/   chat multi-turn, UI Gradio em /ui
#     gemma3_js/       chat multi-turn, HTML/JS em /ui
#
# Como chamar uma receita de uma variante -- o nome da pasta vem primeiro:
#
#     just basico serve            sobe a variante básica
#     just pdf curl-falhas         demonstra o problema da variante de PDF
#     just inventario curl-qa      faz quatro perguntas sobre o estoque
#     just api curl-qa             pergunta sobre feriados vindos de API externa
#     just falcon90m curl-generate gera texto com o Falcon 90M
#     just gemma3 curl-generate    gera texto com o Gemma 3 270M
#     just falcon90m_apps test     roda a suíte das 4 sample apps, sem servidor
#
# Para ver as receitas de uma variante:
#
#     just --list basico
#
# Para rodar duas variantes ao mesmo tempo, mude a porta pelo ambiente:
#
#     just basico serve                 (fica na 3000)
#     PORT=3001 just inventario serve   (vai para a 3001)
# =============================================================================

mod basico 'basico'
mod pdf 'pdf'
mod inventario 'inventario'
mod api 'api'
mod inventario_stride 'inventario_stride'
mod inventario_stride_usage 'inventario_stride_usage'
mod inventario_stride_session_usage 'inventario_stride_session_usage'
mod pdf_stride 'pdf_stride'
mod pdf_stride_usage 'pdf_stride_usage'
mod falcon90m 'falcon90m'
mod gemma3 'gemma3'
mod falcon90m_apps 'falcon90m_apps'
mod gemma3_gradio 'gemma3_gradio'
mod gemma3_js 'gemma3_js'

# Mostra todas as variantes e as receitas gerais
default:
	@just --list

# Instalar/atualizar o .venv a partir do pyproject.toml + uv.lock
sync:
	uv sync --no-active

# Listar todos os bentos já empacotados, de todas as variantes
list:
	uv run --no-active bentoml list

# Ver quais variantes estão de pé e em que portas
ports:
	#!/usr/bin/env bash
	linhas=$(ss -ltnp '( sport >= :3000 and sport <= :3007 ) or sport = :8080' 2>/dev/null | tail -n +2)
	if [ -z "$linhas" ]; then
		echo "Nenhum servidor de pé nas portas 3000-3007 nem 8080."
	else
		echo "Servidores de pé (3000-3007 e/ou 8080):"
		echo "$linhas" | sed 's/^/  /'
	fi

# Derrubar variantes nas portas 3000-3007 e 8080 (serve-open dos LLMs)
stop-all:
	#!/usr/bin/env bash
	encontrou=0
	for porta in 3000 3001 3002 3003 3004 3005 3006 3007 8080; do
		if ss -ltn "sport = :$porta" | grep -q LISTEN; then
			echo "Encerrando o servidor da porta $porta..."
			fuser -k -TERM $porta/tcp >/dev/null 2>&1 || true
			encontrou=1
		fi
	done
	if [ "$encontrou" = "0" ]; then
		echo "Nada para encerrar."
	else
		sleep 2
		echo "Portas liberadas. (Os processos supervisores somem sozinhos em alguns segundos.)"
	fi
