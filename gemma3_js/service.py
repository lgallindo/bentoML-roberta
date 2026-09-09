import bentoml
import torch
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "google/gemma-3-270m-it"
STATIC_DIR = Path(__file__).resolve().parent / "static"

# =============================================================================
# VARIANTE GEMMA3 + JS -- chat multi-turn com HTML/JS feito à mão
# =============================================================================
#
# Mesmo modelo da pasta gemma3/, mas:
#   - POST /chat recebe o histórico completo
#   - UI estática em /ui/ (um index.html + app.js, sem framework)
#
# Prefira porta fora de 3xxx:  PORT=8080 just gemma3_js serve
# =============================================================================

web = FastAPI()


@web.get("/")
async def ui_index():
    """Entrega a página HTML da interface web."""
    return FileResponse(STATIC_DIR / "index.html")


@web.get("/app.js")
async def ui_js():
    """Entrega o JavaScript da interface web."""
    return FileResponse(STATIC_DIR / "app.js", media_type="application/javascript")


@bentoml.service(resources={"cpu": "2"})
@bentoml.asgi_app(web, path="/ui")
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

    def _generate_from_messages(
        self,
        messages: list[dict],
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Gera uma resposta a partir de um histórico de mensagens."""
        if max_new_tokens < 1:
            max_new_tokens = 1
        if max_new_tokens > 512:
            max_new_tokens = 512

        clean = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m.get("role") in {"system", "user", "assistant"} and m.get("content")
        ]
        if not clean:
            return {
                "text": "",
                "model": MODEL_NAME,
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "max_new_tokens": max_new_tokens,
                "temperature": temperature,
            }

        text = self.tokenizer.apply_chat_template(
            clean,
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

    @bentoml.api
    def chat(
        self,
        messages: list[dict],
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Chat multi-turn: o cliente JS envia o histórico completo."""
        return self._generate_from_messages(messages, max_new_tokens, temperature)

    @bentoml.api
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Gera texto a partir de um prompt único do usuário."""
        return self._generate_from_messages(
            [{"role": "user", "content": prompt}],
            max_new_tokens,
            temperature,
        )


if __name__ == "__main__":
    service = QAService.inner()
    messages = [
        {"role": "user", "content": "My name is Ada."},
        {"role": "assistant", "content": "Hi Ada!"},
        {"role": "user", "content": "What is my name?"},
    ]
    print(f"[teste rápido] modelo: {MODEL_NAME}")
    print(f"[teste rápido] chat:   {service.chat(messages=messages)}")
