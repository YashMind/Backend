# 1. Custom DeepSeek Embeddings Class
import os
import requests
from typing import List, Union
from langchain_core.embeddings import Embeddings
from langchain_core.language_models.llms import BaseLLM
from langchain_core.messages import HumanMessage, AIMessage


class DeepSeekEmbeddings(Embeddings):
    """DeepSeek embedding model implementation"""
    def __init__(self, model_name: str = "deepseek-embedding", api_key: str = None):
        self.model_name = model_name
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API key not provided and not found in environment variables")
        
        self.base_url = "https://api.deepseek.com/v1"
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

    def embed_query(self, text: str) -> List[float]:
        """Embed a single query text"""
        return self._embed([text])[0]

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Embed multiple documents"""
        return self._embed(texts)

    def _embed(self, texts: List[str]) -> List[List[float]]:
        """Internal method to call DeepSeek embedding API"""
        payload = {
            "input": texts,
            "model": self.model_name
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/embeddings",
                headers=self.headers,
                json=payload,
                timeout=30
            )
            response.raise_for_status()
            data = response.json()
            return [item["embedding"] for item in data["data"]]
        except requests.exceptions.RequestException as e:
            print(f"DeepSeek API error: {str(e)}")
            raise
        except (KeyError, IndexError) as e:
            print(f"Response parsing error: {str(e)}")
            raise
    
    @property
    def _embedding_type(self) -> str:
        return "deepseek"


class DeepSeekLLM(BaseLLM):
    """DeepSeek language model implementation"""
    model_name: str = "deepseek-chat"
    temperature: float = 0.2
    max_tokens: int = 2048
    api_key: str = None
    base_url: str = "https://api.deepseek.com/v1" 
    headers: dict = None
    def __init__(self, model_name: str, temperature: float, api_key: str = None):
        super().__init__()
        self.model_name = model_name
        self.temperature = temperature
        self.api_key = api_key or os.getenv("DEEPSEEK_API_KEY")
        if not self.api_key:
            raise ValueError("DeepSeek API key not provided and not found in environment variables")
        
        self.headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
    
    def _generate(self, messages: list, **kwargs) -> str:
        """Generate response from DeepSeek API"""
        payload = {
            "model": self.model_name,
            "messages": messages,
            "temperature": self.temperature,
            "max_tokens": self.max_tokens,
            **kwargs
        }
        
        try:
            response = requests.post(
                f"{self.base_url}/chat/completions",
                headers=self.headers,
                json=payload,
                timeout=30
            )

            # Handle 402 Payment Required explicitly
            if response.status_code == 402:
                error_msg = "Payment Required. Please check your DeepSeek API billing status."
                print(error_msg)
                return error_msg

            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]
        except requests.exceptions.RequestException as e:
            print(f"DeepSeek API error: {str(e)}")
            raise
        except (KeyError, IndexError) as e:
            print(f"Response parsing error: {str(e)}")
            raise
    
    def invoke(self, input: Union[str, list], **kwargs) -> str:
        """Handle both single messages and conversation history"""
        if isinstance(input, str):
            messages = [{"role": "user", "content": input}]
        elif isinstance(input, list):
            messages = []
            for msg in input:
                if isinstance(msg, HumanMessage):
                    messages.append({"role": "user", "content": msg.content})
                elif isinstance(msg, AIMessage):
                    messages.append({"role": "assistant", "content": msg.content})
        else:
            raise TypeError("Input must be str or list of messages")
            
        return self._generate(messages, **kwargs)
    
    @property
    def _llm_type(self) -> str:
        return "deepseek"
