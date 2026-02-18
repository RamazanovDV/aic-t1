import asyncio
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Any

from ..api.client import LLMAPIClient, ModelResponse
from ..core.statistics import ModelStats


@dataclass
class ModelConfig:
    name: str
    custom_endpoint: str = ""
    custom_api_token: str = ""
    temperature: float = 0.7
    top_p: float = 1.0
    top_k: int = -1
    prompt_modifier: str = ""
    stop_sequences: List[str] = field(default_factory=list)
    max_tokens: int = 0
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0


class Experiment:
    def __init__(self, client: LLMAPIClient):
        self.client = client
        self._is_cancelled = False

    def cancel(self):
        self._is_cancelled = True
        self.client.cancel_request()

    def reset_cancel(self):
        self._is_cancelled = False

    async def run_single(
        self,
        system_prompt: str,
        user_prompt: str,
        model: ModelConfig,
        index: int = 0,
        progress_callback: Optional[Callable] = None,
        complete_callback: Optional[Callable] = None,
    ) -> ModelStats:
        return await self._run_model(
            system_prompt, user_prompt, model, index, progress_callback, complete_callback
        )

    async def run_parallel(
        self,
        system_prompt: str,
        user_prompt: str,
        models: List[ModelConfig],
        progress_callback: Optional[Callable] = None,
        complete_callback: Optional[Callable] = None,
    ) -> List[ModelStats]:
        self.reset_cancel()
        tasks = []
        for i, model in enumerate(models):
            task = self._run_model(
                system_prompt, user_prompt, model, i, progress_callback, complete_callback
            )
            tasks.append(task)

        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        final_results = []
        for i, result in enumerate(results):
            if isinstance(result, Exception):
                stats = ModelStats(
                    model_name=models[i].name,
                    response_time=0,
                    prompt_tokens=0,
                    completion_tokens=0,
                    total_tokens=0,
                    content="",
                    reasoning=None,
                    raw_request={},
                    raw_response={},
                    error=str(result),
                )
                final_results.append(stats)
            else:
                final_results.append(result)
        
        return final_results

    async def run_sequential(
        self,
        system_prompt: str,
        user_prompt: str,
        models: List[ModelConfig],
        delay: float = 1.0,
        progress_callback: Optional[Callable] = None,
        complete_callback: Optional[Callable] = None,
    ) -> List[ModelStats]:
        self.reset_cancel()
        results = []
        for i, model in enumerate(models):
            if self._is_cancelled:
                break
            result = await self._run_model(
                system_prompt, user_prompt, model, i, progress_callback, complete_callback
            )
            results.append(result)
            if i < len(models) - 1 and delay > 0 and not self._is_cancelled:
                await asyncio.sleep(delay)
        return results

    async def _run_model(
        self,
        system_prompt: str,
        user_prompt: str,
        model: ModelConfig,
        index: int,
        progress_callback: Optional[Callable] = None,
        complete_callback: Optional[Callable] = None,
    ) -> ModelStats:
        if self._is_cancelled:
            return ModelStats(
                model_name=model.name,
                response_time=0,
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                content="",
                reasoning=None,
                raw_request={},
                raw_response={},
                error="Cancelled",
            )

        if progress_callback:
            progress_callback(index, "running", model.name)

        full_user_prompt = user_prompt
        if model.prompt_modifier:
            full_user_prompt = user_prompt + "\n\n" + model.prompt_modifier

        if progress_callback:
            def on_chunk(content: str, reasoning: str):
                progress_callback(index, "streaming", model.name, content, reasoning)
            response = await self.client.chat_completion_stream(
                model.name,
                system_prompt,
                full_user_prompt,
                model.temperature,
                model.top_p,
                model.top_k,
                model.custom_endpoint,
                model.custom_api_token,
                stop=model.stop_sequences if model.stop_sequences else None,
                max_tokens=model.max_tokens or 0,
                frequency_penalty=model.frequency_penalty,
                presence_penalty=model.presence_penalty,
                on_chunk=on_chunk,
            )
        else:
            response = await self.client.chat_completion_stream(
                model.name,
                system_prompt,
                full_user_prompt,
                model.temperature,
                model.top_p,
                model.top_k,
                model.custom_endpoint,
                model.custom_api_token,
                stop=model.stop_sequences if model.stop_sequences else None,
                max_tokens=model.max_tokens or 0,
                frequency_penalty=model.frequency_penalty,
                presence_penalty=model.presence_penalty,
            )

        if self._is_cancelled and response.error != "Cancelled":
            response.error = "Cancelled"
            response.content = ""

        stats = ModelStats(
            model_name=model.name,
            response_time=response.response_time,
            prompt_tokens=response.prompt_tokens,
            completion_tokens=response.completion_tokens,
            total_tokens=response.total_tokens,
            content=response.content,
            reasoning=response.reasoning,
            raw_request=response.raw_request,
            raw_response=response.raw_response,
            error=response.error,
        )

        status = "error" if response.error else "completed"
        if progress_callback:
            progress_callback(index, status, model.name)

        if complete_callback:
            complete_callback(index, stats, model.name)

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
