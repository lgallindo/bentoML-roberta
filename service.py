import bentoml
from transformers import pipeline


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        self.pipeline = pipeline(
            "question-answering",
            model="pierreguillou/bert-base-cased-squad-v1.1-portuguese"
        )
        # Modelos alternativos
        # "deepset/roberta-base-squad2", apenas inglês, resultados em Português serão no mínimo engraçados
        # "pierreguillou/bert-base-cased-squad-v1.1-portuguese", primeiro experimento com um BERT em Português, resultados razoáveis
        # "deepset/xlm-roberta-base-squad2", pesado mas multilingual e capaz de dizer "não sei"

    @bentoml.api
    def answer(self, question: str, context: str) -> dict:
        return self.pipeline(question=question, context=context)
