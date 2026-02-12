#!/usr/bin/env python3

"""
AI-Powered Rego Field Mapper for Policy Rules
Dynamically maps payload_fields to input.xxx rego conditions using Gemini LLM or heuristics

Usage:
    python find_rego_fields.py "authorizing_entity"
    python find_rego_fields.py "reimbursement_ceiling" --no-gemini
    python find_rego_fields.py "distance_threshold" --gemini
"""

import os
import sys
import re
import glob
import json
from pathlib import Path
from typing import List, Dict, Tuple, Optional
from dataclasses import dataclass
from collections import defaultdict

# Optional Gemini import
try:
    import google.generativeai as genai
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False


# ANSI Colors
class Colors:
    CYAN = '\033[0;36m'
    BLUE = '\033[0;34m'
    GREEN = '\033[0;32m'
    YELLOW = '\033[1;33m'
    RED = '\033[0;31m'
    MAGENTA = '\033[0;35m'
    NC = '\033[0m'


@dataclass
class RegoField:
    """Represents a matched Rego field"""
    field_name: str
    score: int
    context: str = ""


class RegoFieldMatcher:
    """Matches payload fields to rego input.xxx fields"""
    
    def __init__(self, rego_dir: str = "opa_bundles", use_gemini: bool = True):
        self.rego_dir = rego_dir
        self.use_gemini = use_gemini and GEMINI_AVAILABLE
        self.api_key = os.environ.get('GEMINI_API_KEY') or os.environ.get('GOOGLE_API_KEY')
        
        if self.use_gemini and self.api_key:
            genai.configure(api_key=self.api_key)
            self.model = genai.GenerativeModel('gemma-3-27b-it')
        else:
            self.model = None
        
        self.all_rego_fields = self._extract_all_rego_fields()
    
    def _extract_all_rego_fields(self) -> List[str]:
        """Extract all unique input.xxx field names from rego files"""
        fields = set()
        
        for rego_file in glob.glob(f"{self.rego_dir}/**/*.rego", recursive=True):
            try:
                with open(rego_file, 'r', encoding='utf-8', errors='ignore') as f:
                    content = f.read()
                    # Find all input.fieldname patterns
                    matches = re.findall(r'input\.([a-zA-Z_][a-zA-Z0-9_]*)', content)
                    fields.update(matches)
            except Exception as e:
                print(f"Warning: Could not read {rego_file}: {e}", file=sys.stderr)
        
        return sorted(list(fields))
    
    def generate_patterns_gemini(self, payload_field: str) -> List[str]:
        """Generate regex patterns using Gemini LLM"""
        if not self.model:
            return []
        
        prompt = f"""Analyze the payload field "{payload_field}" and generate 3 optimized regex patterns (NOT full commands) that would match related input.xxx field names in policy files.

Consider:
1. Direct term matches
2. Synonyms and related concepts  
3. Semantic field families (e.g., "authority" family, "limit" family, "grade" family)
4. Common policy terminology

Return ONLY regex patterns suitable for: grep -iE 'PATTERN'
One pattern per line.
Examples for "{payload_field}":
- If "{payload_field}" is "authorizing_entity": auth|approval|designation|manager
- If "{payload_field}" is "reimbursement_ceiling": limit|ceiling|maximum|allowance|percentage
- If "{payload_field}" is "distance_threshold": distance|maximum|travel|threshold

Return 3 patterns:"""
        
        try:
            response = self.model.generate_content(prompt)
            patterns = []
            for line in response.text.strip().split('\n'):
                line = line.strip().strip('`').strip('"').strip()
                if line and not line.startswith('#'):
                    patterns.append(line)
            return patterns[:3]
        except Exception as e:
            print(f"Warning: Gemini request failed: {e}", file=sys.stderr)
            return []
    
    def generate_patterns_heuristic(self, payload_field: str) -> List[str]:
        """Generate regex patterns using heuristics"""
        payload_lower = payload_field.lower()
        keywords = '|'.join(payload_lower.split('_'))
        
        patterns = []
        
        # Semantic-based pattern selection
        if any(word in payload_lower for word in ['entity', 'authority', 'manager', 'approver', 'designation']):
            patterns.append("auth|approval|designat|grade|manager|employee")
            patterns.append("validation|authority|approver|reporter")
            patterns.append("responsible|steward|validator")
        
        elif any(word in payload_lower for word in ['ceiling', 'limit', 'maximum', 'ratio', 'amount', 'reimburs']):
            patterns.append("limit|ceiling|maximum|percentage|allowance|rate")
            patterns.append("cap|threshold|boarding|lodging")
            patterns.append("claim|benefit|reimburs|stipend")
        
        elif any(word in payload_lower for word in ['distance', 'duration', 'travel', 'threshold']):
            patterns.append("distance|maximum|travel|threshold|duration|km")
            patterns.append("day|hour|time|period|range")
            patterns.append("min|max|exceed")
        
        elif any(word in payload_lower for word in ['basis', 'disbursement', 'claim']):
            patterns.append("basis|claim|eligibility")
            patterns.append("dependency|source")
            patterns.append("type|standard")
        
        else:
            # Default: use keywords
            patterns.append(keywords)
            patterns.append(f"{keywords}|grade|level|category")
            patterns.append(f"{keywords}|rate|amount|value")
        
        return patterns
    
    def score_field(self, field_name: str, payload_field: str) -> int:
        """Calculate relevance score for a field"""
        score = 0
        f_lower = field_name.lower()
        p_lower = payload_field.lower()
        
        # Exact substring match (highest priority)
        if p_lower in f_lower:
            score += 100
            return score
        
        # Word component matches
        p_words = p_lower.split('_')
        word_matches = 0
        for word in p_words:
            if word and word in f_lower:
                score += 30
                word_matches += 1
        
        # If multiple words match, boost score
        if word_matches >= 2:
            score += 20
        
        # Semantic matching - authority/entity/manager family
        if any(w in p_lower for w in ['authority', 'entity', 'manager', 'approval', 'validator', 'designat']):
            # Prefer fields specifically about authority/approval
            if any(w in f_lower for w in ['authority', 'approval']):
                score += 60
            elif any(w in f_lower for w in ['designat', 'grade', 'employee', 'manager']):
                score += 40
        
        # Semantic matching - reimbursement/ceiling/limit/percentage family
        if any(w in p_lower for w in ['reimburs', 'ceiling']):
            # Prioritize percentage and claim-based limits
            if any(w in f_lower for w in ['percentage', 'claim']):
                score += 60
            elif any(w in f_lower for w in ['limit', 'maximum']):
                score += 50
            elif any(w in f_lower for w in ['allowance', 'rate']):
                score += 40
        
        # Semantic matching - limit/maximum/cap family
        elif any(w in p_lower for w in ['limit', 'maximum', 'cap', 'threshold']):
            if any(w in f_lower for w in ['limit', 'maximum', 'threshold']):
                score += 60
            elif any(w in f_lower for w in ['allowance', 'percentage']):
                score += 40
            elif any(w in f_lower for w in ['rate']):
                score += 30
        
        # Semantic matching - stipend/ratio/amount family
        elif any(w in p_lower for w in ['stipend', 'ratio', 'amount']):
            if any(w in f_lower for w in ['allowance', 'lodg', 'board']):
                score += 50
            elif any(w in f_lower for w in ['rate', 'percentage']):
                score += 40
        
        # Semantic matching - distance/duration/travel family
        elif any(w in p_lower for w in ['distance', 'duration', 'travel', 'threshold']):
            if any(w in f_lower for w in ['distance', 'duration', 'threshold']):
                score += 60
            elif any(w in f_lower for w in ['maximum', 'travel']):
                score += 40
            elif any(w in f_lower for w in ['day', 'time']):
                score += 30
        
        # Semantic matching - basis/disbursement/claim family
        elif any(w in p_lower for w in ['basis', 'disbursement', 'claim']):
            if any(w in f_lower for w in ['basis', 'claim']):
                score += 60
            elif any(w in f_lower for w in ['eligibility', 'dependency']):
                score += 50
            elif any(w in f_lower for w in ['source', 'type']):
                score += 40
        
        return score
    
    def get_field_context(self, field_name: str) -> str:
        """Get context line where field is used"""
        try:
            for rego_file in glob.glob(f"{self.rego_dir}/**/*.rego", recursive=True):
                with open(rego_file, 'r', encoding='utf-8', errors='ignore') as f:
                    for line in f:
                        if f"input.{field_name}" in line:
                            return line.strip()
        except Exception:
            pass
        return ""
    
    def match_fields(self, payload_field: str, top_k: int = 3) -> List[RegoField]:
        """Find top K matching rego fields for payload field"""
        
        # Generate patterns
        if self.use_gemini and self.model:
            patterns = self.generate_patterns_gemini(payload_field)
            if not patterns:
                patterns = self.generate_patterns_heuristic(payload_field)
        else:
            patterns = self.generate_patterns_heuristic(payload_field)
        
        # Match fields against patterns
        matched_fields: Dict[str, int] = {}
        
        for pattern in patterns:
            try:
                regex = re.compile(pattern, re.IGNORECASE)
                for field in self.all_rego_fields:
                    if regex.search(field):
                        score = self.score_field(field, payload_field)
                        if score > 0:
                            if field not in matched_fields or score > matched_fields[field]:
                                matched_fields[field] = score
            except re.error:
                continue
        
        # Sort by score and get top K
        sorted_fields = sorted(matched_fields.items(), key=lambda x: x[1], reverse=True)
        
        results = []
        for field_name, score in sorted_fields[:top_k]:
            context = self.get_field_context(field_name)
            results.append(RegoField(field_name=field_name, score=score, context=context))
        
        return results
    
    def print_results(self, payload_field: str, results: List[RegoField]):
        """Pretty print results"""
        print(f"\n{Colors.CYAN}╔════════════════════════════════════════════════╗{Colors.NC}")
        print(f"{Colors.CYAN}║ AI-Powered Rego Field Mapper for Policy Rules  ║{Colors.NC}")
        print(f"{Colors.CYAN}╚════════════════════════════════════════════════╝{Colors.NC}")
        print()
        print(f"{Colors.YELLOW}Payload Field:{Colors.NC} {payload_field}")
        print()
        
        mode = "Gemini AI" if (self.use_gemini and self.model) else "Heuristic"
        print(f"{Colors.MAGENTA}[Mode: {mode}]{Colors.NC}")
        print()
        
        print(f"{Colors.GREEN}═══════════════════════════════════════════════{Colors.NC}")
        print(f"{Colors.GREEN}TOP {len(results)} MATCHING REGO FIELDS{Colors.NC}")
        print(f"{Colors.GREEN}═══════════════════════════════════════════════{Colors.NC}")
        print()
        
        if not results:
            print(f"{Colors.RED}✗ No matches found for: {payload_field}{Colors.NC}")
            return
        
        for i, field in enumerate(results, 1):
            print(f"{Colors.YELLOW}[MATCH #{i}]{Colors.NC} Score: {Colors.BLUE}{field.score}{Colors.NC}")
            print(f"  Field:   {Colors.GREEN}input.{field.field_name}{Colors.NC}")
            if field.context:
                context_preview = field.context[:80]
                print(f"  Context: {Colors.CYAN}{context_preview}{Colors.NC}")
            print()
        
        # Summary
        print(f"{Colors.GREEN}═══════════════════════════════════════════════{Colors.NC}")
        print(f"{Colors.GREEN}✓ Mapping Complete{Colors.NC}")
        print(f"  Mode: {mode}")
        print(f"  Payload: {payload_field}")
        print(f"  Matched: {len(results)} top fields from rego files")
        print(f"{Colors.GREEN}═══════════════════════════════════════════════{Colors.NC}")


def main():
    """CLI interface"""
    import argparse
    
    parser = argparse.ArgumentParser(
        description="AI-Powered Rego Field Mapper for Policy Rules",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python find_rego_fields.py "authorizing_entity"
  python find_rego_fields.py "reimbursement_ceiling" --no-gemini
  python find_rego_fields.py "distance_threshold" --rego-dir ./opa_bundles
        """
    )
    
    parser.add_argument('payload_field', help='Payload field to map to rego fields')
    parser.add_argument('--no-gemini', action='store_true', help='Disable Gemini API and use heuristics')
    parser.add_argument('--rego-dir', default='opa_bundles', help='Path to opa_bundles directory')
    parser.add_argument('--top-k', type=int, default=3, help='Number of top matches to return')
    
    args = parser.parse_args()
    
    # Create matcher
    use_gemini = not args.no_gemini
    matcher = RegoFieldMatcher(rego_dir=args.rego_dir, use_gemini=use_gemini)
    
    # Find matches
    results = matcher.match_fields(args.payload_field, top_k=args.top_k)
    
    # Print results
    matcher.print_results(args.payload_field, results)
    
    # Return exit code based on results
    return 0 if results else 1


if __name__ == '__main__':
    sys.exit(main())
