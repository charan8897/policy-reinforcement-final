#!/usr/bin/env python3
"""
REFACTORED: Policy-Agnostic Stages 3, 4, 6
Completely generic implementations that work for ANY policy domain.

Stage 3: Dynamic Entity Extraction (generic, policy-neutral)
Stage 4: Policy-Agnostic Ambiguity Detection (generic rules)
Stage 6: Dynamic DSL Generation (auto-inferred fact namespace)
"""

import json
import re
from typing import Dict, List, Tuple, Optional, Any
from enum import Enum
from collections import defaultdict

# =============================================================================
# STAGE 3: POLICY-AGNOSTIC ENTITY EXTRACTION
# =============================================================================

class EntityType(Enum):
    """Generic entity types that apply across all policies"""
    NUMERIC_VALUE = "numeric_value"          # Any number: 200, 50, 25%, 3.5
    NUMERIC_RANGE = "numeric_range"          # Range: 1-10, between 100-200
    MONETARY = "monetary"                     # Amounts: $100, Rs 500
    DURATION = "duration"                     # Time: 2 days, 6 hours, 4 weeks
    CATEGORICAL = "categorical"               # Enums: yes/no, Senior/Junior, Personal/Company
    PERCENTAGE = "percentage"                 # Percentages: 25%, 125%
    ROLE = "role"                             # Any job title/role
    ENTITY_REFERENCE = "entity_reference"     # Person/org: "John", "HR Team"
    THRESHOLD = "threshold"                   # Thresholds: "maximum", "minimum", "up to"
    CONDITION = "condition"                   # Logical conditions: IF/THEN, when, provided
    EXCLUSION = "exclusion"                   # What's excluded: "except", "other than"


class GenericEntityExtractor:
    """
    Stage 3 REFACTORED: Policy-agnostic entity extraction.
    
    Strategy:
    1. Extract by PATTERN (regex for numbers, ranges, percentages, durations)
    2. Extract by CONTEXT (words that indicate entity types)
    3. Classify into generic entity types
    4. NO hardcoded schema, NO travel-specific examples
    
    Returns: Dynamic entity list with types, not hardcoded field names
    """
    
    # Generic patterns (work for ANY policy)
    PATTERNS = {
        'numeric': r'\b(\d+(?:\.\d+)?)\b',
        'percentage': r'\b(\d+(?:\.\d+)?)\s*%',
        'monetary': r'(?:[$£€₹]|Rs|USD|INR)\s*(\d+(?:,\d{3})*(?:\.\d+)?)',
        'duration_days': r'(\d+(?:\.\d+)?)\s*(?:day|days)',
        'duration_hours': r'(\d+(?:\.\d+)?)\s*(?:hour|hours?)',
        'duration_weeks': r'(\d+(?:\.\d+)?)\s*(?:week|weeks)',
        'duration_months': r'(\d+(?:\.\d+)?)\s*(?:month|months)',
        'duration_years': r'(\d+(?:\.\d+)?)\s*(?:year|years)',
        'range': r'(\d+)\s*(?:to|-|through)\s*(\d+)',
        'time': r'(\d{1,2}):(\d{2})\s*(?:AM|PM|am|pm)?',
    }
    
    # Generic context keywords (work for ANY policy)
    CONTEXT_KEYWORDS = {
        'threshold': ['maximum', 'minimum', 'at least', 'at most', 'no more than', 'no less than',
                     'exceeding', 'up to', 'not exceeding', 'not less than', 'between'],
        'condition': ['if', 'when', 'provided', 'unless', 'except', 'in case', 'whenever', 
                     'if and only if', 'only if'],
        'requirement': ['must', 'shall', 'required', 'mandatory', 'compulsory'],
        'allowance': ['may', 'can', 'allowed', 'permitted', 'eligible', 'entitled'],
        'exclusion': ['except', 'other than', 'excluding', 'not including', 'excluding'],
        'role': ['employee', 'manager', 'officer', 'director', 'staff', 'personnel', 'member'],
    }
    
    def __init__(self):
        self.extracted_types = defaultdict(list)  # Track what types were found
    
    def extract_entities(self, clause_text: str) -> Dict[str, List[Dict]]:
        """
        Extract all entities from clause using generic patterns.
        
        Returns:
        {
            "numeric_values": [{"value": "200", "unit": "kms", "context": "travel distance"}],
            "percentages": [{"value": "25%", "base": "eligible amount"}],
            "durations": [{"value": "2", "unit": "days"}],
            "categorical": [{"value": "Senior", "category": "employee level"}],
            "roles": [{"value": "Reporting Manager"}],
            "thresholds": [{"type": "maximum", "value": "200"}],
            "conditions": [...],
            "exclusions": [...]
        }
        """
        
        entities = defaultdict(list)
        text_lower = clause_text.lower()
        
        # 1. Extract percentages
        percentages = re.findall(self.PATTERNS['percentage'], clause_text)
        for pct in percentages:
            entities['percentages'].append({
                'value': f"{pct}%",
                'numeric_value': float(pct),
                'context': self._extract_context_around(clause_text, f"{pct}%")
            })
        
        # 2. Extract monetary values
        monetary = re.findall(self.PATTERNS['monetary'], clause_text)
        for amount in monetary:
            cleaned = amount.replace(',', '')
            entities['monetary'].append({
                'value': amount,
                'numeric_value': float(cleaned),
                'currency': self._detect_currency(clause_text, amount),
                'context': self._extract_context_around(clause_text, amount)
            })
        
        # 3. Extract durations
        entities['durations'] = self._extract_durations(clause_text)
        
        # 4. Extract numeric ranges
        ranges = re.findall(self.PATTERNS['range'], clause_text)
        for start, end in ranges:
            entities['ranges'].append({
                'start': int(start),
                'end': int(end),
                'unit': self._detect_unit_after(clause_text, f"{start}.*{end}"),
                'context': self._extract_context_around(clause_text, f"{start}.*{end}")
            })
        
        # 5. Extract plain numeric values (not percentages, not in ranges)
        numerics = re.findall(self.PATTERNS['numeric'], clause_text)
        for num in numerics:
            # Skip if already in percentages or durations
            if f"{num}%" not in clause_text and num not in [str(r[0]) for r in ranges]:
                unit = self._detect_unit_after(clause_text, num)
                entities['numeric_values'].append({
                    'value': num,
                    'numeric_value': float(num),
                    'unit': unit,
                    'context': self._extract_context_around(clause_text, num)
                })
        
        # 6. Extract thresholds (by context keyword)
        for threshold_type, keywords in self.CONTEXT_KEYWORDS.items():
            if threshold_type == 'threshold':
                for keyword in keywords:
                    if keyword in text_lower:
                        # Find what value follows this keyword
                        pattern = f"(?:{keyword}).*?(\d+(?:\.\d+)?)"
                        matches = re.finditer(pattern, clause_text, re.IGNORECASE)
                        for match in matches:
                            entities['thresholds'].append({
                                'type': keyword,
                                'value': match.group(1),
                                'unit': self._detect_unit_after(clause_text, match.group(1)),
                                'context': self._extract_context_around(clause_text, match.group(0))
                            })
        
        # 7. Extract conditions (IF/THEN patterns)
        conditions = self._extract_conditions(clause_text)
        entities['conditions'] = conditions
        
        # 8. Extract categorical values (capitalized words that are not entities)
        categoricals = self._extract_categoricals(clause_text)
        entities['categorical'] = categoricals
        
        # 9. Extract roles (from context keyword matching)
        roles = self._extract_roles(clause_text)
        entities['roles'] = roles
        
        # 10. Extract exclusions
        exclusions = self._extract_exclusions(clause_text)
        entities['exclusions'] = exclusions
        
        return dict(entities)
    
    def _extract_durations(self, text: str) -> List[Dict]:
        """Extract all duration values (days, hours, weeks, months, years)"""
        durations = []
        
        duration_patterns = [
            ('days', self.PATTERNS['duration_days']),
            ('hours', self.PATTERNS['duration_hours']),
            ('weeks', self.PATTERNS['duration_weeks']),
            ('months', self.PATTERNS['duration_months']),
            ('years', self.PATTERNS['duration_years']),
        ]
        
        for unit, pattern in duration_patterns:
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                durations.append({
                    'value': match.group(1),
                    'unit': unit,
                    'context': self._extract_context_around(text, match.group(0))
                })
        
        return durations
    
    def _extract_conditions(self, text: str) -> List[Dict]:
        """Extract conditional logic (IF/THEN, when, provided, etc.)"""
        conditions = []
        
        # IF/THEN pattern
        if_then = re.finditer(r'(?:if|when|provided)\s+(.+?)(?:then|must|shall|can|will)\s+(.+?)(?:\.|,|$)', text, re.IGNORECASE)
        for match in if_then:
            conditions.append({
                'type': 'conditional',
                'condition': match.group(1).strip(),
                'consequence': match.group(2).strip()
            })
        
        return conditions
    
    def _extract_categoricals(self, text: str) -> List[Dict]:
        """Extract categorical values (enums, classifications)"""
        categoricals = []
        
        # Capitalized words that appear in lists or after "such as"
        list_pattern = r'(?:such as|including|like|categories?|types?|kinds?|classes?)\s+([A-Z][a-zA-Z\s,&/-]+)'
        matches = re.finditer(list_pattern, text)
        for match in matches:
            items = [i.strip() for i in match.group(1).split(',')]
            for item in items:
                if len(item) > 2:  # Skip single letters
                    categoricals.append({
                        'value': item,
                        'category_type': 'list_item',
                        'context': self._extract_context_around(text, match.group(0))
                    })
        
        return categoricals
    
    def _extract_roles(self, text: str) -> List[Dict]:
        """Extract role/position names"""
        roles = []
        
        role_context = ['by', 'approved', 'authorized', 'under', 'by the']
        
        for context in role_context:
            pattern = f"{context}\\s+([A-Z][a-zA-Z\\s&/-]+?)(?:\\.|,|and|or|$)"
            matches = re.finditer(pattern, text, re.IGNORECASE)
            for match in matches:
                role = match.group(1).strip()
                if any(role_kw in role.lower() for role_kw in ['manager', 'officer', 'director', 'staff', 'personnel', 'head', 'lead']):
                    roles.append({
                        'value': role,
                        'context': context
                    })
        
        return roles
    
    def _extract_exclusions(self, text: str) -> List[Dict]:
        """Extract what is excluded (other than, except, excluding)"""
        exclusions = []
        
        exclusion_pattern = r'(?:except|other than|excluding|not including|not applicable to|excluding)\s+([A-Za-z\s,&/-]+?)(?:\.|,|;|$)'
        matches = re.finditer(exclusion_pattern, text, re.IGNORECASE)
        for match in matches:
            excluded = match.group(1).strip()
            exclusions.append({
                'type': 'exclusion',
                'value': excluded,
                'context': self._extract_context_around(text, match.group(0))
            })
        
        return exclusions
    
    def _detect_unit_after(self, text: str, value_str: str) -> Optional[str]:
        """Detect unit that comes after a numeric value"""
        idx = text.find(value_str)
        if idx == -1:
            return None
        
        # Look ahead 20 chars for unit keywords
        after_text = text[idx + len(value_str):idx + len(value_str) + 20].lower()
        
        unit_patterns = [
            ('kms', r'km[s]?'),
            ('hours', r'hour[s]?'),
            ('days', r'day[s]?'),
            ('weeks', r'week[s]?'),
            ('months', r'month[s]?'),
            ('percent', r'%|percent'),
            ('employees', r'employee[s]?'),
            ('people', r'people|persons?'),
            ('items', r'item[s]?'),
        ]
        
        for unit_name, unit_pattern in unit_patterns:
            if re.search(unit_pattern, after_text):
                return unit_name
        
        return None
    
    def _extract_context_around(self, text: str, substring: str, window: int = 30) -> str:
        """Extract context around a substring"""
        idx = text.find(substring)
        if idx == -1:
            return ""
        
        start = max(0, idx - window)
        end = min(len(text), idx + len(substring) + window)
        
        return text[start:end].strip()
    
    def _detect_currency(self, text: str, amount: str) -> str:
        """Detect currency symbol/code before amount"""
        idx = text.find(amount)
        if idx > 0:
            before = text[max(0, idx - 5):idx]
            if '$' in before:
                return 'USD'
            elif '₹' in before or 'Rs' in before:
                return 'INR'
            elif '€' in before:
                return 'EUR'
            elif '£' in before:
                return 'GBP'
        return 'UNKNOWN'


# =============================================================================
# STAGE 4: POLICY-AGNOSTIC AMBIGUITY DETECTION
# =============================================================================

class GenericAmbiguityDetector:
    """
    Stage 4 REFACTORED: Policy-agnostic ambiguity detection.
    
    Ambiguity rules:
    1. Vague language (should, may, appropriate) without thresholds
    2. Undefined references (approval, authority without specification)
    3. Incomplete conditions (IF without THEN)
    4. Open-ended language (etc., and so on, others)
    5. Numbers without units
    6. Missing baselines for percentages
    
    These rules work for ANY policy.
    """
    
    VAGUE_KEYWORDS = {
        'should', 'may', 'might', 'could', 'can', 'try', 'attempt',
        'appropriate', 'suitable', 'reasonable', 'adequate', 'sufficient',
        'necessary', 'essential', 'proper', 'correct', 'suitable',
        'generally', 'usually', 'typically', 'often', 'sometimes'
    }
    
    OPEN_ENDED = {'etc', 'and so on', 'or other', 'other', 'others', 'such'}
    
    UNDEFINED_REFS = {'approval', 'approved', 'authorized', 'authorized by', 'requires'}
    
    def detect_ambiguities(self, clause_text: str, entities: Dict = None, intent: str = None) -> Tuple[bool, str, float]:
        """
        Detect if clause is ambiguous.
        
        Returns: (is_ambiguous, reason, confidence_score 0-100)
        """
        
        if not entities:
            entities = {}
        
        score = 0  # 0-100 ambiguity scale
        reasons = []
        
        # Rule 1: Vague keywords
        vague_count = self._count_vague_keywords(clause_text)
        if vague_count > 0:
            score += (vague_count * 15)
            reasons.append(f"Found {vague_count} vague keyword(s)")
        
        # Rule 2: Open-ended language
        open_ended_count = self._count_open_ended(clause_text)
        if open_ended_count > 0:
            score += (open_ended_count * 20)
            reasons.append(f"Open-ended language: {open_ended_count} instance(s)")
        
        # Rule 3: Undefined references (approval without who approves)
        undefined = self._check_undefined_refs(clause_text)
        if undefined:
            score += 25
            reasons.append(f"Undefined reference: {undefined}")
        
        # Rule 4: Incomplete conditions (IF without THEN)
        if self._has_incomplete_condition(clause_text):
            score += 20
            reasons.append("Incomplete condition (IF without THEN or vice versa)")
        
        # Rule 5: Numeric values without units
        if self._has_ununit_numbers(clause_text, entities):
            score += 20
            reasons.append("Numeric values without clear units")
        
        # Rule 6: Percentages without base reference
        if self._has_unanchored_percentages(clause_text):
            score += 15
            reasons.append("Percentages without base value specified")
        
        # Rule 7: Good clarity signals (reduce score)
        clarity_signals = self._count_clarity_signals(clause_text, entities)
        if clarity_signals > 0:
            score -= (clarity_signals * 10)
            reasons.append(f"Clarity indicators: {clarity_signals}")
        
        # Clamp score 0-100
        score = max(0, min(100, score))
        
        # Decision: > 40 = ambiguous
        is_ambiguous = score > 40
        
        # Confidence: how sure we are about the ambiguity judgment
        confidence = 100 - abs(score - 50)
        
        reason_str = ' | '.join(reasons) if reasons else "No ambiguities detected"
        
        return is_ambiguous, reason_str, confidence
    
    def _count_vague_keywords(self, text: str) -> int:
        """Count vague language instances"""
        text_lower = text.lower()
        count = 0
        for keyword in self.VAGUE_KEYWORDS:
            # Word boundary match
            if re.search(rf'\b{keyword}\b', text_lower):
                count += 1
        return count
    
    def _count_open_ended(self, text: str) -> int:
        """Count open-ended language instances"""
        text_lower = text.lower()
        count = 0
        for phrase in self.OPEN_ENDED:
            if phrase in text_lower:
                count += 1
        return count
    
    def _check_undefined_refs(self, text: str) -> Optional[str]:
        """Check for undefined references"""
        text_lower = text.lower()
        
        for ref in self.UNDEFINED_REFS:
            if ref in text_lower:
                # Check if followed by "by" + entity
                pattern = f"{ref}\\s+(?:by\\s+)?([A-Za-z\\s]*)?(?:\\.|,|$)"
                match = re.search(pattern, text_lower, re.IGNORECASE)
                if match:
                    entity = match.group(1)
                    if not entity or len(entity.strip()) < 2:
                        return f"'{ref}' without clear authority specified"
        
        return None
    
    def _has_incomplete_condition(self, text: str) -> bool:
        """Check for incomplete IF/THEN conditions"""
        text_lower = text.lower()
        
        has_if = bool(re.search(r'\bif\b', text_lower))
        has_then = bool(re.search(r'\bthen\b', text_lower))
        
        # If one exists without the other, it's incomplete
        return (has_if and not has_then) or (has_then and not has_if)
    
    def _has_ununit_numbers(self, text: str, entities: Dict) -> bool:
        """Check for numeric values without units"""
        numbers = re.findall(r'\b\d+(?:\.\d+)?\b', text)
        
        # Skip if we have good entity extraction with units
        if entities and ('numeric_values' in entities or 'durations' in entities):
            return False
        
        # If numbers exist but no units nearby
        if numbers:
            unit_keywords = ['km', 'hour', 'day', 'week', 'month', 'year', 'percent', '%', 'rs', 'usd']
            has_units = any(unit in text.lower() for unit in unit_keywords)
            return not has_units
        
        return False
    
    def _has_unanchored_percentages(self, text: str) -> bool:
        """Check if percentages have base values defined"""
        percentages = re.findall(r'\d+%', text)
        if not percentages:
            return False
        
        # Check if percentages are followed by clear base references
        base_indicators = ['of', 'on', 'against', 'from']
        
        for pct in percentages:
            # Find context after percentage
            idx = text.find(pct)
            after = text[idx:min(idx + 30, len(text))].lower()
            
            has_base = any(base in after for base in base_indicators)
            if not has_base:
                return True
        
        return False
    
    def _count_clarity_signals(self, text: str, entities: Dict) -> int:
        """Count clarity indicators (reduce ambiguity score)"""
        count = 0
        
        # Clear threshold language
        threshold_keywords = ['maximum', 'minimum', 'at most', 'at least', 'exactly', 'precisely']
        for kw in threshold_keywords:
            if kw in text.lower():
                count += 1
        
        # Entity coverage
        if entities and len(entities) >= 3:
            count += 1
        
        # Explicit conditions with clear outcomes
        if re.search(r'if.*then|when.*must|provided.*shall', text, re.IGNORECASE):
            count += 1
        
        return count


# =============================================================================
# STAGE 6: POLICY-AGNOSTIC DSL GENERATION
# =============================================================================

class DynamicDSLGenerator:
    """
    Stage 6 REFACTORED: Policy-agnostic DSL generation.
    
    Strategy:
    1. Build fact namespace DYNAMICALLY from extracted entities
    2. Generate rules based on generic intent taxonomy
    3. NO hardcoded fact mapping (no travel.distance, employee.level, etc.)
    4. Generic fact names: metric.*, category.*, threshold.*
    
    Output: DSL rules that work for any policy
    """
    
    def __init__(self):
        self.fact_registry = {}  # Track discovered facts
    
    def generate_dsl_rule(self, clause_id: str, clause_text: str, intent: str, 
                         entities: Dict, is_ambiguous: bool = False) -> Dict:
        """
        Generate DSL rule from clause without policy-specific mapping.
        
        Returns:
        {
            "rule_id": "C6_1",
            "rule_name": "No official travel exceeds 200kms for single person",
            "intent": "RESTRICTION",
            "conditions": [
                {"fact": "metric.distance_km", "operator": "<=", "value": "200"}
            ],
            "actions": ["ENFORCE" or "WARN"],
            "source": "C6_1"
        }
        """
        
        # Build conditions from entities (generic mapping)
        conditions = self._build_conditions_from_entities(entities, clause_text)
        
        # Build actions based on intent (generic)
        actions = self._build_actions_from_intent(intent, is_ambiguous)
        
        rule = {
            "rule_id": clause_id,
            "clause_text": clause_text[:100] + "..." if len(clause_text) > 100 else clause_text,
            "intent": intent,
            "is_ambiguous": is_ambiguous,
            "conditions": conditions,
            "actions": actions,
            "fact_types_used": self._extract_fact_types(conditions)
        }
        
        return rule
    
    def _build_conditions_from_entities(self, entities: Dict, clause_text: str) -> List[Dict]:
        """
        Build DSL conditions from extracted entities using GENERIC mapping.
        
        NO hardcoded entity → fact mappings like:
            distance → travel.distance (WRONG)
            hour → work.hours (WRONG)
            
        Instead, use SEMANTIC mapping:
            numeric_value with "km" unit → metric.distance_km
            numeric_value with "hour" unit → metric.duration_hours
            percentage → metric.percentage
            categorical → category.<inferred_type>
            role → actor.role
            threshold → constraint.threshold_<type>
        """
        
        conditions = []
        
        if not entities:
            return conditions
        
        # Process numeric values
        if 'numeric_values' in entities:
            for num_val in entities['numeric_values']:
                cond = self._build_numeric_condition(num_val)
                if cond:
                    conditions.append(cond)
        
        # Process percentages
        if 'percentages' in entities:
            for pct in entities['percentages']:
                conditions.append({
                    "fact": "metric.percentage",
                    "operator": "EQUALS",
                    "value": pct['value'],
                    "semantic_meaning": f"Percentage value is {pct['value']}"
                })
        
        # Process durations
        if 'durations' in entities:
            for duration in entities['durations']:
                unit = duration['unit']
                fact_name = f"metric.duration_{unit}"
                conditions.append({
                    "fact": fact_name,
                    "operator": "LESS_THAN_OR_EQUAL",
                    "value": duration['value'],
                    "unit": unit,
                    "semantic_meaning": f"Duration must be <= {duration['value']} {unit}"
                })
        
        # Process monetary values
        if 'monetary' in entities:
            for money in entities['monetary']:
                conditions.append({
                    "fact": "metric.monetary_value",
                    "operator": "LESS_THAN_OR_EQUAL",
                    "value": money['value'],
                    "currency": money.get('currency', 'UNKNOWN'),
                    "semantic_meaning": f"Amount must be <= {money['value']}"
                })
        
        # Process thresholds
        if 'thresholds' in entities:
            for threshold in entities['thresholds']:
                conditions.append({
                    "fact": f"constraint.threshold_{threshold['type']}",
                    "operator": "BOUND",
                    "value": threshold['value'],
                    "threshold_type": threshold['type'],
                    "semantic_meaning": f"Value must be {threshold['type']} {threshold['value']}"
                })
        
        # Process categorical values
        if 'categorical' in entities:
            for cat in entities['categorical']:
                conditions.append({
                    "fact": "category.classification",
                    "operator": "IN_SET",
                    "value": cat['value'],
                    "semantic_meaning": f"Must be classified as {cat['value']}"
                })
        
        # Process roles
        if 'roles' in entities:
            for role in entities['roles']:
                conditions.append({
                    "fact": "actor.role",
                    "operator": "EQUALS",
                    "value": role['value'],
                    "semantic_meaning": f"Must be {role['value']}"
                })
        
        # Process exclusions
        if 'exclusions' in entities:
            for excl in entities['exclusions']:
                conditions.append({
                    "fact": "constraint.exclusion",
                    "operator": "NOT_EQUALS",
                    "value": excl['value'],
                    "semantic_meaning": f"Cannot be {excl['value']}"
                })
        
        # Process conditions
        if 'conditions' in entities:
            for cond in entities['conditions']:
                conditions.append({
                    "fact": "logic.conditional",
                    "operator": "IF_THEN",
                    "condition": cond.get('condition', ''),
                    "consequence": cond.get('consequence', ''),
                    "semantic_meaning": f"IF {cond.get('condition')} THEN {cond.get('consequence')}"
                })
        
        return conditions
    
    def _build_numeric_condition(self, num_val: Dict) -> Optional[Dict]:
        """Build a condition from a numeric value"""
        
        unit = num_val.get('unit', 'UNKNOWN')
        value = num_val.get('value')
        
        # Generic fact name: metric.<unit>
        if unit and unit != 'UNKNOWN':
            fact_name = f"metric.{unit.lower().replace(' ', '_')}"
        else:
            fact_name = "metric.value"
        
        # Infer operator from context
        context = num_val.get('context', '').lower()
        if 'maximum' in context or 'max' in context or 'exceed' in context or 'not exceed' in context:
            operator = "LESS_THAN_OR_EQUAL"
        elif 'minimum' in context or 'min' in context or 'at least' in context:
            operator = "GREATER_THAN_OR_EQUAL"
        else:
            operator = "EQUALS"
        
        return {
            "fact": fact_name,
            "operator": operator,
            "value": value,
            "unit": unit,
            "semantic_meaning": f"Metric '{unit}' is {operator} {value}"
        }
    
    def _build_actions_from_intent(self, intent: str, is_ambiguous: bool) -> List[str]:
        """
        Build actions based on GENERIC intent types.
        
        Generic mapping (works for any policy):
        - RESTRICTION → ENFORCE (block action)
        - LIMIT → ENFORCE (enforce boundary)
        - CONDITIONAL_ALLOWANCE → CONDITIONAL_GRANT (if condition met, allow)
        - EXCEPTION → ALLOW_EXCEPTION (allow outside normal rules)
        - APPROVAL_REQUIRED → GATE (require approval)
        - ADVISORY → WARN (suggest, not enforce)
        - INFORMATIONAL → LOG (informational only)
        """
        
        base_action = {
            'RESTRICTION': 'ENFORCE_RESTRICTION',
            'LIMIT': 'ENFORCE_LIMIT',
            'CONDITIONAL_ALLOWANCE': 'GRANT_IF_CONDITIONS_MET',
            'EXCEPTION': 'ALLOW_EXCEPTION',
            'APPROVAL_REQUIRED': 'GATE_BEHIND_APPROVAL',
            'ADVISORY': 'RECOMMEND',
            'INFORMATIONAL': 'LOG_INFORMATIONAL'
        }.get(intent, 'PROCESS')
        
        # If ambiguous, downgrade to WARNING
        if is_ambiguous:
            base_action = 'WARN_' + base_action
        
        return [base_action]
    
    def _extract_fact_types(self, conditions: List[Dict]) -> List[str]:
        """Extract all unique fact types used in conditions"""
        fact_types = set()
        for cond in conditions:
            if 'fact' in cond:
                # Extract the category (metric.*, category.*, constraint.*, etc.)
                fact = cond['fact']
                category = fact.split('.')[0] if '.' in fact else fact
                fact_types.add(category)
        
        return sorted(list(fact_types))


# =============================================================================
# HELPER: Generate Stage 3 Generic Prompt
# =============================================================================

def generate_stage3_prompt(segment_text: str) -> str:
    """
    Generate a completely generic Stage 3 prompt.
    NO travel-specific examples, NO hardcoded schema.
    """
    
    return f"""Extract all ENTITIES and VALUES from this policy clause.

CLAUSE TEXT:
{segment_text}

EXTRACT THE FOLLOWING GENERIC ENTITY TYPES:

1. NUMERIC VALUES
   - Any number mentioned: 200, 50, 3.14
   - Include the unit if present (km, hours, days, etc.)
   
2. PERCENTAGES
   - Any percentage: 25%, 125%
   - Note what this percentage applies to if stated

3. DURATIONS / TIME PERIODS
   - Hours, days, weeks, months, years
   - Example: "2 days", "6 hours", "4 weeks"

4. MONETARY VALUES
   - Amounts with currency: $100, Rs 500, €50
   - Include currency symbol/code

5. RANGES
   - From X to Y format: 1-10, between 100-200

6. CATEGORICAL VALUES
   - Classifications, enumerations, types
   - Example: "Senior", "Junior", "yes/no"

7. ROLES / POSITIONS
   - Any job title or responsibility
   - Example: "Manager", "Reporting Officer"

8. THRESHOLDS
   - Words indicating limits: maximum, minimum, up to, at least, exceeding
   - The value that sets the limit

9. CONDITIONS / LOGIC
   - IF/THEN statements
   - When/provided/unless clauses
   - IF: [condition], THEN: [consequence]

10. EXCLUSIONS
    - What is NOT included or applicable
    - Example: "except", "other than", "excluding"

OUTPUT FORMAT (STRICT JSON):
{{
    "numeric_values": [
        {{"value": "200", "unit": "km", "context": "..."}}
    ],
    "percentages": [
        {{"value": "25%", "context": "..."}}
    ],
    "durations": [
        {{"value": "2", "unit": "days", "context": "..."}}
    ],
    "monetary": [
        {{"value": "$100", "currency": "USD", "context": "..."}}
    ],
    "categorical": [
        {{"value": "Senior", "context": "..."}}
    ],
    "roles": [
        {{"value": "Manager", "context": "..."}}
    ],
    "thresholds": [
        {{"type": "maximum", "value": "200", "unit": "km"}}
    ],
    "conditions": [
        {{"condition": "...", "consequence": "..."}}
    ],
    "exclusions": [
        {{"value": "...", "context": "..."}}
    ]
}}

RULES:
- Extract ONLY values explicitly stated in the clause
- Include context/meaning for each value
- Be descriptive but concise
- Return ONLY valid JSON, no markdown or explanations"""


# =============================================================================
# HELPER: Generate Stage 4 Generic Prompt  
# =============================================================================

def generate_stage4_prompt(clause_id: str, clause_text: str, entities_json: str) -> str:
    """
    Generate a completely generic Stage 4 prompt.
    NO travel-specific ambiguity rules.
    """
    
    return f"""Analyze this policy clause for AMBIGUITY.

CLAUSE ID: {clause_id}
CLAUSE TEXT: {clause_text}

EXTRACTED ENTITIES:
{entities_json}

AMBIGUITY INDICATORS:
1. Vague language (should, may, might, could, appropriate, suitable, reasonable)
2. Undefined references (approval, authority without specifying WHO)
3. Incomplete conditions (IF without THEN, or THEN without IF)
4. Open-ended language (etc., and so on, other, others)
5. Numbers without units or base values
6. Percentages without stating what they're a percentage OF
7. Unspecified thresholds (maximum without value)

OUTPUT FORMAT (strict JSON):
{{
    "is_ambiguous": true/false,
    "ambiguity_score": 0-100,
    "reasons": ["reason1", "reason2", ...],
    "vague_terms": ["term1", "term2", ...],
    "undefined_references": ["ref1", "ref2", ...],
    "clarity_level": "high/medium/low"
}}

DECISION RULE:
- Score > 50 = ambiguous
- Score <= 50 = clear
- Provide detailed reasoning"""


if __name__ == "__main__":
    # Example usage
    print("Policy-Agnostic Stages 3, 4, 6 - Ready to integrate")
    
    # Test Stage 3 extractor
    extractor = GenericEntityExtractor()
    test_clause = "No official travel by personal car must exceed 200 kms on any day. This policy applies to all employees earning above Rs 50,000 monthly."
    entities = extractor.extract_entities(test_clause)
    print("\n=== Stage 3: Entity Extraction ===")
    print(json.dumps(entities, indent=2))
    
    # Test Stage 4 ambiguity detector
    detector = GenericAmbiguityDetector()
    is_amb, reason, conf = detector.detect_ambiguities(test_clause, entities)
    print("\n=== Stage 4: Ambiguity Detection ===")
    print(f"Ambiguous: {is_amb}, Reason: {reason}, Confidence: {conf}")
    
    # Test Stage 6 DSL generator
    dsl_gen = DynamicDSLGenerator()
    rule = dsl_gen.generate_dsl_rule("C6_1", test_clause, "RESTRICTION", entities, is_amb)
    print("\n=== Stage 6: DSL Generation ===")
    print(json.dumps(rule, indent=2))
