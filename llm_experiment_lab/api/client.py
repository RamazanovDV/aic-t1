import json
import time
import asyncio
from dataclasses import dataclass
from typing import Optional, List, Callable, AsyncIterator

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
        custom_api_token: str = "",
        stop: Optional[List[str]] = None,
        max_tokens: int = 0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> ModelResponse:
        if custom_endpoint:
            if "/chat/completions" in custom_endpoint or "/completions" in custom_endpoint:
                endpoint = custom_endpoint
            else:
                endpoint = f"{custom_endpoint.rstrip('/')}/chat/completions"
        else:
            endpoint = f"{self.base_url}/chat/completions"

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

        if stop:
            request_data["stop"] = stop

        if max_tokens > 0:
            request_data["max_tokens"] = max_tokens

        if frequency_penalty != 0.0:
            request_data["frequency_penalty"] = frequency_penalty

        if presence_penalty != 0.0:
            request_data["presence_penalty"] = presence_penalty

        api_token = custom_api_token if custom_api_token else self.api_key
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        print(f"[DEBUG] API Request:")
        print(f"  Custom endpoint provided: {custom_endpoint if custom_endpoint else '(none)'}")
        print(f"  Full URL: {endpoint}")
        print(f"  Model: {model}")
        print(f"  Temperature: {temperature}, Top_p: {top_p}, Top_k: {top_k}")
        print(f"  Request payload: {json.dumps(request_data, indent=2)[:500]}")
        if stop:
            print(f"  Stop sequences: {stop}")
        if max_tokens > 0:
            print(f"  Max tokens: {max_tokens}")
        if frequency_penalty != 0.0:
            print(f"  Frequency penalty: {frequency_penalty}")
        if presence_penalty != 0.0:
            print(f"  Presence penalty: {presence_penalty}")
        print(f"  System prompt length: {len(system_prompt)}")
        print(f"  User prompt length: {len(user_prompt)}")

        start_time = time.time()

        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()

        try:
            async with httpx.AsyncClient(verify=self.verify_ssl, timeout=120.0, follow_redirects=True) as client:
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
            error_msg = f"HTTP {e.response.status_code}: {e.response.text} (URL: {endpoint})"
            print(f"[DEBUG] HTTP Error: {e.response.status_code}")
            print(f"  Response body: {e.response.text}")
            print(f"  Request URL: {endpoint}")
            print(f"  Request model: {model}")
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
            print(f"[DEBUG] Exception: {type(e).__name__}: {str(e)}")
            print(f"  Request endpoint: {endpoint}")
            print(f"  Request model: {model}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
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

    async def chat_completion_stream(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float = 0.7,
        top_p: float = 1.0,
        top_k: int = -1,
        custom_endpoint: str = "",
        custom_api_token: str = "",
        stop: Optional[List[str]] = None,
        max_tokens: int = 0,
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
        on_chunk: Optional[Callable[[str, str], None]] = None,
    ) -> ModelResponse:
        if custom_endpoint:
            if "/chat/completions" in custom_endpoint or "/completions" in custom_endpoint:
                endpoint = custom_endpoint
            else:
                endpoint = f"{custom_endpoint.rstrip('/')}/chat/completions"
        else:
            endpoint = f"{self.base_url}/chat/completions"

        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ]

        request_data = {
            "model": model,
            "messages": messages,
            "temperature": temperature,
            "top_p": top_p,
            "stream": True,
        }

        if top_k > 0:
            request_data["top_k"] = top_k

        if stop:
            request_data["stop"] = stop

        if max_tokens > 0:
            request_data["max_tokens"] = max_tokens

        if frequency_penalty != 0.0:
            request_data["frequency_penalty"] = frequency_penalty

        if presence_penalty != 0.0:
            request_data["presence_penalty"] = presence_penalty

        api_token = custom_api_token if custom_api_token else self.api_key
        headers = {
            "Authorization": f"Bearer {api_token}",
            "Content-Type": "application/json",
        }

        start_time = time.time()

        if self._cancel_event is None:
            self._cancel_event = asyncio.Event()

        accumulated_content = []
        accumulated_reasoning = []
        total_completion_tokens = 0

        try:
            async with httpx.AsyncClient(
                verify=self.verify_ssl, 
                timeout=httpx.Timeout(120.0, connect=30.0), 
                follow_redirects=True
            ) as client:
                self._cancel_event.clear()
                
                async with client.stream("POST", endpoint, json=request_data, headers=headers) as response:
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
                    
                    cancelled = False
                    total_completion_tokens = 0
                    prompt_tokens_from_stream = 0
                    async for line in response.aiter_lines():
                        if self._cancel_event.is_set():
                            cancelled = True
                            break
                        
                        if not line.strip() or not line.startswith("data: "):
                            continue
                        
                        if line.strip() == "data: [DONE]":
                            break
                        
                        try:
                            data = json.loads(line[6:])
                        except json.JSONDecodeError:
                            continue
                        
                        choices = data.get("choices", [])
                        if not choices:
                            continue
                        
                        delta = choices[0].get("delta", {})
                        content_chunk = delta.get("content", "")
                        reasoning_chunk = delta.get("reasoning_content", "") or delta.get("thinking", "")
                        
                        if content_chunk or reasoning_chunk:
                            accumulated_content.append(content_chunk)
                            if reasoning_chunk:
                                accumulated_reasoning.append(reasoning_chunk)
                            if on_chunk:
                                on_chunk(content_chunk, reasoning_chunk)
                        
                        if "usage" in data:
                            total_completion_tokens = data["usage"].get("completion_tokens", 0)
                            prompt_tokens_from_stream = data["usage"].get("prompt_tokens", 0)
                    
                    if cancelled:
                        await response.aclose()
                        response_time = time.time() - start_time
                        return ModelResponse(
                            content="".join(accumulated_content),
                            prompt_tokens=prompt_tokens_from_stream,
                            completion_tokens=total_completion_tokens,
                            total_tokens=prompt_tokens_from_stream + total_completion_tokens,
                            response_time=response_time,
                            raw_request=request_data,
                            raw_response={},
                            reasoning="".join(accumulated_reasoning) if accumulated_reasoning else None,
                            error="Cancelled",
                        )

            response_time = time.time() - start_time

            return ModelResponse(
                content="".join(accumulated_content),
                prompt_tokens=prompt_tokens_from_stream,
                completion_tokens=total_completion_tokens,
                total_tokens=prompt_tokens_from_stream + total_completion_tokens,
                response_time=response_time,
                raw_request=request_data,
                raw_response={
                    "streaming": True,
                    "usage": {
                        "prompt_tokens": prompt_tokens_from_stream,
                        "completion_tokens": total_completion_tokens,
                        "total_tokens": prompt_tokens_from_stream + total_completion_tokens,
                    },
                    "response_time": response_time,
                    "content": "".join(accumulated_content),
                    "reasoning": "".join(accumulated_reasoning) if accumulated_reasoning else None,
                },
                reasoning="".join(accumulated_reasoning) if accumulated_reasoning else None,
            )

        except httpx.HTTPStatusError as e:
            response_time = time.time() - start_time
            error_msg = f"HTTP {e.response.status_code}: {e.response.text} (URL: {endpoint})"
            print(f"[DEBUG] HTTP Error: {e.response.status_code}")
            print(f"  Response body: {e.response.text}")
            print(f"  Request URL: {endpoint}")
            print(f"  Request model: {model}")
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
                content="".join(accumulated_content),
                prompt_tokens=0,
                completion_tokens=total_completion_tokens,
                total_tokens=total_completion_tokens,
                response_time=response_time,
                raw_request=request_data,
                raw_response={},
                reasoning="".join(accumulated_reasoning) if accumulated_reasoning else None,
                error="Cancelled",
            )

        except Exception as e:
            response_time = time.time() - start_time
            print(f"[DEBUG] Exception: {type(e).__name__}: {str(e)}")
            print(f"  Request endpoint: {endpoint}")
            print(f"  Request model: {model}")
            import traceback
            print(f"  Traceback: {traceback.format_exc()}")
            return ModelResponse(
                content="".join(accumulated_content),
                prompt_tokens=0,
                completion_tokens=total_completion_tokens,
                total_tokens=total_completion_tokens,
                response_time=response_time,
                raw_request=request_data,
                raw_response={},
                reasoning="".join(accumulated_reasoning) if accumulated_reasoning else None,
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
                with httpx.Client(verify=self.verify_ssl, timeout=30.0, follow_redirects=True) as client:
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
