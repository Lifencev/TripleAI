import os
from dotenv import load_dotenv

# 1. Load the variables from the .env file into your environment
load_dotenv()

# 2. Assign them to standard Python variables (snake_case)
gemma_4_api_key = os.getenv("SPUR_GEMMA_4_KEY")
gemma_3_api_key = os.getenv("SPUR_GEMMA_3_MM_KEY")

KAGGLE_USERNAME = os.getenv("KAGGLE_USERNAME")
KAGGLE_KEY = os.getenv("KAGGLE_KEY")

# 3. Test that they loaded correctly (Delete or comment out in production!)
print(f"Gemma 4 Key loaded: {bool(gemma_4_api_key)}")
print(f"Gemma 3 MM Key loaded: {bool(gemma_3_api_key)}")

print(f"KAGGLE_USERNAME loaded: {bool(KAGGLE_USERNAME)}")
print(f"KAGGLE_KEY loaded: {bool(KAGGLE_KEY)}")
