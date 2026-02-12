#!/bin/bash

# Dynamic Rego Field Matcher with Gemini LLM-Generated Grep Patterns
# Intelligently maps payload_fields to input.xxx rego conditions using AI
#
# Usage: ./find_rego_fields.sh "payload_field_name" [use_gemini]
# Examples:
#   ./find_rego_fields.sh "authorizing_entity"
#   ./find_rego_fields.sh "reimbursement_ceiling" true
#   ./find_rego_fields.sh "distance_threshold" false

set -euo pipefail

PAYLOAD_FIELD="${1:?ERROR: Provide payload_field as argument}"
USE_GEMINI="${2:-true}"
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Colors
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
MAGENTA='\033[0;35m'
CYAN='\033[0;36m'
NC='\033[0m'

# Generate Gemini-powered grep patterns
generate_gemini_patterns() {
    python3 << 'GEMINI_PY'
import os, sys, json
try:
    import google.generativeai as genai
    api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
    if not api_key:
        sys.exit(1)
    
    genai.configure(api_key=api_key)
    model = genai.GenerativeModel('gemma-3-27b-it')
    
    payload = sys.argv[1]
    prompt = f"""Analyze the payload field "{payload}" and generate 3 optimized grep regex patterns (NOT full commands) that would match related input.xxx field names in policy files.

Consider:
1. Direct term matches
2. Synonyms and related concepts  
3. Semantic field families (e.g., "authority" family, "limit" family, "grade" family)
4. Common policy terminology

Return ONLY regex patterns suitable for: grep -iE 'PATTERN'
One pattern per line.
Examples for "{payload}":
- If "{payload}" is "authorizing_entity": auth|approval|designation|manager
- If "{payload}" is "reimbursement_ceiling": limit|ceiling|maximum|allowance|percentage
- If "{payload}" is "distance_threshold": distance|maximum|travel|threshold

Return 3 patterns:"""
    
    response = model.generate_content(prompt)
    patterns = []
    for line in response.text.strip().split('\n'):
        line = line.strip().strip('`').strip('"')
        if line and not line.startswith('#'):
            patterns.append(line)
    
    for p in patterns[:3]:
        print(p)
except Exception as e:
    sys.exit(1)
GEMINI_PY
}

# Generate heuristic patterns based on payload_field
generate_heuristic_patterns() {
    local payload="$1"
    local payload_lower="${payload,,}"
    
    # Extract keywords  
    local keywords=$(echo "$payload_lower" | tr '_' '|')
    
    # Generate patterns based on semantic understanding
    case "$payload_lower" in
        *entity*|*authority*|*manager*|*approver*)
            echo "auth|approval|designation|grade|manager|employee"
            echo "validation|authority|approver|reporter"
            echo "responsible|steward|validator"
            ;;
        *ceiling*|*limit*|*maximum*|*ratio*|*amount*)
            echo "limit|ceiling|maximum|percentage|allowance|rate"
            echo "cap|threshold|boarding|lodging"
            echo "claim|benefit|reimburs|stipend"
            ;;
        *distance*|*duration*|*travel*|*threshold*)
            echo "distance|maximum|travel|threshold|duration|km"
            echo "day|hour|time|period|range"
            echo "min|max|exceed"
            ;;
        *)
            # Default: use keywords
            echo "$keywords"
            echo "$keywords|grade|level|category"
            echo "$keywords|rate|amount|value"
            ;;
    esac
}

# Score field relevance
score_field() {
    local field="$1"
    local target="$2"
    local score=0
    local f_lower="${field,,}"
    local t_lower="${target,,}"
    
    # Exact substring
    if [[ "$f_lower" == *"$t_lower"* ]]; then
        score=$((score + 100))
    fi
    
    # Word component matches
    IFS='_' read -ra target_words <<< "$t_lower"
    for word in "${target_words[@]}"; do
        if [[ -n "$word" ]] && [[ "$f_lower" == *"$word"* ]]; then
            score=$((score + 25))
        fi
    done
    
    # Semantic matching
    if [[ "$t_lower" =~ (authority|entity|manager|approval|validator|designat) ]]; then
        if [[ "$f_lower" =~ (authority|approval|designat|grade|employee|manager) ]]; then
            score=$((score + 40))
        fi
    fi
    
    if [[ "$t_lower" =~ (ceiling|limit|maximum|stipend|ratio|amount|reimburs) ]]; then
        if [[ "$f_lower" =~ (limit|maximum|allowance|percentage|rate|lodg|board|claim) ]]; then
            score=$((score + 40))
        fi
    fi
    
    if [[ "$t_lower" =~ (distance|duration|travel|threshold) ]]; then
        if [[ "$f_lower" =~ (distance|duration|maximum|travel|day|threshold) ]]; then
            score=$((score + 40))
        fi
    fi
    
    echo "$score"
}

# Main execution
echo -e "${CYAN}╔════════════════════════════════════════════════╗${NC}"
echo -e "${CYAN}║ AI-Powered Rego Field Mapper for Policy Rules  ║${NC}"
echo -e "${CYAN}╚════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "${YELLOW}Payload Field:${NC} $PAYLOAD_FIELD"
echo ""

cd "$SCRIPT_DIR"

# Generate patterns
MODE="Heuristic"
if [[ "$USE_GEMINI" == "true" ]] && python3 -c "import google.generativeai" 2>/dev/null && [[ -n "${GEMINI_API_KEY:-}${GOOGLE_API_KEY:-}" ]]; then
    echo -e "${MAGENTA}[Mode: Gemini AI]${NC}"
    MODE="Gemini AI"
    patterns=$(generate_gemini_patterns "$PAYLOAD_FIELD" 2>/dev/null || generate_heuristic_patterns "$PAYLOAD_FIELD")
else
    echo -e "${MAGENTA}[Mode: Heuristic]${NC}"
    patterns=$(generate_heuristic_patterns "$PAYLOAD_FIELD")
fi

echo -e "${YELLOW}Generated Regex Patterns:${NC}"
count=1
while IFS= read -r pattern; do
    [[ -z "$pattern" ]] && continue
    echo "  Pattern $count: ${BLUE}$pattern${NC}"
    count=$((count + 1))
done <<< "$patterns"
echo ""

# Collect matching fields
temp_file=$(mktemp)
trap "rm -f $temp_file" EXIT

echo -e "${YELLOW}Searching for matching fields...${NC}"
echo ""

while IFS= read -r pattern; do
    [[ -z "$pattern" ]] && continue
    
    # Execute grep with pattern
    while IFS= read -r field; do
        [[ -z "$field" ]] && continue
        
        field="${field#input.}"
        
        # Get context (first matching line from rego)
        context=$(grep -h "input\.$field" opa_bundles/**/*.rego 2>/dev/null | head -1 | xargs || echo "")
        
        # Score
        score=$(score_field "$field" "$PAYLOAD_FIELD")
        
        if (( score > 0 )); then
            echo "$score|input.$field|$context"
        fi
    done < <(grep -roh 'input\.[a-zA-Z_][a-zA-Z0-9_]*' opa_bundles/ --include='*.rego' 2>/dev/null | sort -u | grep -iE "$pattern")
done <<< "$patterns" >> "$temp_file"

# Display results
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}TOP 3 MATCHING REGO FIELDS${NC}"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo ""

if [[ ! -s "$temp_file" ]]; then
    echo -e "${RED}✗ No matches found for: $PAYLOAD_FIELD${NC}"
    exit 1
fi

# Sort by score, deduplicate by field, get top 3
sort -t'|' -k1 -rn "$temp_file" | awk -F'|' '!seen[$2]++' | head -3 | while IFS='|' read -r score field context; do
    echo -e "${YELLOW}[MATCH]${NC} Score: ${BLUE}$score${NC}"
    echo -e "  Field:   ${GREEN}$field${NC}"
    echo -e "  Context: ${CYAN}${context:0:80}${NC}"
    echo ""
done

# Summary
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
echo -e "${GREEN}✓ Mapping Complete${NC}"
echo -e "  Mode: $MODE"
echo -e "  Payload: $PAYLOAD_FIELD"
echo -e "  Matched: 3 top fields from rego files"
echo -e "${GREEN}═══════════════════════════════════════════════${NC}"
