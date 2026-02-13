package data.travel_policy

# Enforced policy rules for travel_policy



    # Rule: C1
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c1_limi := {"allow": true, "reason": "Clause C1: Limit - STRICT"} if {
        input.travelregion == "India"
    input.travelpurpose == "official business travel"
    }


    # Rule: C10
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c10_limi := {"allow": true, "reason": "Clause C10: Limit - STRICT"} if {
        true
    }


    # Rule: C11
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c11_limi := {"allow": true, "reason": "Clause C11: Limit - STRICT"} if {
        true
    }


    # Rule: C12
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c12_limi := {"allow": true, "reason": "Clause C12: Limit - STRICT"} if {
        true
    }


    # Rule: C13
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c13_limi := {"allow": true, "reason": "Clause C13: Limit - STRICT"} if {
        input.gradem4lodgingcategorya == "Rs. 2000"
    input.gradem4lodgingcategoryb == "Rs. 1500"
    input.boardingallowance == "Rs. 500"
    input.personalincidentalallowance == "Rs. 75"
    }


    # Rule: C14
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c14_limi := {"allow": true, "reason": "Clause C14: Limit - STRICT"} if {
        input.gradem5lodgingcategorya == "Rs. 2000"
    input.gradem5lodgingcategoryb == "Rs. 1500"
    input.boardingallowance == "Rs. 350"
    input.personalincidentalallowance == "Rs. 50"
    }


    # Rule: C15
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c15_limi := {"allow": true, "reason": "Clause C15: Limit - STRICT"} if {
        input.gradem6lodgingcategorya == "Rs. 1000"
    input.gradem6lodgingcategoryb == "Rs. 700"
    input.boardingallowance == "Rs. 350"
    }


    # Rule: C16
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c16_cond := {"allow": true, "reason": "Clause C16: Conditional Allowance - CONDITIONAL"} if {
        input.lodgingreimbursementrate == "Rs. 250 per day"
    input.lodgingtype == "relative’s or friend’s place"
    }


    # Rule: C17
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c17_limi := {"allow": true, "reason": "Clause C17: Limit - STRICT"} if {
        input.fourwheelerrate == "7.0 Rs/KM"
    input.twowheelerrate == "2.5 Rs/KM"
    }


    # Rule: C18
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c18_cond := {"allow": true, "reason": "Clause C18: Conditional Allowance - CONDITIONAL"} if {
        input.durationthresholdlow1 == "3 hours"
    input.durationthresholdhigh1 == "12 hours"
    input.entitlementpercentage1 == "50%"
    input.durationthresholdlow2 == "12 hours"
    input.durationthresholdhigh2 == "24 hours"
    input.entitlementpercentage2 == "100%"
    input.timebase == "24-hour clock"
    }


    # Rule: C19
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c19_cond := {"allow": true, "reason": "Clause C19: Conditional Allowance - CONDITIONAL"} if {
        input.minimumtravelduration >= 3
    input.maximumtravelduration <= 12
    input.dailyallowancepercentage == "50%"
    }


    # Rule: C2
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c2_info := {"allow": true, "reason": "Clause C2: Informational - OK"} if {
        true
    }


    # Rule: C20
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c20_cond := {"allow": true, "reason": "Clause C20: Conditional Allowance - CONDITIONAL"} if {
        input.minimumtravelduration >= 12
    input.maximumtravelduration <= 24
    input.dailyallowancepercentage == "100%"
    }


    # Rule: C21
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c21_rest := {"allow": true, "reason": "Clause C21: Restriction - YES"} if {
        input.expenseclaimrequirements == "bills/invoices"
    input.excludedexpensecategories == "Boarding and Personal incidental category"
    }


    # Rule: C22
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c22_cond := {"allow": true, "reason": "Clause C22: Conditional Allowance - CONDITIONAL"} if {
        input.minimumtravelduration >= 15
    input.maximumtravelduration <= 1
    }


    # Rule: C23
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c23_cond := {"allow": true, "reason": "Clause C23: Conditional Allowance - CONDITIONAL"} if {
        input.deputationdurationlowerbound == "1 day"
    input.deputationdurationupperbound == "7 days"
    input.allowancesourceafter7days == "Table 7"
    }


    # Rule: C24
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c24_cond := {"allow": true, "reason": "Clause C24: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C25
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c25_rest := {"allow": true, "reason": "Clause C25: Restriction - YES"} if {
        input.billsubmissionrequirement == "not required"
    }


    # Rule: C26
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c26_cond := {"allow": true, "reason": "Clause C26: Conditional Allowance - CONDITIONAL"} if {
        input.durationprojectionthreshold == "1 year"
    }


    # Rule: C27
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c27_limi := {"allow": true, "reason": "Clause C27: Limit - STRICT"} if {
        input.minimumreimbursementdistance >= 100
    }


    # Rule: C28
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c28_cond := {"allow": true, "reason": "Clause C28: Conditional Allowance - CONDITIONAL"} if {
        input.relocationduration == "7 days"
    input.referencedtables == "Table 8, Table 9, Table 10"
    }


    # Rule: C29
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c29_info := {"allow": true, "reason": "Clause C29: Informational - OK"} if {
        input.employeegrade == "M1"
    input.travelmode == "Air (Economy)"
    }


    # Rule: C3
    # Intent: LIMIT
    # Action: warn
    # Ambiguous: False
    allow_c3_limi := {"allow": true, "reason": "Clause C3: Limit - STRICT"} if {
        input.allowancetype == "Lodging & Boarding"
    input.tourlocation == "India"
    input.ratesource == "Table 4"
    input.ratelimitation == "maximum permissible"
    input.billrequirement == "actual bills"
    input.taxinclusion == "exclusive of taxes"
    }


    # Rule: C30
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c30_limi := {"allow": true, "reason": "Clause C30: Limit - STRICT"} if {
        input.employeegrade == "M2B"
    input.travelmode == "Train (AC II) /Taxi (AC)"
    input.taxirate == "10 Rs/KM"
    }


    # Rule: C31
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c31_limi := {"allow": true, "reason": "Clause C31: Limit - STRICT"} if {
        true
    }


    # Rule: C32
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c32_info := {"allow": true, "reason": "Clause C32: Informational - OK"} if {
        true
    }


    # Rule: C33
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c33_info := {"allow": true, "reason": "Clause C33: Informational - OK"} if {
        true
    }


    # Rule: C34
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c34_cond := {"allow": true, "reason": "Clause C34: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C35
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c35_info := {"allow": true, "reason": "Clause C35: Informational - OK"} if {
        true
    }


    # Rule: C36
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c36_limi := {"allow": true, "reason": "Clause C36: Limit - STRICT"} if {
        true
    }


    # Rule: C37
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c37_limi := {"allow": true, "reason": "Clause C37: Limit - STRICT"} if {
        true
    }


    # Rule: C38
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c38_limi := {"allow": true, "reason": "Clause C38: Limit - STRICT"} if {
        true
    }


    # Rule: C39
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c39_limi := {"allow": true, "reason": "Clause C39: Limit - STRICT"} if {
        true
    }


    # Rule: C4
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c4_cond := {"allow": true, "reason": "Clause C4: Conditional Allowance - CONDITIONAL"} if {
        input.eligibledesignations == "Directors, CEO, COO, or President"
    input.employeegrade == "M1"
    input.airtravelclass == "Economy"
    input.traintravelclass == "AC I, II"
    input.taxitravelclassintercity == "AC"
    input.taxitravelclasslocal == "AC"
    }


    # Rule: C40
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c40_rest := {"allow": true, "reason": "Clause C40: Restriction - YES"} if {
        true
    }


    # Rule: C41
    # Intent: APPROVAL_REQUIRED
    # Action: enforce
    # Ambiguous: False
    allow_c41_appr := {"allow": true, "reason": "Clause C41: Approval Required - CONDITIONAL"} if {
        true
    }


    # Rule: C42
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c42_limi := {"allow": true, "reason": "Clause C42: Limit - STRICT"} if {
        true
    }


    # Rule: C43
    # Intent: APPROVAL_REQUIRED
    # Action: enforce
    # Ambiguous: False
    allow_c43_appr := {"allow": true, "reason": "Clause C43: Approval Required - CONDITIONAL"} if {
        true
    }


    # Rule: C44
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c44_rest := {"allow": true, "reason": "Clause C44: Restriction - YES"} if {
        true
    }


    # Rule: C45
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c45_rest := {"allow": true, "reason": "Clause C45: Restriction - YES"} if {
        true
    }


    # Rule: C46
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c46_cond := {"allow": true, "reason": "Clause C46: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C47
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c47_cond := {"allow": true, "reason": "Clause C47: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C48
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c48_rest := {"allow": true, "reason": "Clause C48: Restriction - YES"} if {
        true
    }


    # Rule: C49
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c49_rest := {"allow": true, "reason": "Clause C49: Restriction - YES"} if {
        true
    }


    # Rule: C5
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c5_cond := {"allow": true, "reason": "Clause C5: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C50
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c50_rest := {"allow": true, "reason": "Clause C50: Restriction - YES"} if {
        true
    }


    # Rule: C51
    # Intent: APPROVAL_REQUIRED
    # Action: warn
    # Ambiguous: False
    allow_c51_appr := {"allow": true, "reason": "Clause C51: Approval Required - CONDITIONAL"} if {
        true
    }


    # Rule: C52
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c52_cond := {"allow": true, "reason": "Clause C52: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C53
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c53_cond := {"allow": true, "reason": "Clause C53: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C54
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c54_info := {"allow": true, "reason": "Clause C54: Informational - OK"} if {
        true
    }


    # Rule: C55
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c55_rest := {"allow": true, "reason": "Clause C55: Restriction - YES"} if {
        true
    }


    # Rule: C6
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c6_cond := {"allow": true, "reason": "Clause C6: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C7
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c7_cond := {"allow": true, "reason": "Clause C7: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C8
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c8_cond := {"allow": true, "reason": "Clause C8: Conditional Allowance - CONDITIONAL"} if {
        input.eligiblegrades == "M5, M6"
    input.intercitytravelmodes == "Train & Bus (Sleeper) / Shared Taxi / Auto"
    input.localtravelmodes == "Auto, Taxi (Non-AC)"
    input.autodistancelimit == "10 KM"
    input.publictransportdistancethreshold == "10 KM"
    }


    # Rule: C9
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c9_limi := {"allow": true, "reason": "Clause C9: Limit - STRICT"} if {
        true
    }