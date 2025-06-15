import google.generativeai as genai
import os

# Set your API key for testing (replace with your actual key or ensure env var is set)
# os.environ["GOOGLE_API_KEY"] = "YOUR_API_KEY" 


try:
    genai.configure(api_key=os.getenv("GOOGLE_API_KEY"))
    for m in genai.list_models():
        if "countTokens" in m.supported_generation_methods:
            print(m.name)
    model_name = "models/gemini-2.5-flash-preview-05-20"  # Or any other Gemini model you're using
    text_to_count = "This is a test string to count tokens."

    model = genai.GenerativeModel(model_name)
    print(f"Model object type: {type(model)}")

    # This is the line that should work
    token_count = model.count_tokens(text_to_count).total_tokens
    print(f"Successfully counted tokens: {token_count}")

except Exception as e:
    print(f"An error occurred: {e}")

# Add these lines to check your environment again
import sys
print(f"Python executable being used: {sys.executable}")
print(f"google-generativeai version in this environment:")
try:
    import pkg_resources
    print(pkg_resources.get_distribution("google-generativeai").version)
except Exception:
    print("Could not determine version using pkg_resources.")