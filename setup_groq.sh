#!/bin/bash
# =============================================================================
# Groq API Setup Script for Policy Validator
# =============================================================================
# This script sets up Groq API integration for the policy validator.
# Groq provides free access to Llama 3.3 70B - faster and no quota limits!
# =============================================================================

set -e

echo "=============================================="
echo "  Groq API Setup for Policy Validator"
echo "=============================================="
echo ""

# Step 1: Install Groq package
echo "[1/4] Installing Groq Python package..."
pip install groq -q
echo "✅ Groq package installed"
echo ""

# Step 2: Get API Key
echo "[2/4] Getting Groq API Key..."
echo ""
echo "To get your free Groq API key:"
echo "  1. Go to: https://console.groq.com/"
echo "  2. Sign up for a free account"
echo "  3. Click 'Create API Key'"
echo "  4. Copy your API key"
echo ""
read -p "Enter your Groq API key: " GROQ_API_KEY

if [ -z "$GROQ_API_KEY" ]; then
    echo "❌ No API key entered. Please get a free key from https://console.groq.com/"
    exit 1
fi

echo "✅ API key received"
echo ""

# Step 3: Update policy_validator.py with the API key
echo "[3/4] Updating policy_validator.py..."
sed -i "s|GROQ_API_KEY = \"gsk_your_groq_api_key_here\"|GROQ_API_KEY = \"$GROQ_API_KEY\"|g" policy_validator.py
echo "✅ API key configured"
echo ""

# Step 4: Test the integration
echo "[4/4] Testing Groq integration..."
python3 -c "
from groq import Groq
client = Groq(api_key='$GROQ_API_KEY')
chat_completion = client.chat.completions.create(
    messages=[{'role': 'user', 'content': 'Say hello'}],
    model='llama-3.3-70b-versatile',
    max_tokens=10
)
print(f'✅ Groq API working! Response: {chat_completion.choices[0].message.content}')
"
echo ""
echo "=============================================="
echo "  Setup Complete!"
echo "=============================================="
echo ""
echo "Now you can use Groq instead of Gemini for:"
echo "  - Intent Classification (Stage 2)"
echo "  - Entity Extraction (Stage 3)"
echo "  - Ambiguity Clarification (Stage 5)"
echo ""
echo "Benefits of Groq:"
echo "  ✅ No rate limits"
echo "  ✅ Faster inference"
echo "  ✅ Free tier available"
echo "  ✅ Llama 3.3 70B quality rivals Claude 3.5 Sonnet"
echo ""
echo "To switch back to Gemini, edit policy_validator.py and set:"
echo "  PipelineConfig.LLM_PROVIDER = 'gemini'"
echo ""
