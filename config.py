import os

# Local LM Studio / Local LLM configuration
LOCAL_LLM_URL = os.getenv("LOCAL_LLM_URL", "http://localhost:1234/v1")
LOCAL_MODEL_NAME = os.getenv("LOCAL_MODEL_NAME", "qwen2.5-35b-instruct")

# Local Hindsight endpoint
HINDSIGHT_API_URL = os.getenv("HINDSIGHT_API_URL", "http://localhost:8080")
HINDSIGHT_BANK_ID = os.getenv("HINDSIGHT_BANK_ID", "sentrymind-devops")
