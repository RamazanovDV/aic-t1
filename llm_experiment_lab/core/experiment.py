import asyncio
from dataclasses import dataclass
from typing import List, Callable, Optional

from ..api.client import LLMAPIClient, ModelResponse
from ..core.statistics import ModelStats


@dataclass
class ModelConfig:
    name: str
    custom_endpoint: str = ""
    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = -1


class Experiment:
    def __init__(self, client: LLMAPIClient):
        self.client = client

    async def run_parallel(
        self,
        system_prompt: str,
        user_prompt: str,
        models: List[ModelConfig],
        progress_callback: Optional[Callable] = None,
    ) -> List[ModelStats]:
        tasks = []
        for i, model in enumerate(models):
            task = self._run_model(
                system_prompt, user_prompt, model, i, progress_callback
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks)
        return results

    async def run_sequential(
        self,
        system_prompt: str,
        user_prompt: str,
        models: List[ModelConfig],
        delay: float = 1.0,
        progress_callback: Optional[Callable] = None,
    ) -> List[ModelStats]:
        results = []
        for i, model in enumerate(models):
            result = await self._run_model(
                system_prompt, user_prompt, model, i, progress_callback
            )
            results.append(result)
            if i < len(models) - 1 and delay > 0:
                await asyncio.sleep(delay)
        return results

    async def _run_model(
        self,
        system_prompt: str,
        user_prompt: str,
        model: ModelConfig,
        index: int,
        progress_callback: Optional[Callable] = None,
    ) -> ModelStats:
        if progress_callback:
            progress_callback(index, "running", model.name)

        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            self.client.chat_completion,
            model.name,
            system_prompt,
            user_prompt,
            model.temperature,
            model.top_p,
            model.top_k,
            model.custom_endpoint,
        )

        stats = ModelStats(
            model_name=model.name,
            response_time=response.response_time,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            content=response.content,
            raw_request=response.raw_request,
            raw_response=response.raw_response,
            error=response.error,
        )

        if progress_callback:
            status = "error" if response.error else "completed"
            progress_callback(index, status, model.name)

        return stats

    def get_response_sync(
        self,
        system_prompt: str,
        user_prompt: str,
        model: ModelConfig,
    ) -> ModelResponse:
        return self.client.chat_completion(
            model=model.name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            temperature=model.temperature,
            top_p=model.top_p,
            top_k=model.top_k,
            custom_endpoint=model.custom_endpoint,
        )
