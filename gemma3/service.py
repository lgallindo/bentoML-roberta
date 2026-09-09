import bentoml
import torch
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "google/gemma-3-270m-it"

# =============================================================================
# VARIANTE GEMMA 3 -- geração de texto (não é QA extrativo)
# =============================================================================
#
# Irmã da variante falcon90m/: um LLM generativo minúsculo servido pelo
# BentoML, em vez de um modelo de *question answering* extrativo.
#
# Padrão: Gemma 3 270M Instruct (~270M parâmetros). É o passo natural depois
# do Falcon-H1-Tiny-90M quando se quer algo ainda ultra-pequeno, porém com
# melhor seguimento de instrução e caminho documentado para fine-tune +
# deploy on-device.
#
# Modelo GATED no Hugging Face: na primeira vez você precisa
#   1) aceitar a licença em https://huggingface.co/google/gemma-3-270m-it
#   2) autenticar:  uv run --no-active hf auth login
# Sem isso o download devolve 401.
#
# API:
#     POST /generate
#     {"prompt": "Say hello in one short sentence.", "max_new_tokens": 64}
#
# Modelos alternativos (troque MODEL_NAME acima):
#   "google/gemma-3-270m-it"   -- padrão desta pasta (instruct)
#   "google/gemma-3-270m"      -- base (sem instrução)
#   "google/gemma-3-1b-it"     -- um degrau maior, ainda pequeno
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        """Carrega o tokenizer e o modelo generativo Gemma."""
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
