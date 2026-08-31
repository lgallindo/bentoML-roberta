# =============================================================================
# Projeto: três serviços de perguntas-e-respostas (QA) com BentoML
#
# As três variantes moram na raiz do projeto, em pastas independentes.
# Todas usam o MESMO ambiente Python (o .venv da raiz), então basta um
# `just sync` para as três.
#
#     basico/        pergunta + contexto vêm na requisição
#     pdf/           contexto = todos os PDFs em context/ (dá errado, de propósito)
#     inventario/    contexto = 25 produtos de um CSV (dá certo)
#
# Como chamar uma receita de uma variante -- o nome da pasta vem primeiro:
#
#     just basico serve            sobe a variante básica
#     just pdf curl-falhas         demonstra o problema da variante de PDF
#     just inventario curl-qa      faz quatro perguntas sobre o estoque
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

# Mostra as três variantes e as receitas gerais
default:
	@just --list

# Instalar/atualizar o .venv a partir do pyproject.toml + uv.lock
sync:
	uv sync --no-active

# Listar todos os bentos já empacotados, das três variantes
list:
	uv run --no-active bentoml list

# Ver quais variantes estão de pé e em que portas
ports:
	#!/usr/bin/env bash
	linhas=$(ss -ltnp 'sport >= :3000 and sport <= :3005' 2>/dev/null | tail -n +2)
	if [ -z "$linhas" ]; then
		echo "Nenhum servidor de pé nas portas 3000-3005."
	else
		echo "Servidores de pé nas portas 3000-3005:"
		echo "$linhas" | sed 's/^/  /'
	fi

# Derrubar TODAS as variantes que estiverem de pé nas portas 3000-3005
stop-all:
	#!/usr/bin/env bash
	encontrou=0
	for porta in 3000 3001 3002 3003 3004 3005; do
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
