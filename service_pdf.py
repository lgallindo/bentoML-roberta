import bentoml
from pathlib import Path

from pypdf import PdfReader
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        model_name = "deepset/xlm-roberta-base-squad2"
        self.model = AutoModelForQuestionAnswering.from_pretrained(model_name)
        self.tokenizer = AutoTokenizer.from_pretrained(model_name)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True
        )

        cdc_pdf = Path(__file__).parent / "DECRETO_11034_2022.pdf"
        sebrae_pdf = Path(__file__).parent / "7121.pdf"
        self.context = (
            self._load_pdf_context(cdc_pdf) + "\n\n" + self._load_pdf_context(sebrae_pdf)
        )
        print(self.context)

    def _load_pdf_context(self, pdf_path: str | Path) -> str:
        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() for page in reader.pages]
        return "\n\n".join(page for page in pages if page)

    @bentoml.api
    def answer(self, question: str) -> dict:
        return self.pipeline(question=question, context=self.context)
