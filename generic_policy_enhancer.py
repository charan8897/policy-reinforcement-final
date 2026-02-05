"""
Generic Policy Enhancer Module
Policy-agnostic enhancements that work for ANY policy type.

This module provides:
1. DocumentStructureDetector - Detects structure generically
2. GenericEntityClassifier - Classifies entities by semantic type
3. GenericIntentClassifier - Classifies clause intent using patterns
4. GenericAmbiguityDetector - Detects ambiguity linguistically
5. GenericDSLGenerator - Generates DSL from semantic inference
6. Unified configuration via JSON

Usage:
    from generic_policy_enhancer import (
        GenericIntentClassifier,
        GenericAmbiguityDetector,
        GenericDSLGenerator
    )
"""

import re
import json
from typing import Dict, List, Any, Optional, Tuple
from dataclasses import dataclass, field
from enum import Enum


class SemanticType(Enum):
    """Semantic types for entity classification"""
    TEMPORAL = "TEMPORAL"
    QUANTITATIVE = "QUANTITATIVE"
    ACTOR = "ACTOR"
    LOCATION = "LOCATION"
    CONDITIONAL = "CONDITIONAL"
    ACTION = "ACTION"
    STATUS = "STATUS"
    UNCATEGORIZED = "UNCATEGORIZED"


class IntentType(Enum):
    """Clause intent types"""
    RESTRICTION = "RESTRICTION"
    MANDATORY = "MANDATORY"
    PERMISSIVE = "PERMISSIVE"
    ADVISORY = "ADVISORY"
    LIMIT = "LIMIT"
    CONDITIONAL = "CONDITIONAL"
    INFORMATIONAL = "INFORMATIONAL"


class AmbiguityType(Enum):
    """Ambiguity types"""
    VAGUE_TERMS = "VAGUE_TERMS"
    UNDEFINED_REFERENCES = "UNDEFINED_REFERENCES"
    INCOMPLETE_CONDITIONS = "INCOMPLETE_CONDITIONS"
    SUBJECTIVE_LANGUAGE = "SUBJECTIVE_LANGUAGE"
    TEMPORAL_AMBIGUITY = "TEMPORAL_AMBIGUITY"
    BOUNDARY_OVERLAPS = "BOUNDARY_OVERLAPS"


@dataclass
class DetectedSection:
    """Detected document section"""
    section_type: str
    header: str
    content: List[str]
    line_start: int
    line_end: int


@dataclass
class ClassifiedEntity:
    """Classified entity with semantic type"""
    name: str
    value: str
    semantic_type: SemanticType
    validation_status: bool = True


@dataclass
class ClassifiedClause:
    """Classified clause with intent and entities"""
    clause_id: str
    original_text: str
    intent: IntentType
    intent_confidence: float
    entities: List[ClassifiedEntity]
    ambiguities: List[Tuple[AmbiguityType, str]]  # (type, context)
    section_type: str = "general"


@dataclass
class DSLRule:
    """Generated DSL rule"""
    rule_id: str
    when_conditions: List[Dict]
    then_outcome: Dict
    enforcement_level: str
    source_clause: str


# =============================================================================
# 1. Document Structure Detector
# =============================================================================

class DocumentStructureDetector:
    """
    Detects document structure regardless of policy type.
    Uses linguistic patterns, not specific keywords.
    """
    
    SECTION_PATTERNS = [
        (r'^#{1,3}\s+.+', 'heading'),                    # Markdown headings
        (r'^[A-Z][A-Z\s]+:$', 'section_header'),         # ALL CAPS headers
        (r'^(?:SECTION|ARTICLE|APPENDIX|ANNEXURE)[\s:]?\d*', 'numbered_section'),
        (r'^\d+\.\s+[A-Z]', 'numbered_item'),            # 1. Policy Statement
        (r'^[-•*]\s+', 'bullet_item'),                   # List items
        (r'^(DEFINITIONS|SCOPE|OBJECTIVE|ELIGIBILITY|EXCLUSIONS|PURPOSE|APPLICABILITY):', 'standard_section'),
        (r'^\d+\.\d+\.\s+', 'sub_section'),              # 1.1 Subsection
    ]
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        if 'section_patterns' in self.config:
            self.SECTION_PATTERNS = [
                (p['pattern'], p['type']) 
                for p in self.config['section_patterns']
            ]
    
    def detect_structure(self, content: str) -> List[DetectedSection]:
        """Detect all structural elements generically"""
        lines = content.split('\n')
        sections = []
        current_section = None
        
        for i, line in enumerate(lines):
            stripped = line.strip()
            if not stripped:
                continue
            
            matched = False
            for pattern, section_type in self.SECTION_PATTERNS:
                if re.match(pattern, stripped):
                    if current_section:
                        current_section.line_end = i
                        sections.append(current_section)
                    
                    current_section = DetectedSection(
                        section_type=section_type,
                        header=stripped,
                        content=[line],
                        line_start=i,
                        line_end=i
                    )
                    matched = True
                    break
            
            if not matched and current_section:
                current_section.content.append(line)
        
        if current_section:
            current_section.line_end = len(lines)
            sections.append(current_section)
        
        return sections
    
    def get_section_text(self, section: DetectedSection) -> str:
        """Reconstruct text from section"""
        return '\n'.join(section.content)


# =============================================================================
# 2. Generic Entity Classifier
# =============================================================================

class GenericEntityClassifier:
    """
    Classifies entities by semantic role, not policy-specific names.
    Works for ANY policy type.
    """
    
    ENTITY_KEYWORDS = {
        SemanticType.TEMPORAL: ['date', 'deadline', 'duration', 'timeframe', 'period', 'within', 'by'],
        SemanticType.QUANTITATIVE: ['amount', 'percentage', 'rate', 'limit', 'threshold', 'count', 'frequency', 'maximum', 'minimum'],
        SemanticType.ACTOR: ['role', 'person', 'department', 'authority', 'entity', 'employee', 'user', 'manager'],
        SemanticType.LOCATION: ['place', 'location', 'region', 'site', 'area', 'city', 'office'],
        SemanticType.CONDITIONAL: ['condition', 'prerequisite', 'requirement', 'criterion', 'eligibility'],
        SemanticType.ACTION: ['action', 'behavior', 'conduct', 'activity', 'task', 'procedure'],
        SemanticType.STATUS: ['status', 'state', 'condition', 'approval'],
    }
    
    VALUE_PATTERNS = {
        SemanticType.TEMPORAL: r'^(\d+\s*(days?|weeks?|months?|hours?|years?|minutes?)|today|immediately)$',
        SemanticType.QUANTITATIVE: r'^[\d,.]+\s*(%|percent|rs|inr|usd|eur|₹)?$',
        SemanticType.ACTOR: r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*$',
        SemanticType.LOCATION: r'^[A-Z][a-z]+(\s+[A-Z][a-z]+)*(,\s*[A-Z][a-z]+)*$',
    }
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        if 'semantic_types' in self.config:
            self.ENTITY_KEYWORDS = {
                SemanticType(k): v for k, v in self.config['semantic_types'].items()
            }
    
    def classify_entity(self, entity_name: str, entity_value: str) -> ClassifiedEntity:
        """Classify entity by semantic type"""
        entity_lower = entity_name.lower()
        
        for semantic_type, keywords in self.ENTITY_KEYWORDS.items():
            if any(kw in entity_lower for kw in keywords):
                validation_status = self._validate_value(semantic_type, entity_value)
                return ClassifiedEntity(
                    name=entity_name,
                    value=entity_value,
                    semantic_type=semantic_type,
                    validation_status=validation_status
                )
        
        # Default to UNCATEGORIZED
        return ClassifiedEntity(
            name=entity_name,
            value=entity_value,
            semantic_type=SemanticType.UNCATEGORIZED,
            validation_status=True
        )
    
    def _validate_value(self, semantic_type: SemanticType, value: str) -> bool:
        """Validate value matches semantic type expectations"""
        pattern = self.VALUE_PATTERNS.get(semantic_type, r'.+')
        return bool(re.match(pattern, str(value).strip(), re.IGNORECASE))
    
    def classify_entities(self, entities: Dict[str, str]) -> List[ClassifiedEntity]:
        """Classify multiple entities"""
        return [self.classify_entity(k, v) for k, v in entities.items()]


# =============================================================================
# 3. Generic Intent Classifier
# =============================================================================

class GenericIntentClassifier:
    """
    Classifies clause intent using linguistic patterns.
    Works for ANY policy type.
    """
    
    INTENT_PATTERNS = {
        IntentType.RESTRICTION: [
            r'\b(must not|shall not|cannot|prohibited|forbidden|not allowed)\b',
        ],
        IntentType.MANDATORY: [
            r'\b(must|shall|is required to|is obligated to)\b',
        ],
        IntentType.PERMISSIVE: [
            r'\b(may|can|is permitted to|is allowed to)\b',
        ],
        IntentType.ADVISORY: [
            r'\b(should|recommended|encouraged|advised|suggested)\b',
        ],
        IntentType.LIMIT: [
            r'\b(up to|maximum|minimum|not to exceed|at most|at least)\b',
        ],
        IntentType.CONDITIONAL: [
            r'\b(if|when|unless|provided that|in the event|only if|subject to)\b',
        ],
        IntentType.INFORMATIONAL: [
            r'\b(means|refers to|is defined as|includes)\b',
            r'^this (policy|document|section|clause)',
        ],
    }
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        if 'intent_patterns' in self.config:
            self.INTENT_PATTERNS = {
                IntentType(k): v for k, v in self.config['intent_patterns'].items()
            }
    
    def classify_intent(self, text: str) -> Tuple[IntentType, float]:
        """Classify clause intent generically with confidence score"""
        text_lower = text.lower()
        scores = {}
        
        for intent, patterns in self.INTENT_PATTERNS.items():
            score = 0
            for pattern in patterns:
                matches = len(re.findall(pattern, text_lower, re.IGNORECASE))
                score += matches
            if score > 0:
                scores[intent] = score
        
        if scores:
            best_intent = max(scores, key=scores.get)
            max_score = scores[best_intent]
            confidence = min(0.95, 0.5 + (max_score * 0.15))  # Normalize confidence
            return best_intent, confidence
        
        return IntentType.INFORMATIONAL, 0.5  # Default


# =============================================================================
# 4. Generic Ambiguity Detector
# =============================================================================

class GenericAmbiguityDetector:
    """
    Detects ambiguity using linguistic patterns, not policy-specific rules.
    Works for ANY policy type.
    """
    
    AMBIGUITY_PATTERNS = {
        AmbiguityType.VAGUE_TERMS: [
            r'\b(reasonable|appropriate|adequate|sufficient|proper)\b',
            r'\b(as applicable|as appropriate|as necessary|as needed)\b',
        ],
        AmbiguityType.UNDEFINED_REFERENCES: [
            r'\b(the|this|that|such)\s+\w+\b',
            r'\b(applicable|relevant|appropriate)\s+\w+\b',
        ],
        AmbiguityType.INCOMPLETE_CONDITIONS: [
            r'\b(if|when|unless)\b[^.!?]*$',
            r'\b(where|whenever)\b[^.!?]*$',
        ],
        AmbiguityType.SUBJECTIVE_LANGUAGE: [
            r'\b(material|significant|substantial|considerable)\b',
            r'\b(timely|prompt|expeditious)\b',
        ],
        AmbiguityType.TEMPORAL_AMBIGUITY: [
            r'\b(immediately|forthwith|promptly)\b',
            r'\b(within a reasonable time)\b',
            r'\b(as soon as possible)\b',
        ],
    }
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        if 'ambiguity_patterns' in self.config:
            self.AMBIGUITY_PATTERNS = {
                AmbiguityType(k): v for k, v in self.config['ambiguity_patterns'].items()
            }
    
    def detect_ambiguities(self, text: str) -> List[Tuple[AmbiguityType, str]]:
        """Detect ambiguity types generically"""
        ambiguities = []
        
        for ambiguity_type, patterns in self.AMBIGUITY_PATTERNS.items():
            for pattern in patterns:
                match = re.search(pattern, text, re.IGNORECASE)
                if match:
                    context = self._extract_context(text, match.start(), match.end())
                    ambiguities.append((ambiguity_type, context))
                    break  # One match per type is enough
        
        return ambiguities
    
    def _extract_context(self, text: str, start: int, end: int, context_chars: int = 50) -> str:
        """Extract context around match"""
        context_start = max(0, start - context_chars)
        context_end = min(len(text), end + context_chars)
        return text[context_start:context_end]


# =============================================================================
# 5. Generic DSL Generator
# =============================================================================

class GenericDSLGenerator:
    """
    Generates DSL rules from any policy clause using schema inference.
    Works for ANY policy type.
    """
    
    OPERATOR_MAP = {
        SemanticType.TEMPORAL: 'LESS_THAN_OR_EQUAL',
        SemanticType.QUANTITATIVE: 'LESS_THAN_OR_EQUAL',
        SemanticType.ACTOR: 'EQUALS',
        SemanticType.LOCATION: 'IN',
        SemanticType.ACTION: 'EQUALS',
        SemanticType.CONDITIONAL: 'EQUALS',
        SemanticType.STATUS: 'EQUALS',
    }
    
    ENFORCEMENT_MAP = {
        IntentType.RESTRICTION: 'enforce',
        IntentType.MANDATORY: 'enforce',
        IntentType.LIMIT: 'enforce',
        IntentType.CONDITIONAL: 'warn',
        IntentType.PERMISSIVE: 'warn',
        IntentType.ADVISORY: 'warn',
        IntentType.INFORMATIONAL: 'inform',
    }
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        if 'enforcement_mapping' in self.config:
            self.ENFORCEMENT_MAP = {
                IntentType(k): v for k, v in self.config['enforcement_mapping'].items()
            }
    
    def generate_rule(self, clause: ClassifiedClause) -> DSLRule:
        """Generate DSL rule from classified clause"""
        when_conditions = self._generate_conditions(clause.entities)
        enforcement_level = self.ENFORCEMENT_MAP.get(clause.intent, 'warn')
        
        return DSLRule(
            rule_id=clause.clause_id,
            when_conditions=when_conditions,
            then_outcome={
                enforcement_level: [{
                    'constraint': self._infer_constraint(clause),
                    'operator': 'EQUALS',
                    'value': 'OK'
                }]
            },
            enforcement_level=enforcement_level,
            source_clause=clause.original_text
        )
    
    def _generate_conditions(self, entities: List[ClassifiedEntity]) -> List[Dict]:
        """Generate when conditions from entities"""
        conditions = []
        
        for entity in entities:
            operator = self.OPERATOR_MAP.get(entity.semantic_type, 'EQUALS')
            conditions.append({
                'fact': self._normalize_fact_name(entity.name),
                'operator': operator,
                'value': self._normalize_value(entity.value, entity.semantic_type)
            })
        
        return conditions
    
    def _normalize_fact_name(self, name: str) -> str:
        """Normalize entity name to fact name"""
        # Convert camelCase to snake_case and lowercase
        name = re.sub(r'(?<!^)(?=[A-Z])', '_', name).lower()
        return re.sub(r'\s+', '_', name)
    
    def _normalize_value(self, value: str, semantic_type: SemanticType) -> str:
        """Normalize value based on semantic type"""
        value = value.strip()
        
        if semantic_type == SemanticType.QUANTITATIVE:
            # Ensure numeric values are properly formatted
            return re.sub(r',', '', value)  # Remove commas from numbers
        
        return value
    
    def _infer_constraint(self, clause: ClassifiedClause) -> str:
        """Infer constraint fact from clause content"""
        # Use intent + primary entity to create meaningful constraint
        intent_words = {
            IntentType.RESTRICTION: 'restriction',
            IntentType.MANDATORY: 'requirement',
            IntentType.LIMIT: 'limit',
            IntentType.CONDITIONAL: 'condition',
            IntentType.ADVISORY: 'advisory',
        }
        
        base = intent_words.get(clause.intent, 'policy')
        
        # Add primary entity type if available
        if clause.entities:
            primary_entity = clause.entities[0].name.lower()
            return f"{base}.{primary_entity}"
        
        return f"{base}.general"


# =============================================================================
# 6. Unified Policy Enhancer
# =============================================================================

class UnifiedPolicyEnhancer:
    """
    Unified enhancer combining all generic components.
    Drop-in replacement for policy-specific logic.
    """
    
    def __init__(self, config: Optional[Dict] = None):
        self.config = config or {}
        self.structure_detector = DocumentStructureDetector(config)
        self.entity_classifier = GenericEntityClassifier(config)
        self.intent_classifier = GenericIntentClassifier(config)
        self.ambiguity_detector = GenericAmbiguityDetector(config)
        self.dsl_generator = GenericDSLGenerator(config)
    
    def process_document(self, content: str) -> Dict[str, Any]:
        """Process entire document generically"""
        sections = self.structure_detector.detect_structure(content)
        
        # Extract clauses from sections
        all_clauses = []
        for section in sections:
            section_clauses = self._extract_clauses_from_section(section)
            all_clauses.extend(section_clauses)
        
        # Classify each clause
        classified_clauses = []
        for clause_text, clause_id in all_clauses:
            classified = self.classify_clause(clause_id, clause_text)
            classified.section_type = section.section_type
            classified_clauses.append(classified)
        
        # Generate DSL rules
        rules = []
        for clause in classified_clauses:
            rule = self.dsl_generator.generate_rule(clause)
            rules.append(rule)
        
        return {
            'sections': [{'type': s.section_type, 'header': s.header} for s in sections],
            'clauses': [self._clause_to_dict(c) for c in classified_clauses],
            'rules': [self._rule_to_dict(r) for r in rules],
            'statistics': self._generate_statistics(classified_clauses, rules)
        }
    
    def classify_clause(self, clause_id: str, text: str) -> ClassifiedClause:
        """Classify single clause"""
        intent, confidence = self.intent_classifier.classify_intent(text)
        
        # Extract entities using simple pattern matching
        entities = self._extract_entities(text)
        classified_entities = self.entity_classifier.classify_entities(entities)
        
        ambiguities = self.ambiguity_detector.detect_ambiguities(text)
        
        return ClassifiedClause(
            clause_id=clause_id,
            original_text=text,
            intent=intent,
            intent_confidence=confidence,
            entities=classified_entities,
            ambiguities=ambiguities
        )
    
    def _extract_entities(self, text: str) -> Dict[str, str]:
        """Extract key-value pairs from text"""
        entities = {}
        
        # Pattern: "X: Y" or "X = Y"
        pattern1 = re.findall(r'([A-Z][a-zA-Z\s]+?)\s*[:=]\s*([^\n,;]+)', text)
        for key, value in pattern1:
            key = key.strip().replace(' ', '')
            value = value.strip()
            if len(key) < 50 and len(value) < 100:
                entities[key] = value
        
        # Pattern: quoted values
        pattern2 = re.findall(r'"([^"]+)"\s*:\s*([^,]+)', text)
        for key, value in pattern2:
            entities[key] = value.strip()
        
        return entities
    
    def _extract_clauses_from_section(self, section: DetectedSection) -> List[Tuple[str, str]]:
        """Extract clauses from section"""
        section_text = self.structure_detector.get_section_text(section)
        clauses = []
        
        # Split by sentence-ending punctuation
        sentences = re.split(r'(?<=[.!?])\s+', section_text)
        
        clause_num = 1
        for sentence in sentences:
            sentence = sentence.strip()
            if len(sentence) > 20:  # Skip very short fragments
                clause_id = f"C{len(clauses) + 1}"
                clauses.append((sentence, clause_id))
        
        return clauses
    
    def _clause_to_dict(self, clause: ClassifiedClause) -> Dict:
        """Convert classified clause to dict"""
        return {
            'clauseId': clause.clause_id,
            'text': clause.original_text,
            'intent': clause.intent.value,
            'intent_confidence': clause.intent_confidence,
            'entities': {e.name: e.value for e in clause.entities},
            'ambiguities': [
                {'type': a[0].value, 'context': a[1]} 
                for a in clause.ambiguities
            ],
            'section_type': clause.section_type
        }
    
    def _rule_to_dict(self, rule: DSLRule) -> Dict:
        """Convert DSL rule to dict"""
        return {
            'rule_id': rule.rule_id,
            'when': rule.when_conditions,
            'then': rule.then_outcome,
            'enforcement_level': rule.enforcement_level
        }
    
    def _generate_statistics(self, clauses: List[ClassifiedClause], rules: List[DSLRule]) -> Dict:
        """Generate processing statistics"""
        intent_counts = {}
        ambiguity_counts = {}
        
        for clause in clauses:
            intent_counts[clause.intent.value] = intent_counts.get(clause.intent.value, 0) + 1
            for ambiguity, _ in clause.ambiguities:
                ambiguity_counts[ambiguity.value] = ambiguity_counts.get(ambiguity.value, 0) + 1
        
        return {
            'total_clauses': len(clauses),
            'total_rules': len(rules),
            'intent_distribution': intent_counts,
            'ambiguity_distribution': ambiguity_counts,
            'clauses_with_entities': sum(1 for c in clauses if c.entities),
            'clauses_with_ambiguities': sum(1 for c in clauses if c.ambiguities)
        }


# =============================================================================
# Configuration Management
# =============================================================================

def load_config(config_path: str = None) -> Dict:
    """Load configuration from JSON file"""
    if config_path is None:
        config_path = 'policy_config.json'
    
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        return {}


def save_config(config: Dict, config_path: str = 'policy_config.json'):
    """Save configuration to JSON file"""
    with open(config_path, 'w') as f:
        json.dump(config, f, indent=2)


# =============================================================================
# Main Entry Point
# =============================================================================

if __name__ == '__main__':
    import sys
    
    if len(sys.argv) < 2:
        print("Usage: python generic_policy_enhancer.py <policy_file.txt>")
        print("Optional: python generic_policy_enhancer.py <policy_file.txt> <config.json>")
        sys.exit(1)
    
    policy_file = sys.argv[1]
    config_path = sys.argv[2] if len(sys.argv) > 2 else None
    
    # Load config
    config = load_config(config_path)
    
    # Initialize enhancer
    enhancer = UnifiedPolicyEnhancer(config)
    
    # Read policy
    with open(policy_file, 'r') as f:
        content = f.read()
    
    # Process
    result = enhancer.process_document(content)
    
    # Output
    print(json.dumps(result, indent=2))
    
    # Save outputs
    base_name = policy_file.rsplit('.', 1)[0]
    with open(f'{base_name}_enhanced.json', 'w') as f:
        json.dump(result, f, indent=2)
    
    print(f"\n✓ Enhanced output saved to {base_name}_enhanced.json")
