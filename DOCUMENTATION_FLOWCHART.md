# Documentation Structure Diagram (Draw.io Compatible)

## Mermaid Diagram for Draw.io Import

```mermaid
graph TB
    Start["🚀 START HERE<br/>README_DOCUMENTATION.txt<br/>(12 KB - 5 min)"]
    
    QuickStart["⭐ QUICK_START.md<br/>(15 KB - 10 min)<br/>7-Stage Overview<br/>Performance Summary<br/>Debugging Tips"]
    
    StagesBreakdown["📖 STAGES_BREAKDOWN.md<br/>(22 KB - 25 min)<br/>Detailed Stage Logic<br/>JSON Examples<br/>Regex Patterns"]
    
    GeminiInt["🤖 GEMINI_INTERACTIONS.md<br/>(28 KB - 30 min)<br/>API Calls by Stage<br/>Prompts & Templates<br/>Error Handling<br/>Rate Limiting"]
    
    CompleteClass["📚 COMPLETE_CLASS_MAP.md<br/>(34 KB - 35 min)<br/>Class References<br/>Method Signatures<br/>Data Flow<br/>File Locations"]
    
    DocIndex["🗂️ DOCUMENTATION_INDEX.md<br/>(13 KB - 10 min)<br/>Navigation Guide<br/>Quick References<br/>Source Locations"]
    
    Start -->|Read First| QuickStart
    
    QuickStart -->|Want Details?| StagesBreakdown
    QuickStart -->|Want API Info?| GeminiInt
    QuickStart -->|Want Code Ref?| CompleteClass
    QuickStart -->|Need Navigation?| DocIndex
    
    StagesBreakdown -->|Need Prompts?| GeminiInt
    StagesBreakdown -->|Need Methods?| CompleteClass
    StagesBreakdown -->|Need Guide?| DocIndex
    
    GeminiInt -->|Need Classes?| CompleteClass
    GeminiInt -->|Need Nav?| DocIndex
    
    CompleteClass -->|Need Nav?| DocIndex
    
    style Start fill:#ff6b6b,stroke:#c92a2a,color:#fff,stroke-width:3px
    style QuickStart fill:#4dabf7,stroke:#1971c2,color:#fff,stroke-width:2px
    style StagesBreakdown fill:#69db7c,stroke:#2b8a3e,color:#fff
    style GeminiInt fill:#a78bfa,stroke:#7c3aed,color:#fff
    style CompleteClass fill:#ffd93d,stroke:#f59f00,color:#000
    style DocIndex fill:#74c0fc,stroke:#1971c2,color:#fff
```

---

## Reading Paths by Use Case

```mermaid
graph LR
    subgraph NewDev["🆕 NEW TO CODEBASE"]
        N1["README_DOCUMENTATION.txt"]
        N2["QUICK_START.md"]
        N3["STAGES_BREAKDOWN.md"]
        N4["(Source Code)"]
    end
    
    subgraph DebugDev["🐛 DEBUGGING ISSUE"]
        D1["QUICK_START.md<br/>Quick Debugging"]
        D2["mechanism.log"]
        D3["STAGES_BREAKDOWN.md<br/>Specific Stage"]
        D4["COMPLETE_CLASS_MAP.md<br/>Methods"]
    end
    
    subgraph ModifyDev["✏️ MODIFY CODE"]
        M1["COMPLETE_CLASS_MAP.md<br/>Class/Stage"]
        M2["GEMINI_INTERACTIONS.md<br/>If Uses Gemini"]
        M3["Source Code"]
        M4["mechanism.log"]
    end
    
    subgraph APIIntDev["🔌 GEMINI INTEGRATION"]
        A1["GEMINI_INTERACTIONS.md"]
        A2["Specific Stage Section"]
        A3["Prompts & Examples"]
        A4["Error Handling Code"]
    end
    
    subgraph DataFlowDev["🔄 UNDERSTAND DATA FLOW"]
        F1["STAGES_BREAKDOWN.md<br/>Stage-by-stage"]
        F2["COMPLETE_CLASS_MAP.md<br/>Flow Diagram"]
        F3["Output JSON Files"]
    end
    
    N1 --> N2 --> N3 --> N4
    D1 --> D2 --> D3 --> D4
    M1 --> M2 --> M3 --> M4
    A1 --> A2 --> A3 --> A4
    F1 --> F2 --> F3
    
    style NewDev fill:#e7f5ff
    style DebugDev fill:#fff3bf
    style ModifyDev fill:#f3e5f5
    style APIIntDev fill:#f0f4ff
    style DataFlowDev fill:#e0f2f1
```

---

## Content Coverage Matrix

```mermaid
graph TB
    subgraph Stages["7 PIPELINE STAGES"]
        S0["Stage 0<br/>DocumentStructureAnalyzer"]
        S1B["Stage 1B<br/>ClauseExtractor"]
        S2["Stage 2<br/>IntentClassifier"]
        S3["Stage 3<br/>GenericEntityExtractor"]
        S4["Stage 4<br/>GenericAmbiguityDetector"]
        S5["Stage 5<br/>AmbiguityClarifier"]
        S6["Stage 6<br/>DSLGenerator"]
    end
    
    subgraph Topics["DOCUMENTATION TOPICS"]
        T1["Gemini API Usage"]
        T2["Prompts & Templates"]
        T3["Error Handling"]
        T4["Methods & Signatures"]
        T5["Data Flow"]
        T6["Performance"]
        T7["Configuration"]
    end
    
    subgraph Files["DOCUMENTATION FILES"]
        F1["QUICK_START.md"]
        F2["STAGES_BREAKDOWN.md"]
        F3["GEMINI_INTERACTIONS.md"]
        F4["COMPLETE_CLASS_MAP.md"]
        F5["DOCUMENTATION_INDEX.md"]
    end
    
    S0 -.->|Covered in| F1
    S1B -.->|Covered in| F1
    S2 -.->|Covered in| F1
    S3 -.->|Covered in| F1
    S4 -.->|Covered in| F1
    S5 -.->|Covered in| F1
    S6 -.->|Covered in| F1
    
    T1 -.->|In| F3
    T2 -.->|In| F3
    T3 -.->|In| F3
    T4 -.->|In| F4
    T5 -.->|In| F2
    T6 -.->|In| F1
    T7 -.->|In| F5
    
    style Stages fill:#e7f5ff
    style Topics fill:#f3e5f5
    style Files fill:#fff3bf
```

---

## Document Dependency Graph

```mermaid
graph LR
    README["README_DOCUMENTATION.txt<br/>Entry Point"]
    
    README -->|First| QS["QUICK_START.md"]
    
    QS -->|Want Details| SB["STAGES_BREAKDOWN.md"]
    QS -->|Want API| GI["GEMINI_INTERACTIONS.md"]
    QS -->|Want Ref| CCM["COMPLETE_CLASS_MAP.md"]
    QS -->|Need Nav| DI["DOCUMENTATION_INDEX.md"]
    
    SB -->|Need Prompts| GI
    SB -->|Need Methods| CCM
    SB -->|Need Nav| DI
    
    GI -->|Need Classes| CCM
    GI -->|Need Nav| DI
    
    CCM -->|Need Nav| DI
    
    QS -.->|Code: 6 Files| Code["Source Code<br/>policy_validator.py<br/>policy_agnostic_stages.py<br/>policy_validator_stage0_new.py"]
    
    SB -.->|Output Files| OUT["JSON/YAML Output<br/>stage0_structured_document.json<br/>stage1_clauses.json<br/>...<br/>stage6_dsl_rules.yaml"]
    
    GI -.->|Logs| LOG["mechanism.log<br/>Execution Details"]
    
    style README fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style QS fill:#4dabf7,stroke:#1971c2,color:#fff
    style SB fill:#69db7c,stroke:#2b8a3e,color:#fff
    style GI fill:#a78bfa,stroke:#7c3aed,color:#fff
    style CCM fill:#ffd93d,stroke:#f59f00,color:#000
    style DI fill:#74c0fc,stroke:#1971c2,color:#fff
    style Code fill:#e0e7ff,stroke:#666
    style OUT fill:#e0e7ff,stroke:#666
    style LOG fill:#e0e7ff,stroke:#666
```

---

## Topic Coverage by Document

```mermaid
graph TB
    subgraph QS["QUICK_START.md"]
        QS1["✅ 7-Stage Overview"]
        QS2["✅ Stage Purpose & I/O"]
        QS3["✅ Gemini Usage Summary"]
        QS4["✅ Performance Table"]
        QS5["✅ Debugging Tips"]
        QS6["✅ Running Instructions"]
    end
    
    subgraph SB["STAGES_BREAKDOWN.md"]
        SB1["✅ Detailed Stage Logic"]
        SB2["✅ Method Signatures"]
        SB3["✅ JSON Examples"]
        SB4["✅ Regex Patterns"]
        SB5["✅ Data Flow per Stage"]
        SB6["✅ Error Handling"]
    end
    
    subgraph GI["GEMINI_INTERACTIONS.md"]
        GI1["✅ API Calls per Stage"]
        GI2["✅ Complete Prompts"]
        GI3["✅ JSON Parsing Code"]
        GI4["✅ Rate Limiting Code"]
        GI5["✅ Error Recovery"]
        GI6["✅ LangChain Details"]
    end
    
    subgraph CCM["COMPLETE_CLASS_MAP.md"]
        CCM1["✅ Class Locations"]
        CCM2["✅ Method Signatures"]
        CCM3["✅ Attributes & Deps"]
        CCM4["✅ Complete Flow Diagram"]
        CCM5["✅ File Locations"]
        CCM6["✅ Support Classes"]
    end
    
    subgraph DI["DOCUMENTATION_INDEX.md"]
        DI1["✅ Reading Guide"]
        DI2["✅ Quick References"]
        DI3["✅ Source Locations"]
        DI4["✅ Common Tasks"]
        DI5["✅ Key Concepts"]
        DI6["✅ Troubleshooting"]
    end
    
    style QS fill:#e7f5ff,stroke:#1971c2
    style SB fill:#e7ffe0,stroke:#2b8a3e
    style GI fill:#f3e5f5,stroke:#7c3aed
    style CCM fill:#fff9e6,stroke:#f59f00
    style DI fill:#e0f2f1,stroke:#1971c2
```

---

## Integration with Codebase

```mermaid
graph TB
    DOCS["📚 DOCUMENTATION<br/>(6 Files - 124 KB)"]
    
    CODE["💻 SOURCE CODE<br/>(7000+ Lines)"]
    
    OUTPUT["📊 OUTPUT FILES<br/>(7 JSON/YAML)"]
    
    LOGS["📋 LOGS<br/>(mechanism.log)"]
    
    SUBGRAPH1["Stage Classes<br/>- DocumentStructureAnalyzer<br/>- ClauseExtractor<br/>- IntentClassifier<br/>- EntityExtractor<br/>- AmbiguityDetector<br/>- AmbiguityClarifier<br/>- DSLGenerator"]
    
    SUBGRAPH2["Support Classes<br/>- PipelineConfig<br/>- PipelineStageStorage<br/>- AmbiguityClarificationEngine"]
    
    DOCS -->|Explains| CODE
    CODE -->|Generates| OUTPUT
    CODE -->|Writes| LOGS
    
    CODE -->|Contains| SUBGRAPH1
    CODE -->|Contains| SUBGRAPH2
    
    DOCS -->|References| SUBGRAPH1
    DOCS -->|References| SUBGRAPH2
    
    OUTPUT -->|Described in| DOCS
    LOGS -->|Analyzed via| DOCS
    
    style DOCS fill:#4dabf7,stroke:#1971c2,color:#fff,stroke-width:3px
    style CODE fill:#69db7c,stroke:#2b8a3e,color:#fff,stroke-width:2px
    style OUTPUT fill:#ffd93d,stroke:#f59f00,color:#000
    style LOGS fill:#a78bfa,stroke:#7c3aed,color:#fff
    style SUBGRAPH1 fill:#e7f5ff,stroke:#1971c2
    style SUBGRAPH2 fill:#f3e5f5,stroke:#7c3aed
```

---

## Quick Navigation Tree

```mermaid
graph TD
    A["📚 DOCUMENTATION"]
    
    A1["README_DOCUMENTATION.txt<br/>(Welcome + Quick Ref)"]
    A2["QUICK_START.md<br/>(10 min Overview)"]
    A3["STAGES_BREAKDOWN.md<br/>(25 min Details)"]
    A4["GEMINI_INTERACTIONS.md<br/>(30 min API Guide)"]
    A5["COMPLETE_CLASS_MAP.md<br/>(35 min Code Ref)"]
    A6["DOCUMENTATION_INDEX.md<br/>(10 min Navigation)"]
    
    B1["Use Case: Learning"]
    B2["Use Case: Debugging"]
    B3["Use Case: Development"]
    B4["Use Case: API Mods"]
    B5["Use Case: Performance"]
    
    A --> A1
    A1 --> A2
    
    A2 --> B1
    A2 --> B2
    A2 --> B3
    A2 --> B4
    A2 --> B5
    
    B1 -.->|Read| A3
    B2 -.->|Check| A3
    B3 -.->|Reference| A5
    B4 -.->|Check| A4
    B5 -.->|See| A3
    
    A3 -.->|For Prompts| A4
    A3 -.->|For Classes| A5
    A4 -.->|For Methods| A5
    
    A3 --> A6
    A4 --> A6
    A5 --> A6
    
    style A fill:#4dabf7,stroke:#1971c2,color:#fff,stroke-width:3px
    style A1 fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style A2 fill:#4dabf7,stroke:#1971c2,color:#fff
    style A3 fill:#69db7c,stroke:#2b8a3e,color:#fff
    style A4 fill:#a78bfa,stroke:#7c3aed,color:#fff
    style A5 fill:#ffd93d,stroke:#f59f00,color:#000
    style A6 fill:#74c0fc,stroke:#1971c2,color:#fff
    style B1 fill:#e7f5ff,stroke:#1971c2
    style B2 fill:#fff3bf,stroke:#f59f00
    style B3 fill:#f3e5f5,stroke:#7c3aed
    style B4 fill:#f0f4ff,stroke:#7c3aed
    style B5 fill:#e0f2f1,stroke:#1971c2
```

---

## How to Import to Draw.io

### Method 1: Copy Mermaid Code
1. Go to https://app.diagrams.net/
2. Create new diagram
3. Click `More Shapes` → Search for `Mermaid`
4. Add Mermaid shape to canvas
5. Double-click and paste the mermaid code above
6. Click Apply

### Method 2: Use Mermaid Live Editor
1. Go to https://mermaid.live/
2. Paste any Mermaid code from above
3. Click "Copy SVG" or "Export as PNG"
4. Import into Draw.io

### Method 3: Direct Import
1. Go to https://app.diagrams.net/
2. Click `File` → `Import from` → `URL`
3. Use Mermaid diagram URL

---

## File Structure Visualization

```mermaid
graph LR
    Root["docupolicy/"]
    
    Src["Source Code"]
    Docs["Documentation"]
    Output["Generated Output"]
    
    Root --> Src
    Root --> Docs
    Root --> Output
    
    Src --> SrcFiles["policy_validator.py<br/>policy_agnostic_stages.py<br/>policy_validator_stage0_new.py<br/>generic_policy_enhancer.py"]
    
    Docs --> DocFiles["✅ README_DOCUMENTATION.txt<br/>✅ QUICK_START.md<br/>✅ STAGES_BREAKDOWN.md<br/>✅ GEMINI_INTERACTIONS.md<br/>✅ COMPLETE_CLASS_MAP.md<br/>✅ DOCUMENTATION_INDEX.md"]
    
    Output --> OutFiles["stage0_structured_document.json<br/>stage1_clauses.json<br/>stage2_classified.json<br/>stage3_entities.json<br/>stage4_ambiguity_flags.json<br/>stage5_clarified_clauses.json<br/>stage6_dsl_rules.yaml<br/>mechanism.log"]
    
    style Root fill:#4dabf7,stroke:#1971c2,color:#fff
    style Src fill:#69db7c,stroke:#2b8a3e,color:#fff
    style Docs fill:#a78bfa,stroke:#7c3aed,color:#fff
    style Output fill:#ffd93d,stroke:#f59f00,color:#000
    style DocFiles fill:#f3e5f5,stroke:#7c3aed
```

---

## Recommended Reading Order

```mermaid
graph TD
    Start["START: New to Codebase?"]
    
    Start -->|YES| A["Read README_DOCUMENTATION.txt<br/>(5 min)"]
    Start -->|NO| Skip["Skip to Use Case"]
    
    A --> B["Read QUICK_START.md<br/>(10 min)"]
    
    B --> Q{What Next?}
    
    Q -->|Understand Logic| C["Read STAGES_BREAKDOWN.md<br/>(25 min)"]
    Q -->|Modify Gemini| D["Read GEMINI_INTERACTIONS.md<br/>(30 min)"]
    Q -->|Code Reference| E["Read COMPLETE_CLASS_MAP.md<br/>(35 min)"]
    Q -->|Need Navigation| F["Read DOCUMENTATION_INDEX.md<br/>(10 min)"]
    
    C --> Debug{Need More?}
    D --> Debug
    E --> Debug
    F --> Debug
    
    Debug -->|Specific Stage| C
    Debug -->|API Issues| D
    Debug -->|Methods| E
    Debug -->|Navigation| F
    Debug -->|Source Code| Code["Check Source Code"]
    
    Skip --> Q
    Code --> Done["Ready to Code!"]
    
    style Start fill:#4dabf7,stroke:#1971c2,color:#fff
    style A fill:#ff6b6b,stroke:#c92a2a,color:#fff
    style B fill:#4dabf7,stroke:#1971c2,color:#fff
    style C fill:#69db7c,stroke:#2b8a3e,color:#fff
    style D fill:#a78bfa,stroke:#7c3aed,color:#fff
    style E fill:#ffd93d,stroke:#f59f00,color:#000
    style F fill:#74c0fc,stroke:#1971c2,color:#fff
    style Code fill:#e7f5ff,stroke:#1971c2
    style Done fill:#51cf66,stroke:#2b8a3e,color:#fff
```

