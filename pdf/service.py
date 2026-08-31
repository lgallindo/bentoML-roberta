import bentoml
from pathlib import Path

from pypdf import PdfReader
from transformers import AutoModelForQuestionAnswering, AutoTokenizer, pipeline

MODEL_NAME = "deepset/xlm-roberta-base-squad2"

# =============================================================================
# POR QUE ESTA VARIANTE RESPONDE ERRADO  (explicação "para quem tem 10 anos")
# =============================================================================
#
# Pense numa prova de "ache a frase no texto". O modelo não SABE nada sobre o
# SAC nem sobre lojas. Ele só sabe pegar um texto que você entrega e grifar o
# pedaço que mais parece com a resposta. Só que ele é míope: enxerga apenas
# umas 384 "pecinhas de palavra" por vez -- mais ou menos uma página.
#
# Aqui a gente cola DOIS livros diferentes num texto só, com 43.069 letras:
#     DECRETO_11034_2022.pdf (o Decreto do SAC) ...... 11.307 letras
#     7121.pdf (uma apostila do Sebrae) .............. 31.762 letras
#
# Para responder UMA pergunta, o modelo tem que arrastar aquela janelinha por
# cima de ~100 pedaços, grifar o melhor candidato dentro de cada pedaço e, no
# fim, escolher o grifo que tirou a maior nota. Daí nascem dois problemas:
#
#   1) DEMORA. São ~100 leituras por pergunta, na CPU. Medido: 15 a 19
#      segundos para CADA pergunta.
#
#   2) CONFUSÃO. Um pedaço QUALQUER da apostila do Sebrae pode tirar uma nota
#      maior do que a resposta certa, que está lá no Decreto. Medido:
#        - "Qual é o prazo para resposta de reclamação no SAC?"
#              -> "" (vazio), mesmo com "sete dias" escrito DUAS VEZES no
#                 Decreto. O modelo simplesmente não achou.
#        - "Quantos dias tem o consumidor para cancelar o serviço?"
#              -> "DIA DAS CRIANÇAS E NATAL," -- um trecho da apostila do
#                 Sebrae, que não tem nada a ver com a pergunta.
#        - "O que é o SAC?" -> essa deu certo, meio por sorte: a resposta
#                 está logo no começo do Decreto, num pedaço sem concorrência.
#
# O QUE ESTÁ FALTANDO: alguém precisa ESCOLHER o pedaço certo do texto ANTES
# de chamar o modelo -- procurar a página que fala do assunto perguntado e
# mandar só aquela página. Esse passo que falta tem nome: é a "busca"
# (retrieval) do RAG, Retrieval-Augmented Generation.
#
# Esta variante existe DE PROPÓSITO para mostrar o problema acontecendo.
# Compare com inventario/, que é o extremo oposto: contexto pequeno
# (8.355 letras) e já organizado em frases curtas.
#
# REPARE NA ASSINATURA DE answer(): aqui ela recebe SÓ `question`. O contexto
# já foi carregado na inicialização e mora dentro do serviço, então não faz
# sentido mandá-lo na requisição.
# =============================================================================


def _context_sample(text: str, n: int = 3) -> str:
    """As n primeiras e as n últimas linhas não vazias do contexto.

    Antes, este serviço fazia `print(self.context)` e despejava as 43.069
    letras inteiras no terminal a cada inicialização -- 957 linhas de log, que
    enterravam as mensagens de verdade do BentoML. Agora mostramos só uma
    amostra: o suficiente para conferir que os PDFs foram lidos direito.
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

        context_dir = Path(__file__).parent / "context"
        pdf_files = sorted(context_dir.glob("*.pdf"))
        if not pdf_files:
            raise FileNotFoundError(f"Nenhum PDF encontrado em {context_dir}")

        self.context = "\n\n".join(
            self._load_pdf_context(pdf_path) for pdf_path in pdf_files if pdf_path.exists()
        )

        line_count = len([l for l in self.context.splitlines() if l.strip()])
        print(
            f"[contexto] {len(self.context)} caracteres em {line_count} linhas "
            f"(2 PDFs colados -- veja o comentário no topo deste arquivo)"
        )
        print(_context_sample(self.context))

    def _load_pdf_context(self, pdf_path: str | Path) -> str:
        reader = PdfReader(str(pdf_path))
        pages = [page.extract_text() for page in reader.pages]
        return "\n\n".join(page for page in pages if page)

    @bentoml.api
    def answer(self, question: str) -> dict:
        return self.pipeline(question=question, context=self.context)


if __name__ == "__main__":
    # Teste rápido sem servidor. Cuidado: além dos ~15s de carregamento do
    # modelo, cada pergunta desta variante leva de 15 a 19 segundos.
    service = QAService.inner()

    question = "O que é o SAC?"
    print(f"[teste rápido] modelo:   {MODEL_NAME}")
    print(f"[teste rápido] pergunta: {question}")
    print(f"[teste rápido] resposta: {service.answer(question=question)}")
