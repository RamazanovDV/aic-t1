import json
import time
import asyncio
from dataclasses import dataclass
from typing import Optional, List

import httpx


@dataclass
class ModelResponse:
    content: str
    prompt_tokens: int
    completion_tokens: int
    total_tokens: int
    response_time: float
    raw_request: dict
    raw_response: dict
    reasoning: Optional[str] = None
    error: Optional[str] = None


class LLMAPIClient:
    def __init__(
        self,
        api_key: str,
        base_url: str = "https://api.openai.com/v1",
        verify_ssl: bool = True,
    ):
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.verify_ssl = verify_ssl
        self._cancel_event: Optional[asyncio.Event] = None

    async def chat_completion(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        top_p: float = 1.0,
        top_k: int = -1,
        custom_endpoint: str = "",
    ) -> ModelResponse:
        endpoint = custom_endpoint if custom_endpoint else f"{self.base_url}/chat/completions"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        request_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
        }

        if top_k > 0:
            request_data["top_k"] = top_k

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }

        start_time = time.time()

        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=120.0) as client:
                self._cancel_event.clear()
                response = await client.post(endpoint, json=request_data, headers=headers)
                
                if self._cancel_event.is_set():
                    return ModelResponse(
                        content="",
                        prompt_tokens=0,
                        completion_tokens=0,
                        total_tokens=0,
                        response_time=time.time() - start_time,
                        raw_request=request_data,
                        raw_response={},
                        reasoning=None,
                        error="Cancelled",
                    )
                
                response.raise_for_status()
                response_json = response.json()

            response_time = time.time() - start_time

            message = response_json["choices"][0]["message"]
            content = message.get("content", "")
            usage = response_json.get("usage", {})

            reasoning = message.get("reasoning_content") or message.get("thinking")

            return ModelResponse(
                content=content,
                prompt_tokens=usage.get("prompt_tokens", 0),
                completion_tokens=usage.get("completion_tokens", 0),
                total_tokens=usage.get("total_tokens", 0),
                response_time=response_time,
                raw_request=request_data,
                raw_response=response_json,
                reasoning=reasoning,
            )

        except httpx.HTTPStatusError as e:
            response_time = time.time() - start_time
            error_msg = f"HTTP {e.response.status_code}: {e.response.text}"
            try:
                error_data = e.response.json()
                error_msg = error_data.get("error", {}).get("message", error_msg)
            except Exception:
                pass
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                response_time=response_time,
                raw_request=request_data,
                raw_response={},
                reasoning=None,
                error=error_msg,
            )

        except asyncio.CancelledError:
            response_time = time.time() - start_time
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                response_time=response_time,
                raw_request=request_data,
                raw_response={},
                reasoning=None,
                error="Cancelled",
            )

        except Exception as e:
            response_time = time.time() - start_time
            return ModelResponse(
                content="",
                prompt_tokens=0,
                completion_tokens=0,
                total_tokens=0,
                response_time=response_time,
                raw_request=request_data,
                raw_response={},
                reasoning=None,
                error=str(e),
            )

    def cancel_request(self):
        if self._cancel_event is not None:
            self._cancel_event.set()

    def list_models(self) -> tuple[List[str], Optional[str]]:
        headers = {
            "Authorization": f"Bearer {self.api_key}",
        }

        endpoints = [
            f"{self.base_url}/models",
            f"{self.base_url}/models/list",
        ]

        for endpoint in endpoints:
            try:
                with httpx.Client(verify=self.verify_ssl, timeout=30.0) as client:
                    response = client.get(endpoint, headers=headers)
                    if response.status_code == 404:
                        continue
                    response.raise_for_status()
                    data = response.json()

                    if "data" in data:
                        models = [m["id"] for m in data["data"]]
                    elif "models" in data:
                        models = [m["id"] for m in data["models"]]
                    else:
                        models = []
                    return models, None
            except httpx.HTTPStatusError as e:
                if e.response.status_code != 404:
                    return [], f"HTTP {e.response.status_code}: {e.response.text}"
            except Exception as e:
                continue

        return [], "Could not fetch models from any endpoint"
