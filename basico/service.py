import bentoml
from transformers import pipeline

MODEL_NAME = "pierreguillou/bert-base-cased-squad-v1.1-portuguese"

# =============================================================================
# VARIANTE BÁSICA -- quem pergunta manda o contexto junto
# =============================================================================
#
# Esta é a variante mais simples das três. A cada chamada, você envia DUAS
# coisas: a pergunta e o texto onde a resposta deve ser procurada.
#
#     {"question": "Qual é a cor do céu?", "context": "O céu é azul."}
#
# Como o contexto vem de fora e é curtinho, o modelo responde em menos de um
# segundo e quase sempre acerta -- afinal, você já entregou a página certa
# para ele. As outras duas variantes existem justamente para mostrar o que
# acontece quando o contexto NÃO vem pronto de fora:
#
#     pdf/                   -- contexto gigante e bagunçado (dá errado)
#     inventario/            -- contexto pequeno e organizado (dá certo)
#
# Modelos alternativos para experimentar (troque MODEL_NAME acima):
#   "deepset/roberta-base-squad2"
#       Só entende inglês. Perguntas em português dão respostas no mínimo
#       engraçadas -- vale rodar uma vez só para ver o estrago.
#   "pierreguillou/bert-base-cased-squad-v1.1-portuguese"
#       Primeiro experimento com um BERT treinado em português. Resultados
#       razoáveis. É o padrão desta variante.
#   "deepset/xlm-roberta-base-squad2"
#       Pesado, porém multilíngue e capaz de dizer "não sei" (devolve resposta
#       vazia em vez de inventar). É o modelo usado nas outras duas variantes.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        self.pipeline = pipeline("question-answering", model=MODEL_NAME)

    @bentoml.api
    def answer(self, question: str, context: str) -> dict:
        return self.pipeline(question=question, context=context)


if __name__ == "__main__":
    # -------------------------------------------------------------------
    # É aqui que o `just basico run` cai.
    #
    # Sem este bloco, rodar "python service.py" não fazia ABSOLUTAMENTE nada:
    # o decorador @bentoml.service só registra a classe, e ninguém chegava a
    # criar um objeto dela. O terminal ficava mudo e saía com código 0, dando
    # a falsa impressão de que alguma coisa tinha rodado.
    #
    # QAService.inner é a classe original, de antes do decorador. Criar o
    # objeto na mão carrega o modelo e permite fazer uma pergunta SEM subir
    # servidor nenhum. É o teste mais rápido para responder "o modelo baixou
    # e funciona?" antes de sair caçando erro de rede ou de porta ocupada.
    # -------------------------------------------------------------------
    service = QAService.inner()

    question = "Qual é a cor do céu?"
    context = "O céu é geralmente azul durante o dia devido à dispersão da luz."

    print(f"[teste rápido] modelo:   {service.pipeline.model.name_or_path}")
    print(f"[teste rápido] pergunta: {question}")
    print(f"[teste rápido] contexto: {context}")
    print(f"[teste rápido] resposta: {service.answer(question=question, context=context)}")
