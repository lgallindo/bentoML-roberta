"""A etapa de BUSCA que falta na variante pdf/.

Este módulo não sabe nada sobre modelos, BentoML ou HTTP. Ele faz uma coisa
só: dada uma pergunta, devolver os pedaços do texto que têm mais chance de
conter a resposta. É o "R" de RAG (*Retrieval-Augmented Generation*) --
recuperação.

E faz isso com a biblioteca padrão do Python: sem banco de vetores, sem
embeddings, sem nenhuma dependência nova. A ideia toda cabe em três passos:

    1. QUEBRAR   os PDFs em trechos pequenos
    2. INDEXAR   contando quais palavras aparecem em quais trechos
    3. BUSCAR    dando uma nota a cada trecho e devolvendo os melhores

O algoritmo de nota é o BM25, que buscadores de texto usam há décadas. Ele
não é "inteligência artificial": é contagem de palavras com duas correções de
bom senso, explicadas na função `Indice.buscar`.

O PASSO 1 É O QUE MAIS IMPORTA, E QUASE NINGUÉM FALA DELE

Enquanto esta pasta foi escrita, a busca foi medida com três jeitos de
quebrar o texto. O modelo, o índice e as perguntas eram os mesmos nos três:

    pedaços de 700 letras, cortados em parágrafo .... o trecho certo vinha,
        mas junto com outro prazo ("noventa dias") na mesma tacada, e o
        modelo grifava o prazo errado;
    pedaços de 400 letras, cortados na marra ........ o corte caía no meio da
        frase, e o modelo passou a responder "não sei" para tudo;
    um trecho por ARTIGO, cortado em fim de frase ... funcionou.

A lição: num documento jurídico, a unidade de sentido é o artigo, não o
parágrafo visual nem um número redondo de letras. Quebrar o texto em cima da
estrutura que ele já tem vale mais do que qualquer ajuste de fórmula.
"""

from __future__ import annotations

import bisect
import math
import re
import unicodedata
from collections import Counter
from pathlib import Path

# Palavras que aparecem em quase toda frase do português e por isso não
# ajudam a distinguir um trecho do outro. Se "de" conta ponto, todo trecho
# ganha ponto, e a nota para de significar alguma coisa.
STOPWORDS = {
    "a", "ao", "aos", "as", "à", "às", "com", "como", "da", "das", "de", "do",
    "dos", "e", "em", "entre", "essa", "esse", "esta", "este", "eu", "for",
    "foi", "há", "isso", "isto", "já", "la", "lhe", "lo", "mais", "mas", "me",
    "mesmo", "meu", "muito", "na", "nas", "no", "nos", "num", "numa", "não",
    "o", "os", "ou", "para", "pela", "pelas", "pelo", "pelos", "per", "por",
    "qual", "quais", "quando", "que", "quem", "se", "sem", "ser", "seu",
    "seus", "sua", "suas", "são", "só", "também", "te", "tem", "ter", "teu",
    "um", "uma", "umas", "uns", "você", "vocês", "é",
}

# Tamanho alvo de um trecho, em letras. Ver o comentário no topo do arquivo:
# este número foi medido, não chutado. Acima de ~700 o modelo começa a
# preferir a resposta vazia; abaixo de ~150 o trecho perde o contexto.
TAMANHO_ALVO = 300

# Onde um artigo começa. É isto que dá a estrutura ao Decreto.
INICIO_DE_ARTIGO = re.compile(r"(?=Art\. \d+)")
CABECALHO = re.compile(r"(Art\. \d+[ºo]?\.?)")

# Fim de frase: ponto, ponto-e-vírgula ou dois-pontos seguidos de espaço.
FIM_DE_FRASE = re.compile(r"(?<=[.;:])\s+")


def normalizar(texto: str) -> list[str]:
    """Quebra um texto em palavras comparáveis.

    Três coisas acontecem aqui, e todas existem para que "Prazo", "prazo" e
    "PRAZO" sejam a MESMA palavra na hora de contar:

        1. tudo vira minúscula;
        2. acentos somem (PDF escaneado erra acento o tempo todo);
        3. o que não for letra ou número vira separador.

    Depois disso, jogamos fora as stopwords e as palavras de uma letra só.

    >>> normalizar("O prazo de RESPOSTA é de sete dias!")
    ['prazo', 'resposta', 'sete', 'dias']
    """
    sem_acento = unicodedata.normalize("NFKD", texto.lower())
    sem_acento = "".join(c for c in sem_acento if not unicodedata.combining(c))
    palavras = re.findall(r"[a-z0-9]+", sem_acento)
    return [p for p in palavras if len(p) > 1 and p not in STOPWORDS]


def ler_documentos(pasta: str | Path) -> list[dict]:
    """Lê os PDFs e devolve, por documento, o texto inteiro e o mapa de páginas.

    O texto vira uma string só por documento, porque um artigo pode começar
    numa página e terminar na seguinte -- e cortar no meio do artigo é
    exatamente o erro que esta pasta existe para não cometer.

    Mas o número da página não pode ser perdido: é ele que vai virar a
    CITAÇÃO na resposta. Por isso guardamos, junto, em que letra do texto
    cada página começou. Depois é só procurar nessa lista para saber de qual
    página um trecho veio.
    """
    from pypdf import PdfReader

    pasta = Path(pasta)
    documentos: list[dict] = []
    for caminho in sorted(pasta.glob("*.pdf")):
        leitor = PdfReader(str(caminho))
        partes: list[str] = []
        inicios: list[int] = []
        paginas: list[int] = []
        posicao = 0
        for numero, pagina in enumerate(leitor.pages, start=1):
            texto = re.sub(r"\s+", " ", pagina.extract_text() or "").strip()
            if not texto:
                continue
            inicios.append(posicao)
            paginas.append(numero)
            partes.append(texto)
            posicao += len(texto) + 1
        if partes:
            documentos.append(
                {
                    "documento": caminho.name,
                    "texto": " ".join(partes),
                    "inicios": inicios,
                    "paginas": paginas,
                }
            )
    if not documentos:
        raise FileNotFoundError(f"Nenhum PDF com texto em {pasta}")
    return documentos


def quebrar_em_trechos(documentos: list[dict]) -> list[dict]:
    """Um trecho por artigo -- e artigos compridos viram vários trechos.

    Duas regras, e as duas foram aprendidas apanhando (veja o topo do arquivo):

      CORTE EM ARTIGO. O Decreto já vem dividido em "Art. 1º", "Art. 2º"...
      Cada artigo trata de um assunto. Cortar ali é cortar onde o próprio
      documento diz que uma ideia acabou e outra começou.

      CORTE EM FIM DE FRASE. Se um artigo passa de ~300 letras, ele é
      dividido -- mas só depois de um ponto final. Cortar no meio da frase
      produz um trecho truncado, e o modelo responde "não sei" para trecho
      truncado (medido: com cortes na marra, TODAS as perguntas viraram
      resposta vazia).

      E cada pedaço a mais herda o cabeçalho do artigo ("Art. 13."), senão o
      segundo pedaço vira um texto órfão, sem dizer de que artigo ele é.
    """
    trechos: list[dict] = []

    for doc in documentos:
        texto = doc["texto"]
        for artigo in INICIO_DE_ARTIGO.split(texto):
            if len(artigo.strip()) < 40:
                continue
            deslocamento = texto.find(artigo)
            encontrado = CABECALHO.match(artigo.strip())
            cabecalho = encontrado.group(1) if encontrado else ""

            acumulado = ""
            posicao_acumulado = deslocamento
            posicao = deslocamento
            for frase in FIM_DE_FRASE.split(artigo):
                if len(acumulado) + len(frase) + 1 <= TAMANHO_ALVO:
                    if not acumulado:
                        posicao_acumulado = posicao
                    acumulado = f"{acumulado} {frase}".strip()
                else:
                    trechos.append(
                        _montar(doc, acumulado, posicao_acumulado, cabecalho)
                    )
                    acumulado = frase
                    posicao_acumulado = posicao
                posicao += len(frase) + 1

            if len(acumulado) >= 40:
                trechos.append(_montar(doc, acumulado, posicao_acumulado, cabecalho))

    return [t for t in trechos if t]


def _montar(doc: dict, texto: str, posicao: int, cabecalho: str) -> dict | None:
    """Monta um trecho, com cabeçalho do artigo e número de página."""
    texto = texto.strip()
    if len(texto) < 40:
        return None
    if cabecalho and not texto.startswith("Art."):
        texto = f"{cabecalho} {texto}"
    # Qual página contém esta posição? A lista `inicios` está em ordem, então
    # bisect acha em tempo logarítmico em vez de varrer tudo.
    i = bisect.bisect_right(doc["inicios"], posicao) - 1
    return {
        "documento": doc["documento"],
        "pagina": doc["paginas"][max(0, i)],
        "texto": texto,
    }


class Indice:
    """O índice: quem tem qual palavra, e o quanto cada palavra vale.

    Construir o índice é a parte cara, e acontece UMA vez, quando o serviço
    sobe. Depois disso cada busca é aritmética em cima de contagens prontas --
    é por isso que buscar leva décimos de milissegundo.
    """

    def __init__(self, trechos: list[dict]):
        self.trechos = trechos
        self.contagens = [Counter(normalizar(t["texto"])) for t in trechos]
        self.tamanhos = [sum(c.values()) for c in self.contagens]
        self.tamanho_medio = (
            sum(self.tamanhos) / len(self.tamanhos) if self.tamanhos else 0.0
        )

        # Em quantos trechos cada palavra aparece. Palavra que aparece em TODO
        # lugar (ex.: "sac", num decreto sobre o SAC) vale pouco; palavra rara
        # vale muito. Esse é o famoso IDF.
        frequencia: Counter = Counter()
        for contagem in self.contagens:
            frequencia.update(contagem.keys())

        total = len(trechos)
        self.idf = {
            palavra: math.log(1 + (total - n + 0.5) / (n + 0.5))
            for palavra, n in frequencia.items()
        }

    def __len__(self) -> int:
        return len(self.trechos)

    def buscar(self, pergunta: str, k: int = 6) -> list[dict]:
        """Dá uma nota BM25 a cada trecho e devolve os k melhores.

        A fórmula tem duas correções de bom senso em cima de "contar palavra":

          SATURAÇÃO (o k1): a décima vez que "prazo" aparece num trecho não
          vale tanto quanto a primeira. Sem isso, um trecho que repete a mesma
          palavra 30 vezes ganharia de um trecho que responde a pergunta uma
          vez, com clareza.

          TAMANHO (o b): trecho comprido tem mais palavras e mais chance de
          conter a sua por acaso. A nota é descontada pelo tamanho, senão o
          vencedor seria sempre o parágrafo mais longo do PDF.

        Trechos com nota zero são descartados: é melhor devolver dois trechos
        bons do que seis, sendo quatro lixo.
        """
        k1, b = 1.5, 0.75
        termos = normalizar(pergunta)
        if not termos:
            return []

        notas: list[tuple[float, int]] = []
        for i, contagem in enumerate(self.contagens):
            nota = 0.0
            for termo in termos:
                frequencia = contagem.get(termo)
                if not frequencia:
                    continue
                denominador = frequencia + k1 * (
                    1 - b + b * self.tamanhos[i] / (self.tamanho_medio or 1)
                )
                nota += self.idf.get(termo, 0.0) * frequencia * (k1 + 1) / denominador
            if nota > 0:
                notas.append((nota, i))

        notas.sort(key=lambda par: (-par[0], par[1]))
        return [{**self.trechos[i], "nota": round(nota, 3)} for nota, i in notas[:k]]


def montar_indice(pasta: str | Path) -> Indice:
    """Atalho: da pasta de PDFs até o índice pronto para buscar."""
    return Indice(quebrar_em_trechos(ler_documentos(pasta)))


if __name__ == "__main__":
    # Rode com:  uv run --no-active python busca.py
    # Mostra a BUSCA sozinha, sem modelo nenhum no caminho. Repare na
    # velocidade: não tem rede neural aqui, é contagem de palavras.
    import time

    inicio = time.perf_counter()
    indice = montar_indice(Path(__file__).parent / "context")
    print(f"[índice] {len(indice)} trechos em {time.perf_counter() - inicio:.2f}s")

    for pergunta in [
        "Qual é o prazo para resposta de reclamação no SAC?",
        "Quantos dias tem o consumidor para cancelar o serviço?",
        "O que é o SAC?",
    ]:
        print(f"\n=== {pergunta}")
        inicio = time.perf_counter()
        encontrados = indice.buscar(pergunta, k=4)
        decorrido = (time.perf_counter() - inicio) * 1000
        for trecho in encontrados:
            print(
                f"  [{trecho['nota']:>6}] {trecho['documento']} p.{trecho['pagina']}: "
                f"{trecho['texto'][:100]}..."
            )
        print(f"  (busca em {decorrido:.2f} ms)")
