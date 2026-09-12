import os
import time

import bentoml
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

from ferramentas import ESQUEMA, executar, extrair

# O menor modelo com *tool calling* de fábrica que dá para baixar: 354,5
# milhões de parâmetros. Troque pelo ambiente para comparar:
#     MODELO=Qwen/Qwen2.5-0.5B-Instruct just lfm2_tools run
MODEL_NAME = os.environ.get("MODELO", "LiquidAI/LFM2-350M")

# =============================================================================
# VARIANTE LFM2 + TOOLS -- o menor modelo que CHAMA FERRAMENTA
# =============================================================================
#
# Até aqui, o modelo só lia (QA extrativo) ou escrevia (falcon90m/, gemma3/).
# Nesta pasta ele faz uma terceira coisa: DECIDE. Ele olha a pergunta, olha a
# lista de ferramentas disponíveis e responde qual delas quer que a gente
# execute -- e com quais argumentos.
#
# O ciclo inteiro tem quatro passos, e o modelo só participa de dois:
#
#     1. modelo   recebe a pergunta + a lista de ferramentas
#                 -> devolve  consultar_estoque(produto="Cafeteira elétrica")
#     2. NÓS      executamos a função Python de verdade (lê o CSV, chama a API)
#     3. modelo   recebe o resultado da função
#                 -> devolve a frase final para o usuário
#     4. NÓS      entregamos a frase
#
# Repare no passo 2: **o modelo não executa nada**. Ele não tem acesso ao CSV,
# não abre conexão, não roda código. Ele só escreve o NOME de uma função e os
# argumentos, em texto. Quem executa somos nós, com um `if nome in FERRAMENTAS`.
# Todo "agente de IA" que você já viu é este laço, com mais enfeites.
#
# A SURPRESA DESTA PASTA
#
# A pasta gemma3_js/ termina com uma lição: "o encanamento funciona e o modelo
# não" -- o Gemma 3 270M recebe o histórico e não consegue usá-lo.
#
# Aqui acontece o contrário, e é surpreendente: um modelo de 354M -- MAIOR que
# o Gemma por só 84M -- chama ferramenta certinho, em português, na primeira
# tentativa. A diferença não é tamanho. É TREINO: o LFM2 foi treinado com
# exemplos de chamada de ferramenta e o Gemma 270M não foi.
#
# Chamar ferramenta não é uma capacidade que "emerge" quando o modelo fica
# grande. É um FORMATO que alguém ensinou. Essa distinção vale mais que
# qualquer tabela de benchmark.
#
# ONDE ELE QUEBRA (medido, ver o README)
#
# O LFM2-350M acerta quando DEVE chamar. Ele erra feio quando NÃO deve:
#
#     "Bom dia! Tudo bem?"          -> consultar_estoque(produto="Nesun")
#     "Qual é a capital da França?" -> consultar_estoque(produto="Paris")
#     "Obrigado, era só isso."      -> consultar_estoque(produto="Wireless Headphones")
#
# Ele inventa um produto e chama a ferramenta assim mesmo. Aprendeu "existe
# ferramenta, logo chame ferramenta", não "decida se precisa de ferramenta".
#
# Com 140M de parâmetros a mais, o Qwen2.5-0.5B-Instruct acerta as seis
# decisões do teste. Rode `just lfm2_tools bancada` e veja os três modelos
# lado a lado. É a régua que justifica pagar mais parâmetros -- não a
# qualidade da frase final, mas a disciplina de saber quando ficar quieto.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o modelo generativo que sabe pedir ferramenta."""
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            dtype=torch.float32,
        )
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

        parametros = sum(p.numel() for p in self.model.parameters())
        print(f"[modelo] {MODEL_NAME} -- {parametros / 1e6:.1f}M parâmetros")
        print(f"[ferramentas] {', '.join(f['function']['name'] for f in ESQUEMA)}")

    def _gerar(self, mensagens: list[dict], max_new_tokens: int, com_tools: bool) -> str:
        """Uma passada pelo modelo. `com_tools` decide se o esquema vai junto.

        Na segunda passada (depois da ferramenta rodar) mandamos as ferramentas
        de novo: sem elas, alguns chat templates rejeitam a mensagem de papel
        "tool" que está no histórico.
        """
        texto = self.tokenizer.apply_chat_template(
            mensagens,
            tools=ESQUEMA if com_tools else None,
            tokenize=False,
            add_generation_prompt=True,
        )
        entrada = self.tokenizer(texto, return_tensors="pt")
        with torch.inference_mode():
            saida = self.model.generate(
                **entrada,
                max_new_tokens=max_new_tokens,
                do_sample=False,
                pad_token_id=self.tokenizer.pad_token_id,
            )
        gerados = saida[0][entrada["input_ids"].shape[-1]:]
        # skip_special_tokens=False de propósito: as etiquetas de tool call
        # SÃO tokens especiais, e jogá-las fora apagaria justamente o que a
        # gente precisa ler.
        return self.tokenizer.decode(gerados, skip_special_tokens=False).strip()

    @bentoml.api
    def tool_call(self, prompt: str, max_new_tokens: int = 96) -> dict:
        """Só o PRIMEIRO salto: o que o modelo pediu, sem executar nada.

        É a rota de diagnóstico desta pasta. Devolve o texto CRU do modelo ao
        lado da versão interpretada -- é olhando os dois juntos que se entende
        que "tool calling" é um formato de texto, não mágica.
        """
        inicio = time.perf_counter()
        cru = self._gerar(
            [{"role": "user", "content": prompt}], max_new_tokens, com_tools=True
        )
        decorrido = (time.perf_counter() - inicio) * 1000
        chamadas = extrair(cru)
        return {
            "modelo": MODEL_NAME,
            "cru": cru,
            "chamadas": chamadas,
            "pediu_ferramenta": bool(chamadas),
            "modelo_ms": round(decorrido, 1),
        }

    @bentoml.api
    def chat(self, prompt: str, max_new_tokens: int = 128) -> dict:
        """O ciclo completo: decidir, executar, responder.

        O campo `passos` conta a história inteira da requisição -- o que o
        modelo pediu, o que a função devolveu, e o que ele escreveu depois.
        Num agente de verdade esse registro é a única forma de descobrir por
        que ele fez o que fez.
        """
        passos: list[dict] = []
        mensagens: list[dict] = [{"role": "user", "content": prompt}]

        inicio = time.perf_counter()
        cru = self._gerar(mensagens, max_new_tokens, com_tools=True)
        passos.append({"passo": "modelo decide", "cru": cru})

        chamadas = extrair(cru)
        if not chamadas:
            # O modelo respondeu direto, sem pedir ferramenta. Isso é o certo
            # para "bom dia" -- e é o que o LFM2-350M quase nunca faz.
            return {
                "modelo": MODEL_NAME,
                "resposta": _limpar(cru),
                "usou_ferramenta": False,
                "passos": passos,
                "total_ms": round((time.perf_counter() - inicio) * 1000, 1),
            }

        mensagens.append(
            {
                "role": "assistant",
                "tool_calls": [
                    {"type": "function", "function": c} for c in chamadas
                ],
            }
        )

        for chamada in chamadas:
            resultado = executar(chamada)
            passos.append(
                {
                    "passo": "ferramenta executa",
                    "ferramenta": chamada["name"],
                    "argumentos": chamada.get("arguments", {}),
                    "resultado": resultado,
                }
            )
            mensagens.append(
                {"role": "tool", "content": _json(resultado)}
            )

        final = self._gerar(mensagens, max_new_tokens, com_tools=True)
        passos.append({"passo": "modelo responde", "cru": final})

        return {
            "modelo": MODEL_NAME,
            "resposta": _limpar(final),
            "usou_ferramenta": True,
            "passos": passos,
            "total_ms": round((time.perf_counter() - inicio) * 1000, 1),
        }

    @bentoml.api
    def tools(self) -> dict:
        """O esquema exato que vai para o modelo, para poder ser lido."""
        return {"modelo": MODEL_NAME, "ferramentas": ESQUEMA}


def _json(valor) -> str:
    import json

    return json.dumps(valor, ensure_ascii=False)


def _limpar(texto: str) -> str:
    """Tira as etiquetas de fim de turno da frase mostrada ao usuário."""
    import re

    return re.sub(r"<\|[^|]*\|>", "", texto).strip()


if __name__ == "__main__":
    service = QAService.inner()

    print(f"\n{'=' * 70}\nCICLO COMPLETO\n{'=' * 70}")
    for pergunta in [
        "Quantas unidades do Fone de ouvido Bluetooth existem em estoque?",
        "Tem Cafeteira elétrica no estoque?",
    ]:
        r = service.chat(prompt=pergunta)
        print(f"\n  P: {pergunta}")
        for passo in r["passos"]:
            if passo["passo"] == "ferramenta executa":
                print(f"     [{passo['passo']}] {passo['ferramenta']}({passo['argumentos']})")
                print(f"                         -> {passo['resultado']}")
            else:
                print(f"     [{passo['passo']}] {passo['cru'][:100]!r}")
        print(f"  R: {r['resposta']}")
        print(f"     ({r['total_ms']} ms)")

    print(f"\n{'=' * 70}\nQUANDO NÃO DEVERIA CHAMAR FERRAMENTA\n{'=' * 70}")
    for pergunta in ["Bom dia! Tudo bem?", "Qual é a capital da França?"]:
        r = service.tool_call(prompt=pergunta)
        print(f"  {pergunta:34} pediu_ferramenta={r['pediu_ferramenta']}  {r['chamadas']}")
