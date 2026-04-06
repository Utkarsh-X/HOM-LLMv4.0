# HOM-LLM(v2.0) — Visual Architecture Report

---

## 1. System Overview Map

```mermaid
graph TB
    subgraph External["External World"]
        USER["👤 User Query"]
        REPO["📂 Code Repository"]
        GEMINI["☁️ Gemini 2.5 Flash API"]
    end

    subgraph Runtime["Runtime Layer"]
        RQ["run_query.py"]
        IR["index_repo.py"]
    end

    subgraph Core["src/homllm"]
        IDX["Indexer Pipeline"]
        RET["Retrieval Pipeline"]
        RANK["Ranking Pipeline"]
        CTX["Context Pipeline"]
        INTEL["Intelligence Controller"]
        GEN["Generation Adapter"]
        CC["Claim Coverage"]
        HALL["Hallucination Detector"]
    end

    subgraph Storage["Storage Layer"]
        TANTIVY["Tantivy BM25"]
        LANCE["LanceDB Vectors"]
        DUCK["DuckDB Metadata"]
        FS["Filesystem Artifacts"]
    end

    subgraph Models["On-Device Models"]
        EMB["Qwen3-Embedding-0.6B"]
        RERANK["Qwen3-Reranker-0.6B"]
    end

    REPO -->|scan & parse| IR
    IR --> IDX
    IDX -->|embed| EMB
    IDX -->|write| TANTIVY
    IDX -->|write| LANCE
    IDX -->|write| DUCK
    IDX -->|write| FS

    USER -->|query| RQ
    RQ --> RET
    RET -->|BM25 search| TANTIVY
    RET -->|vector search| LANCE
    RET -->|embed query| EMB
    RET -->|metadata| DUCK
    RET --> RANK
    RANK -->|cross-encode| RERANK
    RANK --> CTX
    CTX --> CC
    CC --> INTEL
    INTEL --> GEN
    GEN -->|API call| GEMINI
    GEN --> HALL
    HALL -->|answer| USER

    style External fill:#1a1a2e,color:#fff,stroke:#e94560
    style Runtime fill:#16213e,color:#fff,stroke:#0f3460
    style Core fill:#0f3460,color:#fff,stroke:#533483
    style Storage fill:#533483,color:#fff,stroke:#e94560
    style Models fill:#e94560,color:#fff,stroke:#fff
```

---

## 2. End-to-End Query Pipeline Flowchart

```mermaid
flowchart TD
    START(("🔍 User Query"))
    CONFIG["Config.from_file\ndefault.yaml"]
    INTENT["Intent Classification\nEXPLAIN | IMPLEMENT | REFACTOR\nDEBUG | SEARCH | UNKNOWN"]

    subgraph RETRIEVAL["Stage 1: Retrieval"]
        QE["Query Expansion\nmax_terms=6, synonyms"]
        PAR{"Parallel Search"}
        BM25["BM25 Search\nTantivy top_k=50"]
        VEC["Vector Search\nLanceDB top_k=50"]
        HYB["RRF Hybrid Merge\nk=10, bm25_w=0.5, vec_w=0.5"]
        PLANB{"Plan B\nEnabled?"}
        MMR_R["Diversity MMR\nλ=0.6"]
        GRAN["Granularity Boost\nIntent-specific tables"]
        GRAPH["Graph Stitch\nBFS depth=2, max=8"]
        KNEE["Adaptive Knee Gate"]
        PREC["Precision Recovery\nmax_additions=3"]
        COV["Coverage Recovery"]
    end

    subgraph RANKING["Stage 2: Ranking"]
        FEAT["Feature Enrichment\nname_match, struct_bonus"]
        GATE{"Reranker\nGating"}
        RERANK_S["Qwen3 Reranker\ntop_m=35 + BM25 rescue=15"]
        FUSE["Score Fusion\nw_base=1.0 + w_rerank=0.32\n+ w_struct=0.05"]
        DEDUP["Deduplication\nentropy_threshold=0.6"]
        SETOPT["Set Optimizer\n(optional)"]
    end

    subgraph CONTEXT["Stage 3: Context Assembly"]
        ASSEMBLE["Block Assembly"]
        SCORE_C["Block Scoring\n5-factor weighted"]
        COHERE["Coherence Refinement\nprotect top-3"]
        BUDGET{"Budget\nMode?"}
        SUBMOD["Submodular Packer\n4-component: rrf+novelty\n+graph+concept"]
        STD_BUD["Standard Budget\nTokenBudgetManager"]
        REFINE["Post-Allocation\nprecision filter | backfill\nclaim swap | evidence inject"]
        STITCH["Context Stitcher\n→ ContextArtifact"]
    end

    subgraph INTELLIGENCE["Stage 4: Intelligence"]
        DIAG["Diagnostics L1-L3"]
        ACT["Action Engines\n(propose only, no-op)"]
        CLAIM["Claim Coverage\ngate: PASS|WARN|BLOCK"]
        MECH["Mechanical Fixer\n(rule-based)"]
    end

    subgraph GENERATION["Stage 5: Generation"]
        TMPL["Template Loader\nexplain.yaml"]
        RENDER["Prompt Render\n+ reasoning enforcement"]
        LLM["Gemini 2.5 Flash\ntemp=0.0, max_out=2000"]
        HALLUC["Hallucination Detector\ncitation + identifier check"]
        PRESENT["PresentationRenderer\nnormalize + clean"]
    end

    ANSWER(("✅ Answer"))

    START --> CONFIG --> INTENT
    INTENT --> QE --> PAR
    PAR --> BM25 & VEC
    BM25 --> HYB
    VEC --> HYB
    HYB --> PLANB
    PLANB -->|yes| MMR_R --> GRAN --> GRAPH
    PLANB -->|no| KNEE
    GRAPH --> KNEE
    KNEE --> PREC --> COV

    COV --> FEAT --> GATE
    GATE -->|pass| RERANK_S --> FUSE
    GATE -->|skip| FUSE
    FUSE --> DEDUP --> SETOPT

    SETOPT --> ASSEMBLE --> SCORE_C --> COHERE --> BUDGET
    BUDGET -->|submodular| SUBMOD --> REFINE
    BUDGET -->|standard| STD_BUD --> REFINE
    REFINE --> STITCH

    STITCH --> DIAG --> ACT --> CLAIM --> MECH

    MECH --> TMPL --> RENDER --> LLM --> HALLUC --> PRESENT --> ANSWER

    style START fill:#e94560,color:#fff
    style ANSWER fill:#00b894,color:#fff
    style RETRIEVAL fill:#0f3460,color:#fff,stroke:#e94560
    style RANKING fill:#16213e,color:#fff,stroke:#e94560
    style CONTEXT fill:#1a1a2e,color:#fff,stroke:#e94560
    style INTELLIGENCE fill:#533483,color:#fff,stroke:#e94560
    style GENERATION fill:#2d3436,color:#fff,stroke:#e94560
```

---

## 3. Indexing Pipeline Flowchart

```mermaid
flowchart TD
    REPO(("📂 Repository"))

    subgraph SCAN["Phase 1: Discovery"]
        FS["File Scanner\nlanguages filter\nignore_patterns"]
        FI["FileInfo\nfile_id, path, language\ncontent_hash, line_count"]
    end

    subgraph PARSE["Phase 2: AST Parsing"]
        TS["TreeSitter Parser\nper-language grammar"]
        SYM["Symbol Extraction\nFUNCTION | CLASS | METHOD\nVARIABLE | CONSTANT | MODULE\nDECORATOR | IMPORT | ALIAS"]
        SI["SymbolInfo\nid, name, kind, file\nstart_line, end_line\nsignature, decorators"]
    end

    subgraph ENTITY["Phase 3: Entity-Centric (Plan A)"]
        EE["Entity Extractor\n→ EntityInfo"]
        RE["Relation Extractor\nCALLS | DEFINES | USES\nIMPORTS | RESOLVES_TO\nINHERITS | OVERRIDES"]
        CS["Confidence Scorer\npublic(0.3) + docstring(0.4)\n+ exported(0.2) + typed(0.1)"]
    end

    subgraph CHUNK["Phase 4: Hierarchical Chunking"]
        FINE["Fine: Symbol-level\nfunctions, methods"]
        MED["Medium: File sections\nlogical blocks"]
        COARSE["Coarse: File-level\ndocstrings + signatures"]
    end

    subgraph STORE["Phase 5: Storage"]
        EMB_C["QwenEmbedder.embed_code\nNO prefix, raw embedding\nmean pool → L2 norm → 1024d"]
        T_W["Tantivy Write\nBM25 index"]
        L_W["LanceDB Write\nvector index"]
        D_W["DuckDB Write\nmetadata + relations"]
        CG["Callgraph JSON\nFilesystemAdapter"]
    end

    REPO --> FS --> FI
    FI --> TS --> SYM --> SI
    SI --> EE --> RE --> CS
    CS --> FINE & MED & COARSE
    FINE & MED & COARSE --> EMB_C
    EMB_C --> T_W & L_W & D_W & CG

    style REPO fill:#e94560,color:#fff
    style SCAN fill:#0f3460,color:#fff
    style PARSE fill:#16213e,color:#fff
    style ENTITY fill:#1a1a2e,color:#fff
    style CHUNK fill:#533483,color:#fff
    style STORE fill:#2d3436,color:#fff
```

---

## 4. Retrieval Architecture Map

```mermaid
flowchart LR
    Q["Query + Intent"]

    subgraph PREP["Query Preparation"]
        QEX["Query Expansion\nsynonyms, camelCase split\nmax 6 terms"]
        QEMB["embed_query()\ninstruction prefix:\n'Represent this code\nsearch query for retrieval:'"]
    end

    subgraph SEARCH["Parallel Search"]
        BM25["BM25 Retriever\nTantivy\ntop_k=50"]
        VECTOR["Vector Retriever\nLanceDB cosine ANN\ntop_k=50"]
    end

    subgraph MERGE["Hybrid Merge"]
        RRF["RRF Fusion\nscore = Σ 1/(k+rank)\nk=10\nbm25_w=0.5, vec_w=0.5"]
    end

    subgraph PLANB["Plan B Extensions"]
        direction TB
        DIV["MMR Diversity\nλ=0.6, sim_thresh=0.85"]
        GB["Granularity Boost\nintent-specific tables"]
        GS["Graph Stitch\nBFS depth=2\nmax_additions=8\nbeam_high=8, beam_low=3"]
        HDEDUP["Hierarchical Dedup"]
        GMIX["Granularity Mixing\nfine/medium/coarse ratios"]
    end

    subgraph ADAPTIVE["Adaptive Recovery"]
        KNEE["Knee-Gate Detection\nscore drop-off analysis"]
        PR["Precision Recovery\nidentifier re-search\nmax=3, confidence≥0.8"]
        CR["Coverage Recovery\naspect backfill\nmax=3"]
        BAS["Budget-Aware Selection\nsingle-authority from\ncontext.max_tokens"]
    end

    Q --> QEX & QEMB
    QEX --> BM25
    QEMB --> VECTOR
    BM25 --> RRF
    VECTOR --> RRF
    RRF --> DIV --> GB --> GS --> HDEDUP --> GMIX
    GMIX --> KNEE --> PR --> CR --> BAS

    OUT(("Candidates\nto Ranking"))
    BAS --> OUT

    style Q fill:#e94560,color:#fff
    style OUT fill:#00b894,color:#fff
    style PREP fill:#0f3460,color:#fff
    style SEARCH fill:#16213e,color:#fff
    style MERGE fill:#1a1a2e,color:#fff
    style PLANB fill:#533483,color:#fff
    style ADAPTIVE fill:#2d3436,color:#fff
```

---

## 5. Ranking Pipeline Detail

```mermaid
flowchart TD
    IN(("Candidates\nfrom Retrieval"))

    subgraph ENRICH["Feature Enrichment"]
        NM["name_match_score\nidentifier overlap"]
        SB["struct_bonus\nentrypoint +0.1\ndecorator +0.05\ncallgraph +0.05\ncap 0.2"]
        BSB["broad_system_bias\n(optional, off by default)"]
    end

    subgraph RERANKER["Cross-Encoder Reranking"]
        GATING{"Reranker\nGating Check"}
        SELECT["Top-M Selection\ntop_m=35"]
        RESCUE["BM25 Rescue\ntop_k=15"]
        QWEN["QwenReranker.batch_score\nchat-structured input\nmax_length=8192\nGPU batch=8, CPU batch=4"]
        SIG["sigmoid(logit)\n→ [0, 1] score"]
    end

    subgraph FUSION["Score Fusion"]
        FORMULA["final = 1.0×base\n+ 0.32×rerank\n+ 0.05×struct\n+ 0.4×bm25\n+ 0.4×dense\n+ 0.2×name"]
        GEO["Geometry Metrics\nvariance analysis\nrerank contribution %"]
    end

    subgraph POST["Post-Ranking"]
        DD["Dedup\nfile entropy ≥ 0.6"]
        TP["Two-Pass (opt)\nseed_k=20, depth=3"]
        MMR_P["MMR Selection (opt)\nλ=0.7, top_n=30"]
        SO["Set Optimizer (opt)\ngreedy knapsack\nw_rel=1.0, w_struct=0.6\nw_cov=0.8, w_red=0.5"]
        FC["File Concentration\nunique files, entropy\nmax block ratio"]
    end

    IN --> NM & SB & BSB
    NM & SB & BSB --> GATING
    GATING -->|worthwhile| SELECT & RESCUE --> QWEN --> SIG
    GATING -->|skip| FORMULA
    SIG --> FORMULA --> GEO
    GEO --> DD --> TP --> MMR_P --> SO --> FC

    OUT(("Ranked\nCandidates"))
    FC --> OUT

    style IN fill:#e94560,color:#fff
    style OUT fill:#00b894,color:#fff
    style ENRICH fill:#0f3460,color:#fff
    style RERANKER fill:#16213e,color:#fff
    style FUSION fill:#533483,color:#fff
    style POST fill:#2d3436,color:#fff
```

---

## 6. Context Assembly Architecture

```mermaid
flowchart TD
    IN(("Ranked\nCandidates"))

    subgraph SCORING["Block Scoring"]
        BA["BlockAssembler\n→ ContextBlock"]
        BS["ContextBlockScorer\n0.4×semantic + 0.2×name\n+ 0.2×structural\n+ 0.1×novelty + 0.1×coherence"]
        CR["Coherence Refinement\nsame_file=0.8, diff_file=0.5\nproximity=50 lines\ncallgraph +0.1, protect top-3"]
    end

    subgraph PACKING["Budget Allocation"]
        direction TB
        CHECK{"submodular_packer\nenabled?"}
        SUB["Submodular Packer\nU = 0.40×rrf + 0.20×novelty\n+ 0.20×graph + 0.20×concept\ndensity = U / tokens\nepsilon stop = 0.001"]
        STD["Standard Budget\nTokenBudgetManager\nranking-surface-lock"]
    end

    subgraph GUARDS["Stop Guards (Submodular)"]
        EG["Epsilon Guard\nRRF ratio ≥ 0.85 → bypass"]
        NG["Noise Guard\nfile_ratio ≥ 0.60\n+ no concept/graph gain\n+ rrf_ratio < 0.85 → stop"]
        UG["Utility Mass Guards\nrrf ≥ 60%, novelty ≤ 20%\ngraph ≤ 10%"]
    end

    subgraph REFINE["Post-Allocation Refinements"]
        RG["Relevance Gate\nthreshold=0.25"]
        PF["Precision Filter\nidentifier overlap\nlow_score < 0.25"]
        SBF["Sparse Backfill\nutil < 45% or blocks < 18\nadd up to 10"]
        CGS["Claim-Gain Swap\nε=0.02, max 2 swaps"]
        UEI["Evidence Injection\nmax 2 blocks\nclaim_gain ≥ 0.1"]
        DBE["Dynamic Budget\nmax 2 expansions\n+400 tokens each"]
        FBG["Final Budget Guard\ntrim tail if over budget"]
    end

    subgraph OUTPUT["Output"]
        STITCH["ContextStitcher\nfile headers + line numbers\nprovenance metadata"]
        CA["ContextArtifact\ncontext_text, blocks\ntoken_budget, used_tokens\nprovenance, explain_trace"]
    end

    IN --> BA --> BS --> CR --> CHECK
    CHECK -->|yes| SUB --> EG & NG & UG
    CHECK -->|no| STD
    EG & NG & UG --> RG
    STD --> RG
    RG --> PF --> SBF --> CGS --> UEI --> DBE --> FBG
    FBG --> STITCH --> CA

    DONE(("To Intelligence\n& Generation"))
    CA --> DONE

    style IN fill:#e94560,color:#fff
    style DONE fill:#00b894,color:#fff
    style SCORING fill:#0f3460,color:#fff
    style PACKING fill:#16213e,color:#fff
    style GUARDS fill:#533483,color:#fff
    style REFINE fill:#1a1a2e,color:#fff
    style OUTPUT fill:#2d3436,color:#fff
```

---

## 7. Intelligence & Generation Sequence

```mermaid
sequenceDiagram
    participant CTX as ContextArtifact
    participant DC as DiagnosticController
    participant L1 as Level1 Engine<br/>(Structural)
    participant L2 as Level2 Engine<br/>(Semantic)
    participant L3 as Level3 Engine<br/>(Cognitive)
    participant IC as IntelligenceController
    participant CC as ClaimCoverage
    participant MF as MechanicalFixer
    participant TL as TemplateLoader
    participant GA as GenerationAdapter
    participant GP as GeminiProvider
    participant HD as HallucinationDetector
    participant PR as PresentationRenderer

    CTX->>DC: analyze(context)
    DC-->>IC: DiagnosticSnapshot

    IC->>L1: propose(snapshot, context)
    L1-->>IC: L1Plan (structural actions)

    IC->>L2: propose(snapshot, context)
    L2-->>IC: SemanticActionPlan

    IC->>L3: propose(snapshot, context)
    L3-->>IC: CognitiveActionPlan

    Note over IC: merge_plans() → UnifiedActions<br/>L1→L2→L3 order, by priority<br/>ACTIONS ARE LOGGED, NOT EXECUTED

    IC-->>CTX: ContextModificationPlan

    CTX->>CC: run_claim_coverage()
    CC-->>CTX: coverage_result
    CC->>CC: decide_gate_action()
    Note over CC: PASS | WARN | BLOCK | RECOVER

    CTX->>MF: apply(diagnostics)
    Note over MF: Rule-based fixes<br/>No LLM calls

    CTX->>TL: load("explain")
    TL-->>GA: YAML template + variables

    GA->>GA: render prompt<br/>{query} {context}<br/>{reasoning_enforcement}<br/>{claim_contract_rules}

    GA->>GP: invoke_sync(request)
    Note over GP: model=gemini-2.5-flash<br/>temp=0.0, max_out=2000<br/>retry: 4 attempts<br/>key rotation on quota

    GP-->>GA: ProviderResponse(text, tokens, finish_reason)

    GA->>HD: detect(text, context_artifact)
    Note over HD: Check citations vs context<br/>Check identifiers vs symbols<br/>Flag unverified claims

    HD-->>GA: hallucination_flags[]

    GA->>PR: render(text)
    Note over PR: Normalize markers<br/>Map file IDs → paths<br/>Clean status messages

    PR-->>PR: 📤 Final Answer
```

---

## 8. Storage Architecture Map

```mermaid
graph TB
    subgraph WRITE["Write Path (Indexing)"]
        IP["IndexerPipeline.index()"]
    end

    subgraph READ["Read Path (Querying)"]
        RP["RetrievalPipeline.retrieve()"]
    end

    subgraph BM25["Tantivy BM25 Index"]
        BW["bm25_adapter.write()\n• doc_id\n• content (full text)\n• file path\n• symbol metadata"]
        BR["BM25Retriever.search()\n• query string\n• top_k=50\n• TF-IDF scoring"]
    end

    subgraph VECTOR["LanceDB Vector Store"]
        VW["vector_adapter.write()\n• doc_id\n• embedding (1024d)\n• file path\n• granularity level"]
        VR["VectorRetriever.search()\n• query vector (1024d)\n• top_k=50\n• cosine ANN"]
    end

    subgraph META["DuckDB Metadata"]
        MW["metadata_adapter.write()\n• entities (EntityInfo)\n• relations (RelationInfo)\n• file metadata\n• symbol table"]
        MR["metadata_adapter.read()\n• entity lookup\n• relation traversal\n• file info"]
    end

    subgraph FS["Filesystem Artifacts"]
        FW["filesystem_adapter.write()\n• callgraph.json\n• index_manifest.json\n• statistics"]
        FR["filesystem_adapter.read()\n• callgraph loading\n• artifact access"]
    end

    IP --> BW & VW & MW & FW
    RP --> BR & VR & MR & FR

    style WRITE fill:#e94560,color:#fff
    style READ fill:#00b894,color:#fff
    style BM25 fill:#0f3460,color:#fff
    style VECTOR fill:#16213e,color:#fff
    style META fill:#533483,color:#fff
    style FS fill:#2d3436,color:#fff
```

---

## 9. Model Call Map

```mermaid
graph LR
    subgraph ONDEVICE["On-Device Models (torch)"]
        EMB["Qwen3-Embedding-0.6B\nAutoModel\nmean pool → L2 norm\n1024 dimensions"]
        RR["Qwen3-Reranker-0.6B\nAutoModelForSeqClassification\nchat-structured input\nsigmoid(logit) output"]
    end

    subgraph REMOTE["Remote API Models"]
        GEM["Gemini 2.5 Flash\ngoogle.genai SDK\ngenerate_content()\n1.04M context window"]
        JUDGE["Judge Model\n(configurable)\nOpenAI | Gemini | Cerebras\nstructured JSON output"]
    end

    subgraph CALLERS["Call Sites"]
        EC["embed_code()\nNO prefix, raw"]
        EQ["embed_query()\nWITH instruction prefix"]
        BS["batch_score()\ncross-encoder scoring"]
        GS["invoke_sync()\nanswer generation"]
        GST["invoke_stream()\nstreaming generation"]
        JC["call_judge()\nevaluation"]
    end

    EC -->|index time| EMB
    EQ -->|query time| EMB
    BS -->|rank time| RR
    GS -->|generate time| GEM
    GST -->|generate time| GEM
    JC -->|eval time| JUDGE

    subgraph SAFETY["Safety Mechanisms"]
        KR["KeyRotationManager\npool rotation\nquota exhaustion handling"]
        RETRY["Retry Logic\n4 attempts\nprovider-suggested delays"]
        FALLBACK["GPU → CPU Fallback\nboth embedder & reranker"]
        HEAD["Head Validation\nfail-fast if score.weight\nnot in checkpoint"]
    end

    GEM -.-> KR & RETRY
    EMB -.-> FALLBACK
    RR -.-> FALLBACK & HEAD

    style ONDEVICE fill:#e94560,color:#fff
    style REMOTE fill:#0f3460,color:#fff
    style CALLERS fill:#16213e,color:#fff
    style SAFETY fill:#533483,color:#fff
```

---

## 10. Scoring Pipeline Map

```mermaid
flowchart LR
    subgraph INDEX["Index-Time Scores"]
        S1["Entity Confidence\npublic(0.3) + doc(0.4)\n+ export(0.2) + type(0.1)"]
    end

    subgraph RETRIEVAL_S["Retrieval Scores"]
        S2["BM25 TF-IDF"]
        S3["Vector Cosine Sim"]
        S4["RRF Merge\nΣ 1/(k+rank)"]
        S5["MMR Diversity\nλ×sim - (1-λ)×max_sim"]
        S6["Granularity Boost\nintent-specific multiplier"]
    end

    subgraph RANKING_S["Ranking Scores"]
        S7["Feature Enrichment\nname_match + struct_bonus"]
        S8["Reranker Sigmoid\nsigmoid(cross-encoder logit)"]
        S9["Score Fusion\n1.0×base + 0.32×rerank\n+ 0.05×struct + 0.4×bm25\n+ 0.4×dense + 0.2×name"]
    end

    subgraph CONTEXT_S["Context Scores"]
        S10["Block Score\n0.4×sem + 0.2×name\n+ 0.2×struct + 0.1×nov\n+ 0.1×coh"]
        S11["Coherence Bonus\nsame_file(0.8)\ndiff_file(0.5)"]
        S12["Submodular Utility\n0.4×rrf + 0.2×novelty\n+ 0.2×graph + 0.2×concept"]
        S13["Submodular Density\nutility / token_count"]
        S14["Claim Gain\n(2×file_hits + 0.5×content)\n/ hint_terms"]
    end

    subgraph EVAL_S["Evaluation Scores"]
        S15["Judge Metrics\n8 dimensions × paired 1-5\n→ normalized 0-10"]
    end

    S1 --> S2 & S3
    S2 & S3 --> S4
    S4 --> S5 --> S6
    S6 --> S7
    S7 --> S8 --> S9
    S9 --> S10 --> S11 --> S12 --> S13
    S13 --> S14
    S14 --> S15

    style INDEX fill:#e94560,color:#fff
    style RETRIEVAL_S fill:#0f3460,color:#fff
    style RANKING_S fill:#16213e,color:#fff
    style CONTEXT_S fill:#533483,color:#fff
    style EVAL_S fill:#2d3436,color:#fff
```

---

## 11. Configuration Dependency Map

```mermaid
graph TD
    ROOT["Config\n(Pydantic BaseModel)\nfrom_file → default.yaml"]

    ROOT --> IC2["get_indexer_config()\n→ IndexerConfig"]
    ROOT --> RC["get_retrieval_config()\n→ RetrievalConfig"]
    ROOT --> RKC["get_ranking_config()\n→ RankConfig"]
    ROOT --> CC2["get_context_config()\n→ ContextConfig"]
    ROOT --> GC["get_generation_config()\n→ GenerationConfig"]
    ROOT --> INC["get_intelligence_config()\n→ IntelligenceConfig"]

    IC2 --> SC["StorageConfig\nduckdb, tantivy\nlancedb, artifacts"]
    IC2 --> ECC["EntityConfidenceConfig\nbonus weights, cap"]
    IC2 --> HCC["HierarchicalChunkingConfig\nfine/medium/coarse\nchunk_max_lines"]

    RC --> BA2["Budget Authority\nSINGLE SOURCE\ncontext.max_tokens\n+ generation_reserve"]

    CC2 --> PC["PackerConfig\nw_rrf, w_novelty\nw_graph, w_concept\nepsilon, guards"]

    CC2 -.->|budget flows to| RC

    Note1["⚠️ Dual budget authority\nvalidation in\nget_retrieval_config()"]
    RC -.-> Note1

    style ROOT fill:#e94560,color:#fff
    style IC2 fill:#0f3460,color:#fff
    style RC fill:#16213e,color:#fff
    style RKC fill:#533483,color:#fff
    style CC2 fill:#1a1a2e,color:#fff
    style GC fill:#2d3436,color:#fff
    style INC fill:#2d3436,color:#fff
```

---

## 12. Embedding Asymmetry Diagram

```mermaid
flowchart LR
    subgraph INDEX_TIME["Index Time"]
        CODE["Source Code Chunk"]
        EC2["embed_code(code)\nNO instruction prefix\nraw text → tokenize\n→ model → mean pool\n→ L2 normalize\n→ 1024d vector"]
        STORE2["Store in LanceDB"]
    end

    subgraph QUERY_TIME["Query Time"]
        QUERY["User Query"]
        EQ2["embed_query(query)\nWITH prefix:\n'Represent this code\nsearch query\nfor retrieval:'\n→ tokenize → model\n→ mean pool → L2 norm\n→ 1024d vector"]
        SEARCH2["Cosine ANN Search\nin LanceDB"]
    end

    CODE --> EC2 --> STORE2
    QUERY --> EQ2 --> SEARCH2
    STORE2 -.->|cosine similarity| SEARCH2

    subgraph CONTRACT["Embedding Contract"]
        C1["✅ Code: always raw"]
        C2["✅ Query: always prefixed"]
        C3["❌ Double prefix → ValueError"]
        C4["❌ Model mismatch → ValueError"]
    end

    style INDEX_TIME fill:#0f3460,color:#fff
    style QUERY_TIME fill:#16213e,color:#fff
    style CONTRACT fill:#e94560,color:#fff
```

---

## 13. Telemetry Flow Map

```mermaid
flowchart TD
    subgraph SOURCES["Telemetry Sources"]
        RT["RetrievalPipeline\ncandidate counts, search times\ngraph stitch stats, coverage"]
        RKT["RankingPipeline\nfeature vectors, reranker diag\ngeometry metrics, elimination"]
        CTT["ContextPipeline\nsubmodular trace, budget usage\ncoherence stats, refinement log"]
        INT["IntelligenceController\ndiagnostic snapshot\naction plans, audit"]
        GT["GenerationAdapter\ntokens in/out, latency\nfinish reason, provider"]
        HT["HallucinationDetector\ncitation flags\nidentifier flags"]
    end

    subgraph COLLECTOR["QueryTelemetry"]
        QT["QueryTelemetry\nphase durations\nmetadata dict\nJSON export"]
    end

    subgraph SINKS["Output Sinks"]
        JSON["diagnostics/*.json\nper-query telemetry"]
        LOG["Logger\nstructured log lines"]
        STDOUT["Console\nPresentationRenderer"]
    end

    RT & RKT & CTT & INT & GT & HT --> QT
    QT --> JSON & LOG & STDOUT

    style SOURCES fill:#0f3460,color:#fff
    style COLLECTOR fill:#e94560,color:#fff
    style SINKS fill:#00b894,color:#fff
```

---

## 14. Agentic Insertion Points Map

```mermaid
graph TD
    subgraph PIPELINE["Current Single-Pass Pipeline"]
        R["Retrieval"]
        RK["Ranking"]
        C["Context"]
        I["Intelligence"]
        G["Generation"]
        R --> RK --> C --> I --> G
    end

    subgraph AGENTS["Potential Agentic Loops"]
        A1["🔄 Multi-Turn Refinement\nafter Generation\nuse telemetry + hallucination\nflags to re-query"]
        A2["🔄 Adaptive Retrieval\nafter Retrieval\nuse coverage gaps\nto reformulate query"]
        A3["🔄 Claim Recovery\nafter Intelligence\nuse RECOVER gate action\nto re-retrieve evidence"]
        A4["🔄 Template Selection\nbefore Generation\nintent-adaptive routing\nacross template variants"]
        A5["🔄 Eval Self-Improvement\nafter run_judge.py\nuse 8-dim scores\nfor regression detection"]
    end

    G -.->|telemetry| A1
    A1 -.->|refined query| R

    R -.->|coverage result| A2
    A2 -.->|expanded query| R

    I -.->|gate=RECOVER| A3
    A3 -.->|targeted search| R

    C -.->|intent + context| A4
    A4 -.->|template choice| G

    G -.->|answer| A5
    A5 -.->|config adjustment| R

    style PIPELINE fill:#0f3460,color:#fff
    style AGENTS fill:#e94560,color:#fff
```
