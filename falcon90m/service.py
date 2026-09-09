import bentoml
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "tiiuae/Falcon-H1-Tiny-90M-Instruct"

# =============================================================================
# VARIANTE FALCON 90M -- geração de texto (não é QA extrativo)
# =============================================================================
#
# As outras pastas deste repositório usam modelos de *question answering*
# extrativo: o modelo grifa um trecho de um contexto que você entregou.
# Esta variante é diferente de propósito. O Falcon-H1-Tiny-90M é um LLM
# generativo minúsculo (~91M parâmetros, híbrido Transformer + Mamba) que
# *escreve* a resposta token a token.
#
# Por que existe aqui:
#   - Mostra um segundo estilo de serviço BentoML no mesmo projeto
#   - Roda em CPU sem GPU e baixa rápido (centenas de MB, não GB)
#   - Serve para experimentar instrução, roteamento e formatação "na beira"
#     — não para fatos confiáveis nem conversa profunda
#
# API:
#     POST /generate
#     {"prompt": "Say hello in one short sentence.", "max_new_tokens": 64}
#
# Modelos alternativos da mesma família (troque MODEL_NAME acima):
#   "tiiuae/Falcon-H1-Tiny-90M-Instruct"          -- padrão desta pasta
#   "tiiuae/Falcon-H1-Tiny-90M-Instruct-pre-DPO"  -- antes do estágio DPO
#   "tiiuae/Falcon-H1-Tiny-Coder-90M"             -- código / fill-in-the-middle
#   "tiiuae/Falcon-H1-Tiny-90M-Tool-Calling"      -- function calling
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o tokenizer e o modelo generativo Falcon."""
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            dtype=torch.float32,
        )
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token

    @bentoml.api
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Gera texto a partir de um prompt de usuário (chat template)."""
        if max_new_tokens < 1:
            max_new_tokens = 1
        if max_new_tokens > 512:
            max_new_tokens = 512

        messages = [{"role": "user", "content": prompt}]
        text = self.tokenizer.apply_chat_template(
            messages,
            tokenize=False,
            add_generation_prompt=True,
        )
        inputs = self.tokenizer(text, return_tensors="pt")
        do_sample = temperature > 0.0
        gen_kwargs = {
            "max_new_tokens": max_new_tokens,
            "do_sample": do_sample,
            "pad_token_id": self.tokenizer.pad_token_id,
        }
        if do_sample:
            gen_kwargs["temperature"] = temperature

        with torch.inference_mode():
            output_ids = self.model.generate(**inputs, **gen_kwargs)

        prompt_len = inputs["input_ids"].shape[-1]
        completion_ids = output_ids[0][prompt_len:]
        completion = self.tokenizer.decode(
            completion_ids,
            skip_special_tokens=True,
        )
        return {
            "text": completion.strip(),
            "model": MODEL_NAME,
            "prompt_tokens": int(prompt_len),
            "completion_tokens": int(completion_ids.shape[-1]),
            "max_new_tokens": max_new_tokens,
            "temperature": temperature,
        }


if __name__ == "__main__":
    service = QAService.inner()
    prompt = "Say hello in one short sentence."
    print(f"[teste rápido] modelo:  {MODEL_NAME}")
    print(f"[teste rápido] prompt:  {prompt}")
    print(f"[teste rápido] resposta: {service.generate(prompt=prompt)}")
