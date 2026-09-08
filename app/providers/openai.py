from collections.abc import AsyncIterator

from openai import APIError, APITimeoutError, AsyncOpenAI, OpenAI
from openai.types.responses import ResponseInputParam

from app.providers import (
    GenerationRequest,
    GenerationResult,
    ProviderError,
    ProviderTimeout,
    StreamCompleted,
    TextDelta,
)


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


class OpenAIStreamingProvider:
    def __init__(self, client: AsyncOpenAI) -> None:
        self.client = client

    async def stream(
        self, request: GenerationRequest
    ) -> AsyncIterator[TextDelta | StreamCompleted]:
        messages: ResponseInputParam = [
            {"role": message.role, "content": message.content} for message in request.messages
        ]
        try:
            stream = await self.client.responses.create(
                model=request.model,
                input=messages,
                stream=True,
                store=False,
                max_output_tokens=request.max_output_tokens,
                truncation="disabled",
            )
            async with stream:
                async for event in stream:
                    if event.type == "response.output_text.delta":
                        yield TextDelta(event.delta)
                    elif event.type == "response.completed":
                        if event.response.status != "completed":
                            raise ProviderError("Generation did not complete")
                        yield StreamCompleted()
                        return
                    elif event.type in ("response.failed", "response.incomplete", "error"):
                        raise ProviderError("Generation did not complete")
            raise ProviderError("Generation stream ended without completion")
        except APITimeoutError:
            raise ProviderTimeout("Generation timed out") from None
        except APIError:
            raise ProviderError("Generation failed") from None
