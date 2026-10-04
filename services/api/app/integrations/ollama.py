from ollama import AsyncClient


class OllamaGateway:
    def __init__(self, host: str, timeout: float):
        self.client = AsyncClient(host=host, timeout=timeout)

    async def list_model_names(self) -> list[str]:
        response = await self.client.list()
        return [model.model for model in response.models if model.model]

    async def close(self) -> None:
        await self.client.close()
