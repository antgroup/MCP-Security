import requests
import logging
from typing import List, Dict
import os
from openai import OpenAI

def extract_after_think(text: str) -> str:
    parts = text.split("</think>")
    return parts[1].strip() if len(parts) > 1 else text

class LLMClient:
    def __init__(self) -> None:
        self.model = "deepseek-chat"
        api_key_ = os.getenv("DEEPSEEK_API_KEY")
        if not api_key_:
            raise EnvironmentError(
                "DEEPSEEK_API_KEY environment variable is not set.\n"
                "Please set your API key using the following command:\n"
                'export DEEPSEEK_API_KEY="your_actual_api_key_here"'
            )
        self.client = OpenAI(api_key=api_key_, base_url="https://api.deepseek.com")


    def get_response(self, messages: List[Dict[str, str]]) -> str:
        response = self.client.chat.completions.create(
            model=self.model,
            messages=messages,
            stream=False
        )

        return response.choices[0].message.content