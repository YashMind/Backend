# import os
# import sys
# import tiktoken
# import importlib.metadata
# import google.generativeai as genai
# import transformers
# from transformers import AutoTokenizer

# print(f"App's Python executable: {sys.executable}")
# print(f"App's sys.path: {sys.path}")

# try:
#     # Use importlib.metadata to check the version that's actually loaded
#     package_version = importlib.metadata.version("google-generativeai")
#     print(f"App's google-generativeai version: {package_version}")
# except importlib.metadata.PackageNotFoundError:
#     print("google-generativeai not found in this environment via importlib.metadata.")
# except Exception as e:
#     print(f"Could not determine app's google-generativeai version (Error: {e}).")

# def count_tokens(tool: str, model_name: str, text: str) -> int:
#     """
#     Count tokens for different LLM tools and models
#     Supports: ChatGPT, DeepSeek, Gemini
#     """
#     # ChatGPT models
#     if tool == "ChatGPT":
#         try:
#             encoder = tiktoken.encoding_for_model(model_name)
#             return len(encoder.encode(text))
#         except KeyError:
#             # Fallback for unknown models
#             encoder = tiktoken.get_encoding("cl100k_base")
#             return len(encoder.encode(text))
    
#     # DeepSeek models
#     elif tool == "DeepSeek":
#         try:
#             # Try to load a DeepSeek-specific tokenizer
#             tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/deepseek-llm-7b-base")
#             return len(tokenizer.encode(text))
#         except:
#             # Fallback to ChatGPT tokenizer (similar architecture)
#             encoder = tiktoken.get_encoding("cl100k_base")
#             return len(encoder.encode(text))
    
#     # Gemini models
#     elif tool == "Gemini":
#         # Configure API key (should be in environment)
#         genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
        
#         # Create a generative model instance
#         model = genai.GenerativeModel(model_name)
        
#         # Count tokens using Gemini's built-in method
#         return model.count_tokens( text).total_tokens
    
#     else:
#         raise ValueError(f"Unsupported tool: {tool}")


# # Unified token counter class
# class TokenCounter:
#     def __init__(self, tool: str, model_name: str):
#         self.tool = tool
#         self.model_name = model_name
        
#         # Preload tokenizers for efficiency
#         if tool == "ChatGPT":
#             try:
#                 self.encoder = tiktoken.encoding_for_model(model_name)
#             except KeyError:
#                 self.encoder = tiktoken.get_encoding("cl100k_base")
                
#         elif tool == "DeepSeek":
#             try:
#                 self.tokenizer = AutoTokenizer.from_pretrained("deepseek-ai/deepseek-llm-7b-base")
#             except:
#                 self.encoder = tiktoken.get_encoding("cl100k_base")
    
#     def count(self, text: str) -> int:
#         if self.tool == "ChatGPT":
#             return len(self.encoder.encode(text))
        
#         elif self.tool == "DeepSeek":
#             if hasattr(self, 'tokenizer'):
#                 return len(self.tokenizer.encode(text))
#             return len(self.encoder.encode(text))
        
#         elif self.tool == "Gemini":
#             genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
#             return genai.count_tokens(self.model_name, text).total_tokens