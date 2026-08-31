# =============================================================================
# Receitas compartilhadas pelas três variantes.
#
# Cada pasta em variantes/ tem seu próprio justfile, que começa com
#     import '../comum.just'
# e acrescenta só as receitas de curl próprias da sua API. Tudo que é igual
# nas três (subir, parar, empacotar, abrir o Swagger) mora aqui.
#
# O `just` roda cada receita DENTRO da pasta da variante. É por isso que
# `bentoml serve service:QAService` acha o service.py certo e que
# `bentoml build` acha o bentofile.yaml certo, sem ninguém precisar passar
# caminho nenhum.
# =============================================================================

# Porta do servidor. Para rodar mais de uma variante ao mesmo tempo, defina a
# porta no ambiente, ANTES do just:
#     PORT=3001 just pdf serve
PORT := env_var_or_default("PORT", "3000")
BASE_URL := "http://127.0.0.1:" + PORT

# O caminho de importação é o mesmo nas três pastas: cada uma tem o seu
# service.py, com a sua própria classe QAService lá dentro.
SERVICE := "service:QAService"

# ---------------------------------------------------------------------------
# Guarda 1: a porta está livre?
#
# Sem esta guarda, subir uma variante com a porta já ocupada faz o BentoML
# cuspir umas 60 linhas de traceback terminando em
#     OSError: [Errno 98] Address already in use
# e -- pior -- o processo NÃO encerra: o terminal simplesmente trava, e quem
# está aprendendo dá Ctrl+C sem entender o que aconteceu.
# ---------------------------------------------------------------------------
_porta-livre:
	#!/usr/bin/env bash
	if ! ss -ltn "sport = :{{PORT}}" | grep -q LISTEN; then exit 0; fi
	echo ""
	echo "AVISO: a porta {{PORT}} já está ocupada."
	echo ""
	echo "  Causa mais provável: outra variante já está rodando em outro terminal."
	echo ""
	echo "  Quem está usando a porta agora:"
	ss -ltnp "sport = :{{PORT}}" 2>/dev/null | tail -n +2 | sed 's/^/    /'
	echo ""
	echo "  Como resolver (escolha uma):"
	echo "    just stop                  # derruba o servidor da porta {{PORT}}"
	echo "    PORT=3001 just pdf serve   # sobe esta variante em outra porta"
	echo ""
	exit 1

# ---------------------------------------------------------------------------
# Guarda 2: existe servidor respondendo?
#
# As receitas de curl usavam `curl -s ... || true`. Com o servidor desligado,
# elas não imprimiam NADA e ainda assim terminavam com sucesso: o `-s` engolia
# o "Connection refused" e o `|| true` mandava o just fingir que deu certo.
# Quem está aprendendo ficava olhando para um terminal em branco sem nenhuma
# pista do que fazer. Esta guarda transforma aquele silêncio numa instrução.
# ---------------------------------------------------------------------------
_servidor-vivo:
	#!/usr/bin/env bash
	if curl -sf -m 3 -o /dev/null {{BASE_URL}}/readyz; then exit 0; fi
	echo ""
	echo "ERRO: nada está respondendo em {{BASE_URL}}."
	echo ""
	echo "  Abra OUTRO terminal, entre na pasta do projeto e rode:"
	echo "      just basico serve        (ou pdf, ou inventario)"
	echo ""
	echo "  Espere aparecer a linha 'Service QAService initialized'."
	echo "  Na primeira vez demora uns 15 segundos, porque o modelo precisa"
	echo "  ser carregado. Depois volte aqui e repita este comando."
	echo ""
	exit 1

# Subir o servidor desta variante
serve: _porta-livre
	@echo "Subindo a variante {{VARIANTE}} em {{BASE_URL}}"
	BENTOML_LOG_LEVEL=info uv run --no-active bentoml serve {{SERVICE}} --port {{PORT}}

# Derrubar o servidor que estiver ocupando a porta
stop:
	#!/usr/bin/env bash
	if ! ss -ltn "sport = :{{PORT}}" | grep -q LISTEN; then
		echo "Nada rodando na porta {{PORT}}."
		exit 0
	fi
	echo "Encerrando o que estiver na porta {{PORT}}..."
	fuser -k -TERM {{PORT}}/tcp >/dev/null 2>&1 || true
	sleep 2
	if ss -ltn "sport = :{{PORT}}" | grep -q LISTEN; then
		echo "Ainda de pé; mandando SIGKILL."
		fuser -k -KILL {{PORT}}/tcp >/dev/null 2>&1 || true
	fi
	echo "Porta {{PORT}} liberada."

# Empacotar esta variante num bento (usa o bentofile.yaml desta pasta)
build:
	@echo "Empacotando a variante {{VARIANTE}}"
	uv run --no-active bentoml build

# Teste rápido do modelo, sem subir servidor: carrega e faz uma pergunta
run:
	@echo "Teste rápido da variante {{VARIANTE}} (sem servidor, sem porta, sem HTTP)"
	uv run --no-active python service.py

# ---------------------------------------------------------------------------
# POR QUE ESTA RECEITA NÃO CONSEGUE TE DIZER SE DEU CERTO
# (explicação "para quem tem 10 anos")
#
# O `xdg-open` é o mordomo do Linux: você entrega um endereço a ele e ele
# decide qual programa abre aquilo. A última linha da receita termina com três
# pecinhas:
#
#     xdg-open ENDEREÇO  >/dev/null  2>&1  || true
#                        ~~~~~~~~~~  ~~~~     ~~~~~~~
#                            (a)      (b)       (c)
#
#   (a) >/dev/null  joga no lixo tudo que o mordomo FALA de bom.
#   (b) 2>&1        joga no lixo tudo que o mordomo RECLAMA (os erros).
#   (c) || true     manda o just fingir que deu certo, mesmo se o mordomo
#                   tropeçar na escada.
#
# Resultado: num servidor sem navegador, dentro do WSL ou por SSH, o mordomo
# cai duro -- e mesmo assim esta receita imprime a mesma mensagem alegre e
# termina com sucesso. Ela NUNCA falha, o que é o mesmo que dizer que ela
# nunca te avisa de nada.
#
# Por isso o endereço é impresso ANTES da tentativa de abrir: aquele endereço
# na tela é a única parte em que dá para confiar. Se o navegador não abrir
# sozinho, copie e cole.
# ---------------------------------------------------------------------------

# Abrir a documentação interativa (Swagger UI) desta variante no navegador
swagger:
	@echo "Abra a Swagger UI em {{BASE_URL}}/"
	@echo "A especificação OpenAPI em JSON fica em {{BASE_URL}}/docs.json"
	@echo "Tentando abrir no navegador (se nada acontecer, copie o endereço acima)..."
	xdg-open {{BASE_URL}}/ >/dev/null 2>&1 || true
