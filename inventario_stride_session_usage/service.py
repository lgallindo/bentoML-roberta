import bentoml
from io import BytesIO
from pathlib import Path
from statistics import mean, median, pstdev

import matplotlib.pyplot as plt
from PIL import Image
from inventory import load_inventory
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"
MAX_SEQ_LENGTH = 384
DOC_STRIDE = 128

# =============================================================================
# VARIANTE COM MÉTRICAS ACUMULADAS NA SESSÃO
# =============================================================================
#
# O modelo lê 384 pecinhas por janela. Para cobrir um contexto maior, uma nova
# janela repete 128 pecinhas da anterior; essa repetição é o `DOC_STRIDE`.
# Cada instância do serviço mantém as métricas das chamadas recebidas por ela.
# Aqui, "sessão" significa a vida do processo: reiniciar o servidor zera os
# valores e criar várias réplicas cria um acumulado independente por réplica.
#
# `answer()` continua fazendo uma única inferência. O tokenizer, que transforma
# texto em números para o modelo, conta as janelas; depois o serviço guarda o
# score e o total de tokens daquela requisição. O novo
# endpoint apenas calcula estatísticas sobre os valores já guardados.
#
# Para tokens, usamos `input_tokens`: a soma dos tokens de todas as janelas que
# o modelo processou naquela chamada, incluindo a repetição causada por
# DOC_STRIDE. A estatística em `tokens` descreve cada requisição, enquanto
# `cumulative_tokens` é o total processado desde o início da sessão.
# `confidence_scores` descreve os números que o modelo atribuiu às respostas;
# esse número não garante que uma resposta esteja correta.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo, o tokenizer, o contexto e os acumuladores."""
        self.model = AutoModelForQuestionAnswering.from_pretrained(MODEL_NAME)
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.pipeline = pipeline(
            "question-answering",
            model=self.model,
            tokenizer=self.tokenizer,
            handle_impossible_answer=True,
            max_seq_len=MAX_SEQ_LENGTH,
            doc_stride=DOC_STRIDE,
        )

        inventory_csv = Path(__file__).parent / "context" / "estoque_marketplace.csv"
        self.context = load_inventory(inventory_csv)
        self.confidence_scores = []
        self.input_tokens = []

    def _token_usage(self, question: str) -> dict:
        """Conta os tokens e as janelas usados por uma pergunta."""
        # O tokenizer transforma texto em números e cria uma lista de janelas.
        # As 128 pecinhas compartilhadas entre janelas entram na soma de novo.
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

    def _descriptive_statistics(self, values: list[int | float]) -> dict:
        """Calcula estatísticas descritivas para uma série numérica."""
        # Sem nenhuma pergunta respondida ainda, a lista está vazia -- e
        # `mean([])` e `min([])` levantam exceção. Quem sobe o servidor e
        # chama /session-metrics ANTES de /answer receberia um erro 500 sem
        # explicação. Devolver a série vazia mantém o formato do JSON e diz a
        # verdade: contagem zero, nada medido ainda.
        if not values:
            return {
                "count": 0,
                "mean": None,
                "median": None,
                "min": None,
                "max": None,
                "stdev": None,
            }
        return {
            "count": len(values),
            "mean": mean(values),
            "median": median(values),
            "min": min(values),
            "max": max(values),
            "stdev": pstdev(values),
        }

    @bentoml.api
    def answer(self, question: str) -> dict:
        """Responde, registra score e tokens, e devolve o consumo da chamada."""
        result = self.pipeline(question=question, context=self.context)
        token_usage = self._token_usage(question)
        self.confidence_scores.append(result["score"])
        self.input_tokens.append(token_usage["input_tokens"])
        return {**result, "token_usage": token_usage}

    @bentoml.api(route="/session-metrics")
    def session_metrics(self) -> dict:
        """Retorna métricas acumuladas desde a inicialização do serviço."""
        return {
            "model": MODEL_NAME,
            "request_count": len(self.confidence_scores),
            "cumulative_tokens": sum(self.input_tokens),
            "confidence_scores": self._descriptive_statistics(self.confidence_scores),
            "tokens": self._descriptive_statistics(self.input_tokens),
            "max_seq_length": MAX_SEQ_LENGTH,
            "doc_stride": DOC_STRIDE,
        }

    @bentoml.api(route="/score-histogram")
    def score_histogram(self) -> Image.Image:
        """Gera um PNG com a distribuição dos scores acumulados."""
        figure, axis = plt.subplots()
        axis.hist(self.confidence_scores, bins=10, range=(0, 1))
        axis.set_title("Distribuição dos scores de confiança")
        axis.set_xlabel("Score")
        axis.set_ylabel("Quantidade de respostas")
        figure.tight_layout()

        image_buffer = BytesIO()
        figure.savefig(image_buffer, format="png")
        plt.close(figure)
        image_buffer.seek(0)
        return Image.open(image_buffer)


if __name__ == "__main__":
    service = QAService.inner()
    question = "Qual é o preço do Fone de ouvido Bluetooth?"
    print(f"[teste rápido] resultado: {service.answer(question=question)}")
    print(f"[teste rápido] métricas: {service.session_metrics()}")
