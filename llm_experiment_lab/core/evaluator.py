import asyncio
from typing import List, Optional, Callable
from ..api.client import LLMAPIClient, ModelResponse
from ..core.statistics import ModelStats


class Evaluator:
    DEFAULT_SYSTEM_PROMPT = "You are an expert evaluator. Compare LLM responses and provide fair, objective analysis."

    def __init__(self, client: LLMAPIClient):
        self.client = client

    async def evaluate(
        self,
        eval_model: str,
        system_prompt: str,
        user_prompt: str,
        responses: List[dict],
        temperature: float = 0.3,
        eval_system_prompt: str = "",
    ) -> tuple[str, ModelResponse]:
        eval_prompt = self._build_eval_prompt(
            system_prompt, user_prompt, responses
        )

        final_system_prompt = eval_system_prompt if eval_system_prompt else self.DEFAULT_SYSTEM_PROMPT

        result = await self.client.chat_completion(
            model=eval_model,
            system_prompt=final_system_prompt,
            user_prompt=eval_prompt,
            temperature=temperature,
            top_p=1.0,
            top_k=-1,
        )

        return result.content if not result.error else f"Error: {result.error}", result

    async def evaluate_stream(
        self,
        eval_model: str,
        system_prompt: str,
        user_prompt: str,
        responses: List[dict],
        temperature: float = 0.3,
        eval_system_prompt: str = "",
        on_chunk: Optional[Callable[[str, str], None]] = None,
    ) -> tuple[str, ModelResponse]:
        eval_prompt = self._build_eval_prompt(
            system_prompt, user_prompt, responses
        )

        final_system_prompt = eval_system_prompt if eval_system_prompt else self.DEFAULT_SYSTEM_PROMPT

        result = await self.client.chat_completion_stream(
            model=eval_model,
            system_prompt=final_system_prompt,
            user_prompt=eval_prompt,
            temperature=temperature,
            top_p=1.0,
            top_k=-1,
            on_chunk=on_chunk,
        )

        return result.content if not result.error else f"Error: {result.error}", result

    def _build_eval_prompt(
        self,
        system_prompt: str,
        user_prompt: str,
        responses: List[dict],
    ) -> str:
        prompt = f"""Сравните следующие ответы на один и тот же запрос и предоставьте рейтинг от лучшего к худшему с краткими пояснениями.

Системный промпт: {system_prompt}

Пользовательский промпт: {user_prompt}

"""

        for i, resp in enumerate(responses, 1):
            if resp.get("content"):
                model_name = resp.get("model", "Unknown")
                content = resp["content"]
                stats = resp.get("stats", {})
                time_val = stats.get("response_time", 0)
                total_tokens = stats.get("total_tokens", 0)
                prompt += f"Ответ {i} (модель: {model_name}, время: {time_val:.2f}с, токены: {total_tokens}):\n{content}\n\n"

        prompt += """Предоставьте:
1. Рейтинг от лучшего (1-е место) к худшему (3-е место)
2. Краткое пояснение для каждого места
3. Ключевые сильные и слабые стороны каждого ответа
4. Учтите при оценке скорость ответа и количество затраченных токенов"""

        return prompt
