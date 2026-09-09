import bentoml
from pathlib import Path

from inventory import load_inventory
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384
DOC_STRIDE = 128

# =============================================================================
# VARIANTE COM doc_stride EXPLÍCITO
# =============================================================================
#
# O modelo lê no máximo MAX_SEQ_LENGTH pecinhas de texto por vez. Quando o
# contexto é maior, o pipeline cria várias janelas e faz uma leitura em cada
# uma delas.
#
# DOC_STRIDE diz quantas pecinhas da janela anterior reaparecem na próxima.
# Essa sobreposição evita perder uma resposta que esteja na borda da janela.
# Portanto, o contexto pode consumir mais tokens no processamento total do que
# a quantidade de tokens de uma única janela.
#
# Esta variante só responde. O acompanhamento dos tokens fica em serviços cujo
# nome termina em `_usage`.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo, o tokenizer e o contexto do estoque."""
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
            # O tamanho da janela e a sobreposição entre janelas são definidos
            # explicitamente para tornar o percurso do contexto reproduzível.
            max_seq_len=MAX_SEQ_LENGTH,
            doc_stride=DOC_STRIDE,
        )

        inventory_csv = Path(__file__).parent / "context" / "estoque_marketplace.csv"
        self.context = load_inventory(inventory_csv)

    @bentoml.api
    def answer(self, question: str) -> dict:
        """Responde uma pergunta usando janelas sobrepostas do contexto."""
        return self.pipeline(question=question, context=self.context)

if __name__ == "__main__":
    service = QAService.inner()
    question = "Qual é o preço do Fone de ouvido Bluetooth?"
    print(f"[teste rápido] resposta: {service.answer(question=question)}")
