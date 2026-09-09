import bentoml
import gradio as gr
import torch
from fastapi import FastAPI
from transformers import AutoModelForCausalLM, AutoTokenizer

MODEL_NAME = "google/gemma-3-270m-it"

# =============================================================================
# VARIANTE GEMMA3 + GRADIO -- chat multi-turn com UI Gradio
# =============================================================================
#
# Mesmo modelo da pasta gemma3/, mas:
#   - POST /chat recebe a lista completa de mensagens (memória no cliente)
#   - UI Gradio em /ui
#
# Prefira porta fora de 3xxx:  PORT=8080 just gemma3_gradio serve
# =============================================================================

_SERVICE = None


def _clamp_tokens(n: int) -> int:
    """Limita a quantidade de tokens gerados ao intervalo permitido."""
    if n < 1:
        return 1
    if n > 512:
        return 512
    return n


def _gradio_respond(message: str, history: list):
    """Converte uma interação do Gradio em uma chamada de chat."""
    if _SERVICE is None:
        return "Serviço ainda não inicializado."
    messages = []
    for item in history or []:
        role = item.get("role")
        content = item.get("content")
        if role in {"user", "assistant", "system"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": message})
    return _SERVICE.chat(messages=messages, max_new_tokens=128)["text"]


def _build_gradio_app():
    """Monta a aplicação web Gradio dentro de uma aplicação FastAPI."""
    demo = gr.ChatInterface(
        fn=_gradio_respond,
        title="Gemma 3 270M",
        description="Chat multi-turn (histórico no Gradio → API /chat).",
        type="messages",
    )
    app = FastAPI()
    return gr.mount_gradio_app(app, demo, path="/")


@bentoml.service(resources={"cpu": "2"})
@bentoml.asgi_app(_build_gradio_app(), path="/ui")
class QAService:

    def __init__(self):
        """Carrega o tokenizer, o modelo e registra o serviço para o Gradio."""
        global _SERVICE
        self.tokenizer = AutoTokenizer.from_pretrained(MODEL_NAME)
        self.model = AutoModelForCausalLM.from_pretrained(
            MODEL_NAME,
            dtype=torch.float32,
        )
        self.model.eval()
        if self.tokenizer.pad_token_id is None:
            self.tokenizer.pad_token = self.tokenizer.eos_token
        _SERVICE = self

    def _generate_from_messages(
        self,
        messages: list[dict],
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Gera uma resposta a partir de um histórico de mensagens."""
        max_new_tokens = _clamp_tokens(max_new_tokens)
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
        """Chat multi-turn: o cliente envia o histórico completo a cada chamada."""
        return self._generate_from_messages(messages, max_new_tokens, temperature)

    @bentoml.api
    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
        temperature: float = 0.0,
    ) -> dict:
        """Compatível com gemma3/: um único prompt de usuário."""
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
