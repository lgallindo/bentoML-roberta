import bentoml
from pathlib import Path

from pypdf import PdfReader
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384
DOC_STRIDE = 128

# =============================================================================
# VARIANTE PDF COM doc_stride EXPLÍCITO
# =============================================================================
#
# O contexto contém dois PDFs completos. O modelo lê no máximo
# MAX_SEQ_LENGTH pecinhas por vez, então o pipeline divide o texto em janelas.
# Esta variante declara explicitamente o tamanho e a sobreposição dessas
# janelas.
#
# MAX_SEQ_LENGTH limita cada janela a 384 pecinhas. DOC_STRIDE faz a próxima
# janela repetir 128 pecinhas da anterior. Assim, uma resposta na borda pode
# aparecer inteira em alguma janela, mas a repetição aumenta o total lido.
#
# Esta variante só responde. O acompanhamento dos tokens fica em serviços cujo
# nome termina em `_usage`.
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
            # O tamanho da janela e a sobreposição entre janelas são definidos
            # explicitamente para tornar o percurso dos PDFs reproduzível.
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

    @bentoml.api
    def answer(self, question: str) -> dict:
        """Responde uma pergunta usando janelas sobrepostas do contexto."""
        return self.pipeline(question=question, context=self.context)


if __name__ == "__main__":
    service = QAService.inner()
    question = "O que é o SAC?"
    print(f"[teste rápido] resposta: {service.answer(question=question)}")
