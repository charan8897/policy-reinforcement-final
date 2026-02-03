"""
Policy Translator - Convert technical DSL to human-readable business language
"""

class PolicyTranslator:
    """Translate DSL rules to business English"""
    
    @staticmethod
    def translate_fact(fact):
        """Convert technical fact names to human-readable"""
        fact_map = {
            'approval.required': 'Approval Required',
            'approval.manager': 'Manager Approval',
            'approval.hod': 'HOD Approval',
            'allowance.general': 'General Allowance',
            'allowance.accommodation': 'Accommodation Allowance',
            'allowance.food': 'Food Allowance',
            'allowance.travel': 'Travel Allowance',
            'limit.general': 'General Limit',
            'limit.accommodation': 'Accommodation Limit',
            'limit.daily': 'Daily Limit',
            'settlement.timeframe': 'Settlement Timeframe',
            'settlement.deadline': 'Settlement Deadline',
            'submission.deadline': 'Submission Deadline',
            'bill.required': 'Bill/Receipt Required',
            'approval.level': 'Approval Level',
            'employee.grade': 'Employee Grade',
            'travel.type': 'Travel Type',
            'accommodation.type': 'Accommodation Type',
            'claimpercentage': 'Claim Percentage',
            'maximumclaimpercentage': 'Maximum Claim Percentage',
            'settlementtimelimit': 'Settlement Time Limit',
            'minimumhoursforreimbursement': 'Minimum Hours for Reimbursement',
            'policyeffectivedate': 'Policy Effective Date',
            'PASS': 'Status',
        }
        return fact_map.get(fact, fact.replace('_', ' ').title())
    
    @staticmethod
    def translate_operator(operator):
        """Convert operators to human-readable"""
        operator_map = {
            'EQUALS': 'must be',
            'NOT_EQUALS': 'must not be',
            'GREATER_THAN': 'must be greater than',
            'LESS_THAN': 'must be less than',
            'GREATER_THAN_OR_EQUAL': 'must be at least',
            'LESS_THAN_OR_EQUAL': 'must not exceed',
            'CONTAINS': 'must contain',
            'APPROVED': 'is approved as',
            'ENFORCED': 'is enforced as',
            'CONDITIONAL': 'conditional',
            'REQUIRED': 'required',
        }
        return operator_map.get(operator, operator.lower())
    
    @staticmethod
    def translate_value(value):
        """Convert values to human-readable"""
        value_map = {
            'OK': 'Approved',
            'YES': 'Yes',
            'NO': 'No',
            'CONDITIONAL': 'with conditions',
            'STRICT': 'strictly',
            'APPROVED': 'approved',
        }
        return value_map.get(value, value)
    
    @staticmethod
    def translate_constraint(constraint):
        """Translate a single constraint to English"""
        if not constraint:
            return ""
        
        fact = constraint.get('fact', '')
        operator = constraint.get('operator', '')
        value = constraint.get('value', '')
        
        fact_human = PolicyTranslator.translate_fact(fact)
        operator_human = PolicyTranslator.translate_operator(operator)
        value_human = PolicyTranslator.translate_value(str(value))
        
        return f"{fact_human} {operator_human} {value_human}"
    
    @staticmethod
    def translate_policy(policy):
        """
        Translate entire policy to human-readable format
        
        Returns: dict with original DSL + human-readable explanations
        """
        
        translation = {
            'policyId': policy.get('policyId'),
            'name': policy.get('name'),
            'enforcement': policy.get('outcome', {}).get('enforcement', 'unknown').upper(),
            'when_clauses': [],
            'constraint': '',
            'explanation': ''
        }
        
        # Translate "when" conditions
        when_list = policy.get('when', [])
        if when_list:
            for condition in when_list:
                condition_text = PolicyTranslator.translate_constraint(condition)
                translation['when_clauses'].append(condition_text)
            
            when_text = ' AND '.join(translation['when_clauses'])
            translation['when_text'] = f"When {when_text}"
        else:
            translation['when_text'] = "Always applies"
        
        # Translate constraint
        constraint = policy.get('what', {}).get('constraint', {})
        if constraint:
            translation['constraint'] = PolicyTranslator.translate_constraint(constraint)
        
        # Generate explanation
        translation['explanation'] = PolicyTranslator.generate_explanation(policy)
        
        return translation
    
    @staticmethod
    def generate_explanation(policy):
        """Generate business-friendly explanation of the policy"""
        
        policy_id = policy.get('policyId', 'Unknown')
        enforcement = policy.get('outcome', {}).get('enforcement', 'warn').upper()
        
        # Build explanation
        parts = []
        
        # When clause
        when_list = policy.get('when', [])
        if when_list:
            when_parts = []
            for condition in when_list:
                when_parts.append(PolicyTranslator.translate_constraint(condition))
            parts.append(f"When {' AND '.join(when_parts)}")
        else:
            parts.append("In all cases")
        
        # Then clause
        constraint = policy.get('what', {}).get('constraint', {})
        constraint_text = PolicyTranslator.translate_constraint(constraint)
        
        if enforcement == 'ENFORCE':
            parts.append(f"then {constraint_text} (ENFORCED)")
        else:
            parts.append(f"then {constraint_text} (WARNING ONLY)")
        
        explanation = ', '.join(parts)
        
        # Add clarification for different enforcement types
        if enforcement == 'WARN':
            explanation += "\n\n📋 Note: This is a warning-level policy. Users will be notified but not blocked."
        elif enforcement == 'ENFORCE':
            explanation += "\n\n🔒 Note: This is a strict enforcement policy. Users will be blocked if not compliant."
        
        return explanation
    
    @staticmethod
    def batch_translate_policies(policies):
        """Translate multiple policies"""
        return [PolicyTranslator.translate_policy(p) for p in policies]
