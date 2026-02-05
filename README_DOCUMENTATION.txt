================================================================================
                    POLICY VALIDATOR - DOCUMENTATION GUIDE
================================================================================

WELCOME! This directory now contains COMPLETE documentation of the 7-stage 
policy validation pipeline.

================================================================================
                              START HERE ⭐
================================================================================

If you're new to this codebase, read these in order:

1. QUICK_START.md (15 KB - 10 minutes)
   └─ High-level overview of all 7 stages
   └─ Quick debugging tips
   └─ Performance summary

2. STAGES_BREAKDOWN.md (22 KB - 25 minutes)
   └─ Detailed breakdown of each stage
   └─ Example JSON outputs
   └─ Methods and regex patterns

3. GEMINI_INTERACTIONS.md (28 KB - 30 minutes)
   └─ How Gemini is used in each stage
   └─ Complete prompt templates
   └─ Error handling strategies

4. COMPLETE_CLASS_MAP.md (34 KB - 35 minutes)
   └─ Exhaustive class reference
   └─ Method signatures
   └─ Data flow details

5. DOCUMENTATION_INDEX.md (16 KB - 10 minutes)
   └─ Navigation guide
   └─ Quick reference tables
   └─ Common tasks

================================================================================
                            WHAT YOU'LL LEARN
================================================================================

After reading these documents, you'll understand:

✅ How the 7-stage pipeline works (PDF → DSL Rules)
✅ What each stage does and its input/output
✅ How Gemini AI is integrated at each stage
✅ Parallel processing and performance optimization
✅ Error handling and recovery strategies
✅ How to debug individual stages
✅ Complete class and method reference
✅ Data flow through the pipeline
✅ Configuration and customization options

================================================================================
                            PIPELINE OVERVIEW
================================================================================

PDF Document
    ↓
Stage 0: DocumentStructureAnalyzer (Extract sections + annexures)
    ↓ stage0_structured_document.json
Stage 1B: ClauseExtractor (Extract individual clauses)
    ↓ stage1_clauses.json
Stage 2: IntentClassifier (Classify intent: RESTRICTION, LIMIT, etc.)
    ↓ stage2_classified.json
Stage 3: GenericEntityExtractor (Extract entities: amounts, durations, etc.)
    ↓ stage3_entities.json
Stage 4: GenericAmbiguityDetector (Detect vague language)
    ↓ stage4_ambiguity_flags.json
Stage 5: AmbiguityClarifier (Clarify ambiguities with context)
    ↓ stage5_clarified_clauses.json
Stage 6: DSLGenerator (Generate executable DSL rules)
    ↓ stage6_dsl_rules.yaml
Executable Rules → Enforcement Engine

Total Time: ~2-3 minutes
Gemini Calls: ~80
Workers: 8 parallel

================================================================================
                          DOCUMENT DESCRIPTIONS
================================================================================

QUICK_START.md
  • Perfect for getting started quickly
  • 7-stage overview with diagrams
  • Key methods and purpose for each class
  • Performance summary table
  • Debugging tips
  • Running instructions

STAGES_BREAKDOWN.md
  • Deep dive into each of 7 stages
  • Input/output specifications
  • JSON example outputs
  • Regex patterns explained
  • Methods listed with descriptions
  • Parallel processing details
  • Error handling for each stage

GEMINI_INTERACTIONS.md
  • How Gemini API is called at each stage
  • Complete prompt templates shown
  • JSON parsing and error handling
  • Rate limiting strategy (exponential backoff)
  • LangChain integration details
  • Summary table: all stages, hit rates
  • Real code examples with explanations

COMPLETE_CLASS_MAP.md
  • Full class reference for all 7 stages
  • Method signatures and docstrings
  • Key attributes and dependencies
  • Support classes (Config, Storage)
  • Complete data flow diagram
  • Quick reference tables
  • File locations in codebase

DOCUMENTATION_INDEX.md
  • Reading guide (different entry points)
  • Quick reference tables (Gemini usage, performance)
  • Source code locations
  • Key concepts explained
  • Common tasks and debugging
  • Feedback and updates

================================================================================
                          QUICK REFERENCE
================================================================================

WHAT DOES EACH STAGE DO?

Stage 0: Parse document structure, extract sections & annexures
Stage 1B: Extract individual policy clauses
Stage 2: Classify clause intent (RESTRICTION, LIMIT, etc.) - Uses Gemini
Stage 3: Extract entities (amounts, durations, roles) - Uses Gemini
Stage 4: Detect ambiguous language (vague/unclear terms)
Stage 5: Clarify ambiguous clauses with policy context - Uses Gemini
Stage 6: Generate executable DSL rules - Uses Gemini (fallback)

GEMINI USAGE SUMMARY

Stage 0: ❌ NO (Regex-based)
Stage 1B: ✅ YES (1 API call) - LangChain or Direct
Stage 2: ✅ YES (25 API calls) - 8 parallel workers
Stage 3: ✅ YES (25 API calls) - 8 parallel workers
Stage 4: ❌ NO (Rule-based heuristics)
Stage 5: ✅ YES (~8 API calls) - Only ambiguous clauses
Stage 6: ✅ YES (~2-3 API calls) - Only when pattern fails

Total: ~80 API calls for 25-clause policy

PERFORMANCE

Total Time: 175 seconds (~3 minutes)
Parallelization: 8 workers on stages 2,3,5,6 = ~8x faster
Success Rate: 85-95% depending on stage

OUTPUT FILES

stage0_structured_document.json - Parsed document structure
stage1_clauses.json - Individual clauses
stage2_classified.json - Clauses with intent + confidence
stage3_entities.json - Extracted entities
stage4_ambiguity_flags.json - Ambiguity scores and reasons
stage5_clarified_clauses.json - Clarified text + confidence
stage6_dsl_rules.yaml - Executable DSL rules

================================================================================
                          GETTING STARTED
================================================================================

READING DIFFERENT ENTRY POINTS:

I want to understand the pipeline quickly:
  → Start with QUICK_START.md

I want to debug a specific stage:
  → Check QUICK_START.md "Quick Debugging" section
  → Then STAGES_BREAKDOWN.md for that stage
  → Then COMPLETE_CLASS_MAP.md for method details

I want to modify Gemini integration:
  → Start with GEMINI_INTERACTIONS.md
  → Then COMPLETE_CLASS_MAP.md for class details

I want to understand data flow:
  → STAGES_BREAKDOWN.md shows stage-by-stage flow
  → COMPLETE_CLASS_MAP.md has complete flow diagram

I want a method reference:
  → COMPLETE_CLASS_MAP.md has all methods with signatures

================================================================================
                        COMMON TROUBLESHOOTING
================================================================================

Problem: Understanding Stage 2 Intent Classification
  Solution: Read QUICK_START.md "Stage 2" → 7 Intent Types table
           Then COMPLETE_CLASS_MAP.md "STAGE 2"

Problem: Debugging Gemini API errors
  Solution: Read GEMINI_INTERACTIONS.md "Gemini API Error Handling"
           Check mechanism.log for execution details

Problem: Understanding rate limiting
  Solution: Read GEMINI_INTERACTIONS.md "Rate Limiting (429 Error)"
           Shows exponential backoff strategy

Problem: Modifying Stage 3 Entity Extraction
  Solution: Read COMPLETE_CLASS_MAP.md "STAGE 3"
           Read GEMINI_INTERACTIONS.md "Stage 3: Entity Extraction"

Problem: Understanding DSL Rules
  Solution: Read QUICK_START.md "Stage 6"
           Read COMPLETE_CLASS_MAP.md "STAGE 6"
           Check stage6_dsl_rules.yaml for examples

================================================================================
                            KEY TAKEAWAYS
================================================================================

1. ARCHITECTURE
   - 7-stage pipeline: PDF → DSL Rules
   - Stages 2,3,5,6 use Gemini; others rule-based or regex
   - Parallel processing on stages 2,3,5,6 (8 workers each)

2. GEMINI INTEGRATION
   - ~80 API calls total for 25 clauses
   - Temperature 0.1 (deterministic)
   - Rate limiting with exponential backoff
   - LangChain optional (provides Pydantic validation)

3. DATA FLOW
   - Each stage outputs JSON → next stage's input
   - Stage 4 (ambiguity detection) is critical for Stage 5 clarification
   - Stage 6 uses 3-step approach: Index (90%) → Pattern (5%) → LLM (5%)

4. ERROR HANDLING
   - All stages have thread-safe logging
   - JSON parse errors return defaults
   - Rate limits trigger retry with backoff
   - MongoDB optional (continues without it)

5. CONFIGURATION
   - PipelineConfig centralizes all settings
   - Temperature, workers, chunk size, timeouts all configurable
   - Ambiguity detection has "strict mode"

================================================================================
                        FILE SIZES & READ TIME
================================================================================

QUICK_START.md              15 KB   10 min   (Overview)
STAGES_BREAKDOWN.md         22 KB   25 min   (Details)
GEMINI_INTERACTIONS.md      28 KB   30 min   (API Integration)
COMPLETE_CLASS_MAP.md       34 KB   35 min   (Class Reference)
DOCUMENTATION_INDEX.md      16 KB   10 min   (Navigation)

Total: ~115 KB, ~110 minutes of reading material

But you don't need to read it all at once!
Start with QUICK_START.md, then read what you need.

================================================================================
                          WHEN TO READ EACH
================================================================================

New to the codebase?
  → QUICK_START.md (15 min) + STAGES_BREAKDOWN.md (25 min) = 40 min start

Need to modify a stage?
  → COMPLETE_CLASS_MAP.md for that stage (10 min)
  → GEMINI_INTERACTIONS.md if it uses Gemini (5 min)
  → Source code for implementation (variable)

Debugging an issue?
  → QUICK_START.md "Quick Debugging" (2 min)
  → mechanism.log for execution details (variable)
  → COMPLETE_CLASS_MAP.md for class details (5 min)

Want to understand performance?
  → QUICK_START.md "Performance Summary" table (2 min)
  → STAGES_BREAKDOWN.md "Performance Characteristics" (5 min)

Want to understand Gemini integration?
  → GEMINI_INTERACTIONS.md (30 min - complete coverage)
  → Source code for specific implementation (variable)

================================================================================
                            SUPPORT & UPDATES
================================================================================

These documents were created: Feb 3, 2026

Keep them updated as you:
- Fix bugs
- Add features
- Modify prompts
- Change configuration
- Add new stages

The DOCUMENTATION_INDEX.md includes a "Feedback & Updates" section.

================================================================================
                        ENJOY THE CODEBASE! 🚀
================================================================================

You now have complete documentation of the policy validation pipeline.

Next steps:
1. Read QUICK_START.md for overview
2. Run a test policy through the pipeline
3. Check mechanism.log for execution details
4. Read STAGES_BREAKDOWN.md for deeper understanding
5. Refer to COMPLETE_CLASS_MAP.md for implementation details

Questions? Check DOCUMENTATION_INDEX.md for navigation guide.

Happy coding!
