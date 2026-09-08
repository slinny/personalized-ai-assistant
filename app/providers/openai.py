from openai import APIError, APITimeoutError, OpenAI
from openai.types.responses import ResponseInputParam

from app.providers import GenerationRequest, GenerationResult, ProviderError, ProviderTimeout


class OpenAIProvider:
    def __init__(self, client: OpenAI) -> None:
        self.client = client

    def generate(self, request: GenerationRequest) -> GenerationResult:
        messages: ResponseInputParam = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        try:
            response = self.client.responses.create(
                model=request.model,
                input=messages,
                stream=False,
                store=False,
                max_output_tokens=request.max_output_tokens,
                truncation="disabled",
            )
        except APITimeoutError:
            raise ProviderTimeout("Generation timed out") from None
        except APIError:
            raise ProviderError("Generation failed") from None
        if response.status != "completed" or not response.output_text.strip():
            raise ProviderError("Generation did not return completed text")
        return GenerationResult(response.output_text)
