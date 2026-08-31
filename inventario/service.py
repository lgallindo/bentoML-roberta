import bentoml
from pathlib import Path

from inventario import carregar_estoque
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"

# =============================================================================
# VARIANTE INVENTÁRIO -- contexto pequeno e arrumado antes de chegar no modelo
# =============================================================================
#
# Esta variante usa o MESMO modelo da variante do PDF, mas responde certo e em
# 2 a 4 segundos, em vez de errar em 15 a 19. A diferença não está no modelo:
# está no tamanho e no formato do contexto.
#
#   variantes/pdf/  -> 43.069 letras de dois documentos colados, sem tratamento
#   aqui            ->  8.355 letras, 25 produtos, cada um em 4 frases curtas
#
# O arquivo inventario.py faz o trabalho pesado: transforma cada linha do CSV
# em frases de português comum, repetindo o nome do produto em TODAS elas. É
# por isso que "Qual é o prazo de envio da Cafeteira elétrica?" funciona -- a
# frase "O prazo de envio de Cafeteira elétrica é de 3 dias úteis." existe
# literalmente dentro do contexto, e o modelo só precisa grifá-la.
#
# Medido nesta variante:
#   "Qual é o preço do Fone de ouvido Bluetooth?"     -> "R$ 189,90"
#   "Quantas unidades ... existem em estoque?"        -> "42"
#   "Qual é o prazo de envio da Cafeteira elétrica?"  -> "3 dias úteis"
#   "Quem vende o Fone de ouvido Bluetooth?"          -> "Som & Cia"
#   "Qual é a capital da França?"                     -> "" (não sei, correto!)
#
# Aquele último caso é importante: com handle_impossible_answer=True o modelo
# tem permissão para devolver resposta vazia em vez de inventar. Um modelo que
# sempre responde alguma coisa é MAIS perigoso que um que admite não saber.
#
# REPARE NA ASSINATURA DE answer(): aqui ela recebe SÓ `question`. O contexto
# já foi carregado na inicialização e mora dentro do serviço, então não faz
# sentido mandá-lo na requisição.
# =============================================================================


def _context_sample(text: str, n: int = 3) -> str:
    """As n primeiras e as n últimas linhas não vazias do contexto.

    Serve para conferir, na inicialização, que o CSV virou prosa do jeito
    esperado, sem despejar os 25 produtos inteiros no log toda vez.
    """
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
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
        )

        estoque_csv = Path(__file__).parent / "context" / "estoque_marketplace.csv"
        self.context = carregar_estoque(estoque_csv)

        line_count = len([l for l in self.context.splitlines() if l.strip()])
        print(
            f"[contexto] {len(self.context)} caracteres em {line_count} linhas "
            f"(CSV convertido em prosa por inventario.py)"
        )
        print(_context_sample(self.context))

    @bentoml.api
    def answer(self, question: str) -> dict:
        return self.pipeline(question=question, context=self.context)


if __name__ == "__main__":
    # Teste rápido sem servidor: carrega o modelo, lê o CSV e faz uma pergunta.
    service = QAService.inner()

    question = "Qual é o preço do Fone de ouvido Bluetooth?"
    print(f"[teste rápido] modelo:   {MODEL_NAME}")
    print(f"[teste rápido] pergunta: {question}")
    print(f"[teste rápido] resposta: {service.answer(question=question)}")
