package data.travel_policy

# Enforced policy rules for travel_policy



    # Rule: C1
    # Intent: LIMIT
    # Action: warn
    # Ambiguous: False
    allow_c1_limi := {"allow": true, "reason": "Clause C1: Limit - STRICT"} if {
        input.travelregion == "India"
    input.travelpurpose == "official business travel"
    }


    # Rule: C10
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c10_cond := {"allow": true, "reason": "Clause C10: Conditional Allowance - CONDITIONAL"} if {
        input.m1gradecategoryacitylodgingallowance == 4000
    input.m1gradecategoryblodgingallowance == 3000
    }


    # Rule: C11
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c11_info := {"allow": true, "reason": "Clause C11: Informational - OK"} if {
        input.boardingallowancebasis == "employee grade"
    input.tablereference == "Table 5"
    input.m1gradeboardingallowance == "Actual boarding allowance"
    }


    # Rule: C12
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c12_cond := {"allow": true, "reason": "Clause C12: Conditional Allowance - CONDITIONAL"} if {
        input.employeegradeexample == "M1"
    input.personalincidentalallowance == "Actual"
    }


    # Rule: C13
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c13_cond := {"allow": true, "reason": "Clause C13: Conditional Allowance - CONDITIONAL"} if {
        input.lodgingreimbursementrate == "Rs. 250 per day"
    input.lodgingtype == "relative’s or friend’s place"
    }


    # Rule: C14
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c14_cond := {"allow": true, "reason": "Clause C14: Conditional Allowance - CONDITIONAL"} if {
        input.fourwheelerrate == "7.0 Rs/KM"
    input.twowheelerrate == "2.5 Rs/KM"
    }


    # Rule: C15
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c15_cond := {"allow": true, "reason": "Clause C15: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C16
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c16_cond := {"allow": true, "reason": "Clause C16: Conditional Allowance - CONDITIONAL"} if {
        input.minimumtravelduration >= 3
    input.maximumtravelduration <= 12
    input.dailyallowancepercentage == "50%"
    }


    # Rule: C17
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c17_cond := {"allow": true, "reason": "Clause C17: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C18
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c18_rest := {"allow": true, "reason": "Clause C18: Restriction - YES"} if {
        true
    }


    # Rule: C19
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c19_cond := {"allow": true, "reason": "Clause C19: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C2
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c2_cond := {"allow": true, "reason": "Clause C2: Conditional Allowance - CONDITIONAL"} if {
        input.tourdurationmaxdays == "15 days"
    input.deputationdurationmindays == "15 days"
    input.deputationdurationmaxyears == "1 year"
    input.transferdurationminyears == ">1 year"
    input.tourclassification == "Tour"
    input.deputationclassification == "Deputation"
    input.transferclassification == "Transfer"
    }


    # Rule: C20
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c20_cond := {"allow": true, "reason": "Clause C20: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C21
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c21_cond := {"allow": true, "reason": "Clause C21: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C22
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c22_rest := {"allow": true, "reason": "Clause C22: Restriction - YES"} if {
        true
    }


    # Rule: C23
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c23_cond := {"allow": true, "reason": "Clause C23: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C24
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c24_cond := {"allow": true, "reason": "Clause C24: Conditional Allowance - CONDITIONAL"} if {
        input.minimumrelocationdistance >= 100
    }


    # Rule: C25
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c25_cond := {"allow": true, "reason": "Clause C25: Conditional Allowance - CONDITIONAL"} if {
        input.relocationduration == "7 days"
    }


    # Rule: C26
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c26_info := {"allow": true, "reason": "Clause C26: Informational - OK"} if {
        input.graderange == "M1 to M6"
    }


    # Rule: C27
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c27_info := {"allow": true, "reason": "Clause C27: Informational - OK"} if {
        input.citycategorya == "NCR, Kolkata, Chennai, Mumbai, Hyderabad, Bangalore, Pune, Ahmedabad, Chandigarh, Capitals"
    input.citycategoryb == "All other cities"
    }


    # Rule: C28
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c28_cond := {"allow": true, "reason": "Clause C28: Conditional Allowance - CONDITIONAL"} if {
        input.gradem1m2travelmode == "Air (Economy)"
    input.gradem2btravelmode == "Train (AC II)/Taxi (AC)"
    input.gradem3travelmode == "Train (III AC)/Bus/Taxi(AC)"
    input.gradem4travelmode == "Train (III AC)/Bus(AC)/Shared Taxi/Auto"
    input.gradem5m6travelmode == "Train & Bus (Sleeper)/Shared Taxi/Auto/Public Conveyance"
    }


    # Rule: C29
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c29_cond := {"allow": true, "reason": "Clause C29: Conditional Allowance - CONDITIONAL"} if {
        input.taxiacrate == "10 Rs/KM"
    input.ticketdowngradepolicy == "1 class down"
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
        input.entitlementtypes == "Lodging, Boarding, Travel Allowance"
    input.ratetype == "maximum permissible rates"
    input.taxinclusion == "exclusive of taxes"
    }


    # Rule: C31
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c31_rest := {"allow": true, "reason": "Clause C31: Restriction - YES"} if {
        input.requireddocumentation == "bills/invoices"
    }


    # Rule: C32
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c32_limi := {"allow": true, "reason": "Clause C32: Limit - STRICT"} if {
        input.quotationcount == 3
    input.maximumrelocationlimit <= 20
    }


    # Rule: C33
    # Intent: APPROVAL_REQUIRED
    # Action: enforce
    # Ambiguous: False
    allow_c33_appr := {"allow": true, "reason": "Clause C33: Approval Required - CONDITIONAL"} if {
        input.requestsubmissiondeadline == "1 day prior to the date of travel"
    input.reservationemail == "reservation@ujaas.com"
    }


    # Rule: C34
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c34_rest := {"allow": true, "reason": "Clause C34: Restriction - YES"} if {
        input.requiredapproval == "HOD"
    }


    # Rule: C35
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c35_rest := {"allow": true, "reason": "Clause C35: Restriction - YES"} if {
        input.requiredinformation == "employee name, age, designation, contact number, project code, tour purpose, place, DOT, duration, and HOD approval (or reason for absence of HOD approval)"
    }


    # Rule: C36
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c36_cond := {"allow": true, "reason": "Clause C36: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C37
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c37_cond := {"allow": true, "reason": "Clause C37: Conditional Allowance - CONDITIONAL"} if {
        input.minimumrequestleadtime >= one day
    }


    # Rule: C38
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c38_rest := {"allow": true, "reason": "Clause C38: Restriction - YES"} if {
        input.restrictedbookingtypes == "Hotels, Flights, Seats, Web Check-in"
    }


    # Rule: C39
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c39_rest := {"allow": true, "reason": "Clause C39: Restriction - YES"} if {
        input.billsubmissiondeadline == "15 days"
    input.deductiontimeframe == "30 days"
    }


    # Rule: C4
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c4_info := {"allow": true, "reason": "Clause C4: Informational - OK"} if {
        input.employeegrades == "M1-M2"
    input.intercitytravelmodes == "Air (Economy) /Train (AC I, II) /Taxi (AC)"
    input.localtravelmodes == "Taxi (AC)"
    }


    # Rule: C40
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c40_rest := {"allow": true, "reason": "Clause C40: Restriction - YES"} if {
        input.requiredbillinformation == "employee name, designation, department code, tour place, tour date, bill amount, date of submission"
    }


    # Rule: C41
    # Intent: APPROVAL_REQUIRED
    # Action: enforce
    # Ambiguous: False
    allow_c41_appr := {"allow": true, "reason": "Clause C41: Approval Required - CONDITIONAL"} if {
        input.requiredsignatures == "employee and HOD"
    }


    # Rule: C42
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c42_cond := {"allow": true, "reason": "Clause C42: Conditional Allowance - CONDITIONAL"} if {
        input.requiredapproval == "HOD"
    input.deviationhandling == "clarification note REQUIRED"
    }


    # Rule: C43
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: enforce
    # Ambiguous: False
    allow_c43_cond := {"allow": true, "reason": "Clause C43: Conditional Allowance - CONDITIONAL"} if {
        true
    }


    # Rule: C44
    # Intent: INFORMATIONAL
    # Action: enforce
    # Ambiguous: False
    allow_c44_info := {"allow": true, "reason": "Clause C44: Informational - OK"} if {
        true
    }


    # Rule: C45
    # Intent: RESTRICTION
    # Action: enforce
    # Ambiguous: False
    allow_c45_rest := {"allow": true, "reason": "Clause C45: Restriction - YES"} if {
        true
    }


    # Rule: C5
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c5_info := {"allow": true, "reason": "Clause C5: Informational - OK"} if {
        input.employeegrades == "M3"
    input.intercitytravelmodes == "Train (III AC) /Bus/Taxi(AC)"
    input.localtravelmode == "Taxi (AC)"
    }


    # Rule: C6
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c6_info := {"allow": true, "reason": "Clause C6: Informational - OK"} if {
        input.employeegrades == "M4"
    input.intercitytravelmodes == "Train (III AC)/Bus(AC) /Shared Taxi/Auto"
    input.localtravelmodes == "Auto, Taxi (Non-AC)"
    }


    # Rule: C7
    # Intent: INFORMATIONAL
    # Action: warn
    # Ambiguous: False
    allow_c7_info := {"allow": true, "reason": "Clause C7: Informational - OK"} if {
        input.eligibleemployeegrades == "M5/M6"
    input.intercitytravelmodes == "Train & Bus (Sleeper)/Shared Taxi/ Auto"
    input.localtravelmodes == "Auto/Taxi Non-AC"
    }


    # Rule: C8
    # Intent: CONDITIONAL_ALLOWANCE
    # Action: warn
    # Ambiguous: False
    allow_c8_cond := {"allow": true, "reason": "Clause C8: Conditional Allowance - CONDITIONAL"} if {
        input.vehicletypesform2m3 == "hatchback/sedan cars"
    input.vehicletypeswithclient == "Sedan/ SUV cars"
    }


    # Rule: C9
    # Intent: LIMIT
    # Action: enforce
    # Ambiguous: False
    allow_c9_limi := {"allow": true, "reason": "Clause C9: Limit - STRICT"} if {
        input.nonactaxirate == "Rs. 8/KM"
    input.actaxirate == "Rs. 10/KM"
    }