package data.travel_policy

# Enforced policy rules for travel_policy



    # Rule: C1
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c1_info := {"allow": true, "reason": "Clause C1: Informational - OK"} if {
        true
    }


    # Rule: C10
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c10_rest := {"allow": true, "reason": "Clause C10: Restriction - YES"} if {
        input.settlementdeadline == "2 days"
    }


    # Rule: C11
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c11_cond := {"allow": true, "reason": "Clause C11: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C12
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c12_cond := {"allow": true, "reason": "Clause C12: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C13
    # Intent: APPROVAL_REQUIRED
    # Action: enforce
    # Ambiguous: False
    allow_c13_appr := {"allow": true, "reason": "Clause C13: Approval Required - CONDITIONAL"} if {
        input.validationauthority == "HR & Accounts"
    input.approvalsource == "reporting manager"
    }


    # Rule: C14
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c14_rest := {"allow": true, "reason": "Clause C14: Restriction - YES"} if {
        true
    }


    # Rule: C15
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c15_limi := {"allow": true, "reason": "Clause C15: Limit - STRICT"} if {
        input.boardinglodginglimit == "eligible amount or bill amount, whichever is less"
    }


    # Rule: C16
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c16_cond := {"allow": true, "reason": "Clause C16: Conditional Allowance - CONDITIONAL"} if {
        input.minimumoutofficehours >= 6
    }


    # Rule: C17
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c17_limi := {"allow": true, "reason": "Clause C17: Limit - STRICT"} if {
        input.maximumdailydistance <= 200
    input.travelmode == "Self Drive"
    }


    # Rule: C18
    # Intent: ADVISORY
    # Action: enforce
    # Ambiguous: False
    allow_c18_advi := {"allow": true, "reason": "Clause C18: Advisory - CONDITIONAL"} if {
        input.maximumkilometersforpersonalcar <= 200
    input.minimumgroupsizeforencouragedtravel >= 3
    }


    # Rule: C19
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c19_rest := {"allow": true, "reason": "Clause C19: Restriction - YES"} if {
        input.driverchargesapplicability == "not applicable for personal car travel"
    }


    # Rule: C2
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c2_info := {"allow": true, "reason": "Clause C2: Informational - OK"} if {
        input.applicableto == "all employees of NAGA LIMITED"
    }


    # Rule: C20
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c20_limi := {"allow": true, "reason": "Clause C20: Limit - STRICT"} if {
        input.maximumdailydistance <= 50
    }


    # Rule: C21
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c21_info := {"allow": true, "reason": "Clause C21: Informational - OK"} if {
        input.policyeffectivedate == "01st April 2014"
    }


    # Rule: C3
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c3_cond := {"allow": true, "reason": "Clause C3: Conditional Allowance - CONDITIONAL"} if {
        input.relativefriendstayallowancepercentage == "25%"
    input.billrequirementforrelativefriendstay == "not required"
    }


    # Rule: C4
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c4_limi := {"allow": true, "reason": "Clause C4: Limit - STRICT"} if {
        input.maximumreimbursementpercentage <= 125
    input.accommodationtype == "Twin sharing"
    input.eligibleemployeelevel == "Senior"
    }


    # Rule: C5
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c5_rest := {"allow": true, "reason": "Clause C5: Restriction - YES"} if {
        input.approvalauthority == "Reporting Manager"
    }


    # Rule: C6
    # Intent: ADVISORY
    # Action: enforce
    # Ambiguous: False
    allow_c6_advi := {"allow": true, "reason": "Clause C6: Advisory - CONDITIONAL"} if {
        true
    }


    # Rule: C7
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c7_cond := {"allow": true, "reason": "Clause C7: Conditional Allowance - CONDITIONAL"} if {
        input.eligibilitybasis == "Job band and grade"
    input.policyreference == "Company Policy"
    }


    # Rule: C8
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c8_rest := {"allow": true, "reason": "Clause C8: Restriction - YES"} if {
        true
    }


    # Rule: C9
    # Intent: ADVISORY
    # Action: enforce
    # Ambiguous: False
    allow_c9_advi := {"allow": true, "reason": "Clause C9: Advisory - CONDITIONAL"} if {
        true
    }