import bentoml
from pathlib import Path

from pypdf import PdfReader
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384
DOC_STRIDE = 128

# =============================================================================
# VARIANTE PDF: resposta e consumo na mesma chamada
# =============================================================================
#
# Os PDFs são lidos e convertidos em um contexto único. O modelo lê até 384
# pecinhas por vez; por isso o texto é dividido em janelas. Cada nova janela
# repete 128 pecinhas da anterior. Essa repetição é o `DOC_STRIDE` e permite
# que uma resposta perto da borda apareça completa em outra janela.
#
# A API oferece apenas /answer, que devolve o resultado usual do QA junto com
# `token_usage`, o relatório das janelas usadas nessa pergunta.
#
# O pipeline faz uma inferência em cada janela. `_token_usage()` usa o
# tokenizer, que transforma texto em números, apenas para contar as janelas;
# ele não executa o modelo novamente. `window_count` é a quantidade de janelas,
# `window_sizes` mostra seus tamanhos e `input_tokens` soma o conteúdo delas.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo, o tokenizer e os PDFs como um único contexto."""
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
            # Estes valores precisam coincidir com a contagem de janelas.
            max_seq_len=MAX_SEQ_LENGTH,
            doc_stride=DOC_STRIDE,
        )

        context_dir = Path(__file__).parent / "context"
        pdf_files = sorted(context_dir.glob("*.pdf"))
        self.context = "\n\n".join(
            self._load_pdf_context(pdf_file) for pdf_file in pdf_files
        )

    def _load_pdf_context(self, pdf_path: str | Path) -> str:
        """Extrai e concatena o texto de todas as páginas de um PDF."""
        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() for page in reader.pages]
        return "\n\n".join(page for page in pages if page)

    def _token_usage(self, question: str) -> dict:
        """Conta os tokens e as janelas usados por uma pergunta."""
        # O tokenizer reproduz as mesmas janelas configuradas no pipeline.
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
        # Preserva answer, score, start e end e acrescenta o relatório.
        result = self.pipeline(question=question, context=self.context)
        return {**result, "token_usage": self._token_usage(question)}


if __name__ == "__main__":
    service = QAService.inner()
    question = "O que é o SAC?"
    print(f"[teste rápido] resultado: {service.answer(question=question)}")
