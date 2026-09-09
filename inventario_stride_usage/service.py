import bentoml
from pathlib import Path

from inventory import load_inventory
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384
DOC_STRIDE = 128

# =============================================================================
# VARIANTE: resposta e consumo na mesma chamada
# =============================================================================
#
# O modelo só consegue ler uma quantidade limitada de pecinhas por vez. O
# serviço divide um contexto maior em janelas de 384 pecinhas e faz a mesma
# pergunta em cada janela. Cada janela nova repete 128 pecinhas da anterior;
# essa repetição é o `DOC_STRIDE` e ajuda a manter inteira uma resposta que
# esteja na borda de duas janelas.
#
# A API expõe uma chamada HTTP. `answer()` chama o pipeline uma vez e acrescenta
# ao resultado um relatório sobre as janelas usadas nessa chamada.
#
# O método `_token_usage()` não chama o modelo. O tokenizer, que transforma
# texto em números compreendidos pelo modelo, apenas repete a divisão em
# janelas para contar o trabalho. A medição não dispara uma segunda inferência.
# `window_count` diz quantas janelas foram criadas, `window_sizes` mostra o
# tamanho de cada uma e `input_tokens` soma esses tamanhos, incluindo pecinhas
# repetidas pelo stride.
#
# O código continua mostrando explicitamente MAX_SEQ_LENGTH e DOC_STRIDE para
# que a relação entre configuração, janelas e consumo fique observável.
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
            # O pipeline usará estas mesmas configurações na inferência.
            max_seq_len=MAX_SEQ_LENGTH,
            doc_stride=DOC_STRIDE,
        )

        inventory_csv = Path(__file__).parent / "context" / "estoque_marketplace.csv"
        self.context = load_inventory(inventory_csv)

    def _token_usage(self, question: str) -> dict:
        """Conta os tokens e as janelas usados por uma pergunta."""
        # A lista de input_ids representa as janelas que o pipeline precisa
        # processar quando o contexto não cabe em uma entrada só.
        tokens = self.tokenizer(
            question,
            self.context,
            truncation="only_second",
            max_length=MAX_SEQ_LENGTH,
            stride=DOC_STRIDE,
            return_overflowing_tokens=True,
        )
        window_sizes = [len(input_ids) for input_ids in tokens["input_ids"]]
        return {
            "model": MODEL_NAME,
            "question_tokens": len(self.tokenizer(question, add_special_tokens=False)["input_ids"]),
            "context_tokens": len(self.tokenizer(self.context, add_special_tokens=False)["input_ids"]),
            "input_tokens": sum(window_sizes),
            "window_count": len(window_sizes),
            "window_sizes": window_sizes,
            "max_seq_length": MAX_SEQ_LENGTH,
            "model_max_length": self.tokenizer.model_max_length,
            "doc_stride": DOC_STRIDE,
        }

    @bentoml.api
    def answer(self, question: str) -> dict:
        """Responde a pergunta e inclui o consumo de tokens no resultado."""
        # O resultado usual do QA é preservado; o relatório entra como uma
        # chave adicional no mesmo JSON.
        result = self.pipeline(question=question, context=self.context)
        return {**result, "token_usage": self._token_usage(question)}


if __name__ == "__main__":
    service = QAService.inner()
    question = "Qual é o preço do Fone de ouvido Bluetooth?"
    print(f"[teste rápido] resultado: {service.answer(question=question)}")
