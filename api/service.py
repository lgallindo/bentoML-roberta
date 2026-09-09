import bentoml

from api import carregar_feriados
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"

# =============================================================================
# VARIANTE API -- o contexto vem de fora, e por isso pode mudar
# =============================================================================
#
# Mesmo modelo das variantes pdf/ e inventario/. A diferença é de novo o
# contexto -- mas desta vez não é o tamanho dele, e sim a PROCEDÊNCIA:
#
#   pdf/          43.069 letras de dois PDFs no disco        -> erra, 15-19 s
#   inventario/    8.355 letras de um CSV no disco           -> acerta, 2-4 s
#   aqui           ~2.900 letras buscadas na BrasilAPI       -> acerta, 2-4 s
#
# As duas primeiras leem arquivo. Esta faz uma chamada HTTP para
# <https://brasilapi.com.br> na inicialização, recebe JSON, e só então monta a
# prosa. O trabalho de conversão é o mesmo de inventario.py; o que muda é que
# agora existe uma dependência externa no caminho.
#
# O QUE ISSO ACRESCENTA, E POR QUE INTERESSA A MLOPS
#
# 1. O serviço pode subir com contexto DIFERENTE em dias diferentes, sem que
#    uma linha de código mude. Pergunte "Quando é o Carnaval?" com
#    FERIADOS_ANO=2026 e com FERIADOS_ANO=2027: mesma pergunta, mesmo modelo,
#    mesmo código, respostas diferentes.
#
# 2. Nenhuma métrica de servidor percebe isso. Chamadas, latência e taxa de
#    erro ficam idênticas quer o contexto esteja correto, velho ou vazio. É o
#    mesmo argumento de ~/bentoml-lai/deriva, agora do lado do dado de entrada.
#
# 3. A dependência externa pode cair. Se a BrasilAPI não responder, api.py usa
#    o cache em context/ e o serviço sobe assim mesmo -- mas AVISA de onde veio
#    o contexto. Serviço que morre na inicialização por causa de terceiro é
#    frágil; serviço que finge que está tudo bem é pior.
#
# MEDIDO NESTA VARIANTE em 2026-09-09 (14 feriados, 2.874 caracteres, CPU):
#
#   "Quando é o Carnaval?"                    -> "16 de fevereiro de 2026"  (0,08)
#   "Quando é o Natal?"                       -> "25 de dezembro de 2026"   (0,06)
#   "Em que dia da semana cai o Natal?"       -> "sexta-feira"              (0,61)
#   "Em que dia da semana cai o Carnaval?"    -> "segunda-feira"            (0,28)
#   "Qual feriado acontece em 7 de setembro?" -> "Independência do Brasil"  (0,19)
#   "Qual é a capital da França?"             -> ""  (não sei, correto!)    (0,96)
#
#   "Quando é o feriado de Tiradentes?"       -> "terça-feira"              (0,52)
#                                                 ^^^^^^^^^^^ ERRADO
#
# A última linha fica aqui de propósito, e vale mais que as outras seis.
# Perguntaram QUANDO e o modelo respondeu um dia da semana: a resposta é do
# TIPO errado. Repare que ele não está mentindo -- Tiradentes de fato cai numa
# terça -- e repare, sobretudo, que o score 0,52 é maior que o das seis
# respostas CERTAS acima. Confiança alta não é sinal de resposta certa, e
# confiança baixa não é sinal de resposta errada.
#
# É por isso que a variante inventario_stride_session_usage/ existe: para ver a
# DISTRIBUIÇÃO dos scores, não um score isolado. E é por isso que monitorar
# modelo é diferente de monitorar servidor -- nenhuma das sete chamadas acima
# gerou erro de HTTP, e a sétima está errada.
# =============================================================================


def _context_sample(text: str, n: int = 3) -> str:
    """As n primeiras e as n últimas linhas não vazias do contexto."""
    lines = [line for line in text.splitlines() if line.strip()]
    if len(lines) <= 2 * n:
        return "\n".join(lines)
    omitted = len(lines) - 2 * n
    return "\n".join(
        lines[:n] + [f"    [... {omitted} linhas omitidas ...]"] + lines[-n:]
    )


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo, o tokenizer e busca o contexto na API externa."""
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
        )

        self.context, self.origem, self.quantidade = carregar_feriados()

        print(
            f"[contexto] {self.quantidade} feriados, {len(self.context)} caracteres "
            f"(JSON convertido em prosa por api.py)"
        )
        print(f"[contexto] origem: {self.origem}")
        print(_context_sample(self.context))

    @bentoml.api
    def answer(self, question: str) -> dict:
        """Responde uma pergunta usando o contexto buscado na API.

        A resposta inclui `origem`, para que quem consome saiba se o contexto
        veio da API agora ou do cache em disco. Sem esse campo não há como
        distinguir uma resposta atual de uma resposta velha.
        """
        resultado = self.pipeline(question=question, context=self.context)
        return {**resultado, "origem": self.origem}


if __name__ == "__main__":
    # Teste rápido sem servidor: carrega o modelo, busca a API e pergunta.
    service = QAService.inner()

    question = "Quando é o Carnaval?"
    print(f"[teste rápido] modelo:   {MODEL_NAME}")
    print(f"[teste rápido] pergunta: {question}")
    print(f"[teste rápido] resposta: {service.answer(question=question)}")
