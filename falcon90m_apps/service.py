import bentoml

from engine import MODEL_NAME, FalconAppsEngine

# =============================================================================
# SAMPLE APPS on Falcon-H1-Tiny-90M (structured glue, not a chatbot)
# =============================================================================
#
# Endpoints:
#   POST /extract_json   {"text": "...", "keys": ["name","city"]}
#   POST /route_intent   {"text": "...", "labels": ["BILLING","TECH","CANCEL","OTHER"]}
#   POST /fill_template  {"template": "Hello {name}", "data": {"name": "Ada"}}
#   POST /tag_email      {"subject": "...", "tags": ["meeting","invoice","spam","support"]}
#
# Prefira PORT=8080 (fora de 3xxx). CPU limitado a 2 cores.
# =============================================================================


@bentoml.service(resources={"cpu": "2"})
class QAService:

    def __init__(self):
        self.engine = FalconAppsEngine(model_name=MODEL_NAME, threads=2)

    @bentoml.api
    def extract_json(self, text: str, keys: list[str]) -> dict:
        return self.engine.extract_json(text=text, keys=keys)

    @bentoml.api
    def route_intent(self, text: str, labels: list[str] | None = None) -> dict:
        return self.engine.route_intent(text=text, labels=labels)

    @bentoml.api
    def fill_template(self, template: str, data: dict[str, str]) -> dict:
        return self.engine.fill_template(template=template, data=data)

    @bentoml.api
    def tag_email(self, subject: str, tags: list[str] | None = None) -> dict:
        return self.engine.tag_email(subject=subject, tags=tags)


if __name__ == "__main__":
    from suite import run_suite

    raise SystemExit(run_suite(verbose=True))
