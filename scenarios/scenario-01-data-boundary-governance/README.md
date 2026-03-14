# Scenario 01
# Data Boundary Governance

---

## What We Built

An AI research assistant with two governance layers that prevent
access to sensitive internal data. The assistant can answer questions
from approved knowledge sources but returns nothing for sensitive queries.

---

## The Problem We Solved

Without governance controls, an AI assistant connected to a knowledge
repository could retrieve any document — including sensitive internal
data like pricing strategies and product roadmaps. This scenario
implements two independent control layers to enforce data boundaries.

---

## Architecture

```
User Query
    └── Lambda Function (AI Assistant)
            ├── TRACK B: Direct S3 Access
            │       ├── IAM tag condition check
            │       ├── ALLOW → public-research/* documents
            │       └── DENY  → sensitive-internal/* documents
            │
            └── TRACK A: Bedrock Knowledge Base
                    ├── Scoped ingestion (public-research/ only)
                    ├── Vector search via Amazon Nova Lite
                    ├── RESPONDS → approved knowledge queries
                    └── NO DATA  → sensitive data queries

All requests logged → CloudTrail + CloudWatch
```

---

## AWS Services Used

| Service | Purpose | What We Learned |
|---|---|---|
| Amazon S3 | Knowledge repository with object tagging | Tags travel with data, enabling classification-based controls |
| AWS IAM | Identity and access policies | Tag conditions enforce boundaries at the identity layer |
| AWS Lambda | AI assistant functions | Two functions — one per governance track |
| Amazon Bedrock | Knowledge Base and AI model | Governance must be applied at ingestion not retrieval |
| Amazon S3 Vectors | Vector store for Knowledge Base | Cost-effective alternative to OpenSearch Serverless |
| AWS CloudTrail | API-level audit logging | All allow and deny events are captured |
| Amazon CloudWatch | Execution logs | Lambda results surfaced for monitoring |

---

## Track B — Tag-Based IAM Governance

### What it does
Controls direct S3 access using object tags and IAM condition keys.
The Lambda execution role can only retrieve objects tagged
data-classification: public-research. Objects tagged sensitive
are explicitly denied regardless of location.

### How it works
```
S3 Object Tags:
├── public-research/ai_governance_notes.txt  → data-classification: public-research
├── public-research/market_trends.txt        → data-classification: public-research
├── sensitive-internal/pricing_strategy.txt  → data-classification: sensitive
└── sensitive-internal/product_roadmap.txt   → data-classification: sensitive

IAM Policy Evaluation at request time:
├── Tag = public-research → ALLOW s3:GetObject
└── Tag = sensitive       → DENY  s3:GetObject
```

### Why this matters
Boundary enforcement is based on what the data IS, not where it lives.
A sensitive document remains protected even if moved to a different
folder or bucket because the tag travels with the object.

### Validation Results
| Document | Tag | Result |
|---|---|---|
| ai_governance_notes.txt | public-research | ALLOWED |
| market_trends.txt | public-research | ALLOWED |
| pricing_strategy.txt | sensitive | DENIED (AccessDenied) |
| product_roadmap.txt | sensitive | DENIED (AccessDenied) |

---

## Track A — Bedrock Knowledge Base Governance

### What it does
Connects a real AI model (Amazon Nova Lite) to a scoped knowledge
repository. Sensitive documents are excluded at ingestion — they
never enter the vector store and therefore can never be retrieved.

### How it works
```
Data Source scoped to:
s3://driftlock-ai-knowledge-lab-east1/public-research/
        ↓
Only public-research/ documents are ingested
        ↓
Titan Text Embeddings V2 converts docs to vectors
        ↓
Vectors stored in Amazon S3 Vectors
        ↓
Nova Lite queries vector store for relevant content
        ↓
Sensitive documents were never ingested
        ↓
Sensitive queries return no results
```

### Critical governance lesson
IAM tag conditions do NOT protect Bedrock Knowledge Base retrieval.
Bedrock queries the vector store directly, bypassing IAM policies.
Governance must be enforced at ingestion by scoping the data source URI.

```
Wrong assumption:
IAM deny policy → blocks Bedrock from retrieving sensitive docs
                                    ↑
                            This is NOT true

Correct approach:
Scoped S3 URI → sensitive docs never enter vector store
             → cannot be retrieved because they don't exist
```

### Validation Results
| Query | Expected | Result |
|---|---|---|
| What are the latest AI governance trends? | RESPONDED | Content from ai_governance_notes.txt |
| What are the current market trends? | RESPONDED | Content from market_trends.txt |
| What is our product roadmap? | NO DATA | Search returned nothing |
| What is our pricing strategy? | NO DATA | Insufficient information |

---

## Defense in Depth

Two independent control layers each enforcing the same boundary:

```
Layer 1 — Ingestion Boundary (Track A)
        Sensitive documents excluded from vector store at sync time
        └── Prevention at the source

Layer 2 — Identity Boundary (Track B)
        IAM tag conditions block direct S3 access
        └── Prevention at the identity layer

Layer 3 — Audit Visibility (both tracks)
        CloudTrail and CloudWatch capture all events
        └── Detection and evidence
```

If one layer fails the other still provides protection.
This is defense in depth — a core security architecture principle.

---

## Key Lessons Learned

### Governance must be applied at ingestion
An AI model connected to a knowledge base will retrieve anything
in the vector store. IAM policies apply to S3 API calls, not
to vector store queries. Scope your data source URI to approved
content before the first sync.

### Tags are stronger than folder structure
Folder-based separation breaks when files are moved. Tag-based
conditions are portable — the governance control travels with
the data regardless of storage location.

### Least privilege is a process not a setting
Start with minimum permissions, add only what errors require,
document every addition. The final IAM policy tells an honest
story of exactly what each service needs to function.

### Setup permissions differ from operational permissions
Provisioning managed services often requires broader permissions
than day-to-day operation. Grant what setup requires, then scope
down to operational minimum once resources are stable.

### Region alignment is mandatory
All resources in a Bedrock architecture must be in the same AWS
region. S3 buckets and Knowledge Bases in different regions cannot
communicate and produce cryptic authorization errors.

### Never operate as root
AWS intentionally blocks sensitive operations for root users.
Create a named IAM user for all development work and reserve
root access for account-level settings only.

---

## Known Limitations

### Single enforcement layer for Bedrock
The Bedrock boundary relies entirely on scoped ingestion. A
misconfigured data source URI would allow sensitive documents
to enter the vector store. A production implementation would
add a second control — an S3 bucket policy denying Bedrock's
service role access to sensitive-internal/ as a backup layer.

### No query-level filtering
The Knowledge Base returns whatever the vector search finds.
There is no runtime filter that could catch a sensitive document
if it somehow entered the vector store. Scenario 02 addresses
this with Amazon Bedrock Guardrails for query-level controls.

### Lambda timeout sensitivity
Bedrock RetrieveAndGenerate calls can take 10-30 seconds.
The default Lambda timeout of 3 seconds must be increased
to 60 seconds for multi-query functions.

---

## Files in This Scenario

```
scenario-01-basic-data-boundary/
├── README.md                          ← architecture and validation
├── iam-permissions.md                 ← this file's companion
├── lambda/
│   ├── driftlock-ai-assistant.py      ← Track B: direct S3 validation
│   └── driftlock-bedrock-assistant.py ← Track A: Bedrock KB queries
└── policies/
    ├── S3DataBoundaryPolicy.json       ← tag-based IAM policy
    └── driftlock-bedrock-kb-policy.json← Bedrock query permissions
```

---
