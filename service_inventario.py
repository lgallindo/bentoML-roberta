import bentoml
from pathlib import Path

from inventario import carregar_estoque
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

        estoque_csv = Path(__file__).parent / "estoque_marketplace.csv"
        self.context = carregar_estoque(estoque_csv)
        print(self.context)

    @bentoml.api
    def answer(self, question: str) -> dict:
        return self.pipeline(question=question, context=self.context)
