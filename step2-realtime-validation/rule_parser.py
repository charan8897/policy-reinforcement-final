#!/usr/bin/env python3
"""
Fast PolicySpec Rule Parser - No Gemini API calls
Directly parse and match policy rules without Gemini
"""

import re

class PolicySpecRuleParser:
    """Parse and evaluate PolicySpec rules without Gemini"""
    
    def __init__(self, rules_text):
        """Initialize parser with rules text"""
        self.rules_text = rules_text
        self.rules = self._parse_rules()
    
    def _parse_rules(self):
        """Parse rules into structured format"""
        rules = []
        
        # Split by rule definitions
        rule_pattern = r'rule\s+(\w+)\s+(MUST|SHOULD|EXPECTED)\s*\{(.*?)\}'
        matches = re.finditer(rule_pattern, self.rules_text, re.DOTALL)
        
        for match in matches:
            rule_name = match.group(1)
            enforcement = match.group(2)
            rule_body = match.group(3)
            
            rules.append({
                'name': rule_name,
                'enforcement': enforcement,
                'body': rule_body,
                'conditions': self._extract_conditions(rule_body),
                'requirements': self._extract_requirements(rule_body)
            })
        
        return rules
    
    def _extract_conditions(self, body):
        """Extract 'when' conditions"""
        when_pattern = r'when\s+([^\n]+)'
        match = re.search(when_pattern, body)
        if match:
            return match.group(1).strip()
        return None
    
    def _extract_requirements(self, body):
        """Extract 'require' statements"""
        require_pattern = r'require\s+([^\n]+)'
        matches = re.findall(require_pattern, body)
        return matches
    
    def _evaluate_condition(self, condition, field_name, field_value):
        """Evaluate a condition against field"""
        if not condition:
            return True
        
        # Simple pattern matching
        condition_lower = condition.lower()
        field_lower = field_name.lower()
        value_lower = str(field_value).lower()
        
        # Check if field is mentioned in condition
        if field_lower not in condition_lower:
            return False
        
        # Parse simple comparisons
        # e.g., "employee.grade >= 8" or "booking.duration_days <= 45"
        
        # Extract numeric comparisons
        numeric_patterns = [
            (r'<=\s*(\d+)', lambda op, val: float(field_value) <= float(val)),
            (r'>=\s*(\d+)', lambda op, val: float(field_value) >= float(val)),
            (r'<\s*(\d+)', lambda op, val: float(field_value) < float(val)),
            (r'>\s*(\d+)', lambda op, val: float(field_value) > float(val)),
            (r'==\s*["\']?(\w+)["\']?', lambda op, val: value_lower == val.lower()),
        ]
        
        for pattern, compare_fn in numeric_patterns:
            match = re.search(pattern, condition)
            if match:
                try:
                    return compare_fn(None, match.group(1))
                except:
                    return False
        
        return True
    
    def _extract_requirement_value(self, requirement, field_name, field_value):
        """Extract the requirement value from requirement string"""
        # e.g., "booking.duration_days <= 45" → extract 45
        
        numeric_match = re.search(r'<=\s*(\d+)|>=\s*(\d+)', requirement)
        if numeric_match:
            return numeric_match.group(1) or numeric_match.group(2)
        
        string_match = re.search(r'==\s*["\']?([^"\']+)["\']?', requirement)
        if string_match:
            return string_match.group(1)
        
        return None
    
    def validate_field_fast(self, field_name, field_value, found_rules):
        """Fast validation using rule parsing (no Gemini)"""
        
        violations = []
        warnings = []
        recommendations = []
        
        for rule in self.rules:
            # Check if this rule mentions our field
            rule_body_lower = rule['body'].lower()
            field_lower = field_name.lower()
            
            # Loose match - if field name appears in rule
            if field_lower not in rule_body_lower:
                continue
            
            # Check MUST rules (violations)
            if rule['enforcement'] == 'MUST':
                # Parse requirement and check
                for req in rule['requirements']:
                    if '<=' in req or '>=' in req or '==' in req:
                        # Try to validate
                        try:
                            # Handle numeric comparisons
                            if '<=' in req:
                                match = re.search(r'<=\s*(\d+)', req)
                                if match:
                                    limit = int(match.group(1))
                                    try:
                                        if float(field_value) > limit:
                                            violations.append({
                                                'rule': rule['name'],
                                                'message': f"Violates {rule['name']}: {req}",
                                                'requirement': req
                                            })
                                    except:
                                        pass
                            elif '>=' in req:
                                match = re.search(r'>=\s*(\d+)', req)
                                if match:
                                    limit = int(match.group(1))
                                    try:
                                        if float(field_value) < limit:
                                            violations.append({
                                                'rule': rule['name'],
                                                'message': f"Violates {rule['name']}: {req}",
                                                'requirement': req
                                            })
                                    except:
                                        pass
                        except:
                            pass
            
            # Check EXPECTED/SHOULD rules
            elif rule['enforcement'] in ['EXPECTED', 'SHOULD']:
                warnings.append({
                    'rule': rule['name'],
                    'message': f"Note: {rule['enforcement'].lower()} - {rule['name']}",
                    'enforcement': rule['enforcement']
                })
        
        # Determine status
        if violations:
            return {
                'status': 'error',
                'message': f"✗ {field_name}={field_value} violates policy",
                'violations': violations,
                'reasoning': '; '.join([v['message'] for v in violations[:2]])
            }
        elif warnings:
            return {
                'status': 'warning',
                'message': f"⚠ {field_name}={field_value} - check policy notes",
                'warnings': warnings,
                'reasoning': 'Policy expects additional validation'
            }
        else:
            return {
                'status': 'valid',
                'message': f"✓ {field_name}={field_value} accepted",
                'reasoning': 'No policy constraints violated'
            }
