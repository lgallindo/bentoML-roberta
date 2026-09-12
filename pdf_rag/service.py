import time

import bentoml
from pathlib import Path

from busca import montar_indice
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
TRECHOS_PADRAO = 6

# =============================================================================
# VARIANTE PDF + RAG -- a etapa de BUSCA que faltava na variante pdf/
# =============================================================================
#
# Esta pasta usa os MESMOS DOIS PDFs e o MESMO MODELO da variante pdf/. Não
# trocamos de modelo, não aumentamos a máquina, não afinamos nada. A única
# diferença é que alguém ESCOLHE os pedaços certos do texto antes de chamar o
# modelo -- e é só isso que separa errar em 18 segundos de acertar em 1.
#
# O comentário no topo de pdf/service.py termina assim:
#
#     "O QUE ESTÁ FALTANDO: alguém precisa ESCOLHER o pedaço certo do texto
#      ANTES de chamar o modelo (...) Esse passo que falta tem nome: é a
#      'busca' (retrieval) do RAG."
#
# Esta pasta é aquele parágrafo virando código. O trabalho todo mora em
# busca.py, que não usa nenhuma biblioteca nova: é BM25 escrito à mão com a
# biblioteca padrão do Python.
#
# MEDIDO NESTA VARIANTE (CPU, 173 trechos indexados em ~0,6 s na subida):
#
#   "Qual é o prazo para resposta de reclamação no SAC?"
#       pdf/  -> ""  (vazio), em 15-19 s -- não achou, apesar de estar escrito
#       aqui  -> "sete dias corridos" (score 0,47) em ~0,8 s, citando
#               DECRETO_11034_2022.pdf p.3, Art. 13
#
#   "Quantos dias tem o consumidor para cancelar o serviço?"
#       pdf/  -> "DIA DAS CRIANÇAS E NATAL," -- um trecho da apostila do Sebrae
#       aqui  -> ""  (vazio)
#
#       O vazio aqui é a resposta CERTA, e vale parar nele. O Decreto não dá
#       prazo nenhum para cancelamento: o Art. 14 manda fazer o "processamento
#       imediato do pedido de cancelamento". Não existem "quantos dias". A
#       pergunta pressupõe um prazo que o documento não tem, e as duas
#       variantes reagem de formas opostas -- a pdf/ inventa uma resposta
#       tirada de um texto sobre outro assunto, e esta admite que não sabe.
#
#   "Qual é a capital da França?"
#       aqui  -> ""  (vazio), sem nem chamar o modelo: nenhuma palavra da
#               pergunta aparece em nenhum trecho, então a busca devolve lista
#               vazia e não há o que perguntar.
#
# POR QUE UM PIPELINE POR TRECHO, EM VEZ DE COLAR OS TRECHOS
#
# A primeira versão desta pasta colava os k melhores trechos num contexto só e
# fazia UMA chamada ao modelo. Não funcionou: com `handle_impossible_answer`
# ligado, quanto maior o contexto, mais a "resposta vazia" ganhava dos grifos
# de verdade. Medido no mesmo trecho do Art. 13:
#
#     600 letras de contexto -> "sete dias corridos"  (0,32)
#     768 letras de contexto -> ""                    (vazio ganha com 0,42)
#
# Então aqui o modelo é chamado UMA VEZ POR TRECHO, e no fim comparamos os
# grifos. Cada chamada enxerga um texto curto, onde a resposta vazia não tem
# vantagem artificial. São 6 chamadas rápidas em vez de 1 chamada grande --
# e, principalmente, em vez das ~100 janelas que a variante pdf/ arrasta.
#
# É a mesma ideia da série `*_stride`, com uma diferença que é o ponto todo:
# lá as ~100 janelas passeiam pelo documento INTEIRO; aqui as 6 chamadas só
# olham o que a busca já escolheu.
#
# O QUE ESTA VARIANTE **NÃO** RESOLVE
#
# A busca é por PALAVRA. Se a pergunta usa uma palavra e o documento usa outra
# para a mesma coisa, o BM25 não faz a ponte. O caso está vivo aqui dentro:
# a pergunta diz "resposta de reclamação" e o Art. 13 diz "as demandas serão
# respondidas". Para o BM25, "resposta" e "respondidas" são palavras
# diferentes, e o trecho certo cai para a SEXTA posição do ranking. Só
# funciona porque pegamos os 6 primeiros, não o primeiro.
#
# Diminua para `trechos=3` e a resposta some. Esse é o buraco que os
# *embeddings* fecham, e é o assunto da próxima variante.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo e INDEXA os PDFs (a parte cara acontece aqui)."""
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
        )

        inicio = time.perf_counter()
        self.indice = montar_indice(Path(__file__).parent / "context")
        demora = time.perf_counter() - inicio

        letras = sum(len(t["texto"]) for t in self.indice.trechos)
        medio = letras // max(1, len(self.indice))
        print(
            f"[índice] {len(self.indice)} trechos, {letras} caracteres "
            f"(média de {medio} por trecho), montado em {demora:.2f}s"
        )
        print(
            "[índice] a variante pdf/ manda estas mesmas letras INTEIRAS para o "
            "modelo a cada pergunta; aqui mandamos só os melhores trechos."
        )

    @bentoml.api
    def answer(self, question: str, trechos: int = TRECHOS_PADRAO) -> dict:
        """Busca os melhores trechos e pergunta ao modelo UM TRECHO POR VEZ.

        Os dois tempos vêm separados de propósito: `busca_ms` e `modelo_ms`.
        A busca custa décimos de milissegundo e o modelo custa centenas -- ver
        os dois lado a lado deixa claro que a etapa que CONSERTOU a variante é
        também, de longe, a mais barata das duas.
        """
        trechos = max(1, min(int(trechos), 12))

        inicio = time.perf_counter()
        encontrados = self.indice.buscar(question, k=trechos)
        busca_ms = (time.perf_counter() - inicio) * 1000

        vazio = {
            "answer": "",
            "score": 0.0,
            "fonte": None,
            "trechos_lidos": 0,
            "candidatos": [],
            "busca_ms": round(busca_ms, 2),
            "modelo_ms": 0.0,
        }

        if not encontrados:
            # Nenhuma palavra da pergunta aparece em nenhum trecho. Devolver
            # vazio é melhor que mandar o PDF inteiro para o modelo e deixar
            # ele inventar alguma coisa -- que é o que a variante pdf/ faz.
            return vazio

        inicio = time.perf_counter()
        candidatos = []
        for trecho in encontrados:
            grifo = self.pipeline(question=question, context=trecho["texto"])
            texto = grifo["answer"].strip()
            if texto:
                candidatos.append(
                    {
                        "answer": texto,
                        "score": round(float(grifo["score"]), 4),
                        "documento": trecho["documento"],
                        "pagina": trecho["pagina"],
                        "nota_busca": trecho["nota"],
                    }
                )
        modelo_ms = (time.perf_counter() - inicio) * 1000

        if not candidatos:
            # A busca achou trechos, mas o modelo não grifou nada em nenhum.
            # Isso é diferente do caso acima, e a rota /search mostra por quê.
            return {**vazio, "trechos_lidos": len(encontrados), "modelo_ms": round(modelo_ms, 1)}

        candidatos.sort(key=lambda c: -c["score"])
        melhor = candidatos[0]
        return {
            "answer": melhor["answer"],
            "score": melhor["score"],
            "fonte": {
                "documento": melhor["documento"],
                "pagina": melhor["pagina"],
                "nota_busca": melhor["nota_busca"],
            },
            "trechos_lidos": len(encontrados),
            "candidatos": candidatos,
            "busca_ms": round(busca_ms, 2),
            "modelo_ms": round(modelo_ms, 1),
        }

    @bentoml.api
    def search(self, question: str, trechos: int = TRECHOS_PADRAO) -> dict:
        """Só a BUSCA, sem o modelo -- para ver o que o RAG entregaria.

        Existe para diagnóstico, e é a rota mais útil desta pasta quando algo
        dá errado. Quando a resposta vier ruim, esta rota diz de quem é a
        culpa: se o trecho certo NÃO aparece aqui, o problema é da busca; se
        aparece e o modelo errou mesmo assim, o problema é do modelo. São dois
        consertos diferentes, e confundir os dois custa dias.
        """
        trechos = max(1, min(int(trechos), 12))
        inicio = time.perf_counter()
        encontrados = self.indice.buscar(question, k=trechos)
        busca_ms = (time.perf_counter() - inicio) * 1000
        return {
            "trechos": encontrados,
            "total_indexado": len(self.indice),
            "busca_ms": round(busca_ms, 2),
        }


if __name__ == "__main__":
    # Teste rápido sem servidor. Compare os tempos com os da variante pdf/,
    # que leva de 15 a 19 segundos POR PERGUNTA.
    service = QAService.inner()

    perguntas = [
        "Qual é o prazo para resposta de reclamação no SAC?",
        "Quantos dias tem o consumidor para cancelar o serviço?",
        "O que é o SAC?",
        "Qual é a capital da França?",
    ]
    print(f"\n[teste rápido] modelo: {MODEL_NAME}\n")
    for pergunta in perguntas:
        r = service.answer(question=pergunta)
        fonte = r["fonte"]
        onde = f"{fonte['documento']} p.{fonte['pagina']}" if fonte else "-"
        print(f"  P: {pergunta}")
        print(f"  R: {r['answer']!r}  (score {r['score']})")
        print(
            f"     {r['trechos_lidos']} trechos lidos | busca {r['busca_ms']} ms | "
            f"modelo {r['modelo_ms']} ms | fonte: {onde}"
        )
        print()
