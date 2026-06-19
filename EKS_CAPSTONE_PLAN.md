# MediLink Hub → EKS Capstone: Full Implementation Plan

---

## Quick Answers to Your Questions

| Question | Answer | Why |
|----------|--------|-----|
| **Are we doing ECR?** | ✅ **Yes** | It's the native container registry for EKS. GitHub Actions pushes images → ECR → EKS pulls from ECR. Adds another AWS service. No reason to use DockerHub when you're all-in on AWS. |
| **Are we doing ArgoCD?** | ✅ **Yes** | It separates CI (GitHub Actions builds+scans) from CD (ArgoCD deploys). The ArgoCD UI showing your app tree syncing is one of the most impressive demo visuals you can show an evaluator. It's also industry standard. |
| **How do we prevent hallucinations?** | 8-layer strategy detailed in [Phase 6](#phase-6-anti-hallucination--confidence-scoring--guardrails-day-6) | The key insight: RAG inherently reduces hallucinations by grounding the LLM in your actual documents. But we go further with confidence scoring, citation enforcement, retrieval thresholds, constrained prompting, "I don't know" responses, AND Bedrock Guardrails for platform-level safety. |
| **Is it splitting into microservices?** | **No — you already have them.** | MediLink Hub already has 4 microservices. We're adding 1 new one (`rag-service`). Total = 5 services + frontend. That's the perfect number for an EKS demo — enough to show real distributed system patterns, not so many that it becomes unmanageable. |
| **Step by step?** | 11 phases below (Phase 0-10) | Each phase has exact files, commands, and what to demo. |

---

## Architecture: Before vs After

### What changes:

| Layer | Before (Current) | After (Capstone) |
|-------|-------------------|-------------------|
| **Compute** | EC2 ASG + Launch Templates + user-data scripts | EKS managed node groups |
| **Container Registry** | None (git clone on boot) | Amazon ECR |
| **Orchestration** | Bash scripts on EC2 | Kubernetes (Helm + KGateway) |
| **API Gateway** | Internal ALB with path rules | KGateway (Envoy Gateway) with JWT + rate limiting |
| **AI** | Bolted-on `/chat` endpoint calling HuggingFace | System-integrated RAG pipeline (Textract OCR → pgvector → Bedrock + Guardrails) |
| **AI Safety** | None | Bedrock Guardrails (content filters, PII redaction, denied topics) |
| **Async Processing** | SQS → Lambda (notifications only) | SQS → Lambda (notifications) + S3 → SQS → rag-service (document processing) |
| **CI/CD** | None | GitHub Actions CI → ArgoCD CD (GitOps) |
| **Security** | AWS-level only (WAF, KMS, SGs) | AWS-level + K8s-level (NetworkPolicies, IRSA, Pod Security Standards) |
| **Scaling** | ASG CPU tracking (never demoed) | HPA with live load test demo |
| **Resilience** | Circuit breaker in code (not highlighted) | Documented failure scenarios + retries + liveness/readiness probes |
| **Document Access** | Per-appointment only, broken access control | Doctor-patient relationship derived from appointments, proper authorization |
| **Document Organization** | No categorization | Category-based filtering (lab reports, prescriptions, imaging, etc.) |

### What stays the same:

| Component | Status |
|-----------|--------|
| VPC (8 subnets, 2 AZs, NAT Gateways) | ✅ Keep (modify subnet tags for EKS) |
| RDS PostgreSQL | ✅ Keep (add pgvector extension) |
| S3 (document storage, KMS encrypted) | ✅ Keep |
| KMS (CMK for encryption) | ✅ Keep |
| Secrets Manager (DB creds, JWT, API keys) | ✅ Keep |
| SQS + DLQ (appointment notifications) | ✅ Keep + add RAG processing queue |
| Lambda (notification worker) | ✅ Keep |
| SNS, SES | ✅ Keep |
| CloudWatch (logs, alarms) | ✅ Keep (add EKS-specific) |
| CloudTrail | ✅ Keep |
| WAF v2 | ✅ Keep (attach to new ALB) |
| VPC Endpoints (PrivateLink) | ✅ Keep |
| CloudFront | ✅ Keep |

### Final AWS Services Count: 23+

```
EKS, ECR, VPC, ALB, WAF v2, RDS PostgreSQL, S3, KMS, Secrets Manager,
SQS, SNS, Lambda, SES, CloudWatch, CloudTrail, CloudFront, VPC Endpoints,
NAT Gateway, IAM (IRSA), Textract, Bedrock, Bedrock Guardrails, Route 53 (optional)
```

---

## Final Architecture Diagram

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                          DEVELOPER WORKFLOW                                 │
│                                                                             │
│   git push → GitHub Actions:                                                │
│   ┌──────┐  ┌──────┐  ┌───────┐  ┌───────┐  ┌──────┐  ┌────────────────┐  │
│   │Lint  │→ │SAST  │→ │Docker │→ │Trivy  │→ │Push  │→ │Update GitOps   │  │
│   │+Test │  │Sonar │  │Build  │  │Scan   │  │to ECR│  │repo (image tag)│  │
│   └──────┘  └──────┘  └───────┘  └───────┘  └──────┘  └───────┬────────┘  │
│                                                                 │           │
│                                                          ┌──────▼────────┐  │
│                                                          │ ArgoCD syncs  │  │
│                                                          │ to EKS cluster│  │
│                                                          └───────────────┘  │
└─────────────────────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────────────────────┐
│                           AWS VPC (10.0.0.0/16)                             │
│                                                                             │
│  ┌── Public Subnets ────────────────────────────────────────────────────┐   │
│  │  WAF v2 → ALB (AWS LB Controller) → CloudFront                     │   │
│  └──────────────────────────────┬───────────────────────────────────────┘   │
│                                 │                                           │
│  ┌── Private Subnets (EKS) ─────▼──────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  ┌──────────────────────────────────────────────────────────────┐    │   │
│  │  │              KGateway (Envoy Gateway)                        │    │   │
│  │  │    JWT validation · Path routing · Rate limiting             │    │   │
│  │  └───┬──────┬──────┬──────┬──────┬──────────────────────────────┘    │   │
│  │      │      │      │      │      │                                   │   │
│  │  ┌───▼──┐┌──▼───┐┌─▼──┐┌─▼──┐┌──▼───┐  ┌────────┐ ┌────────────┐  │   │
│  │  │User  ││Appt  ││Hlth││Doc ││RAG   │  │Redis   │ │ArgoCD      │  │   │
│  │  │Svc   ││Svc   ││Svc ││Svc ││Svc   │  │(Cache) │ │(GitOps)    │  │   │
│  │  │:8001 ││:8002 ││:8003│:8004│:8005 │  │:6379   │ │            │  │   │
│  │  └──┬───┘└──┬───┘└─┬──┘└─┬──┘└──┬───┘  └────────┘ └────────────┘  │   │
│  │     │       │      │     │      │                                   │   │
│  │     │       │      │     │      ├──── Textract (OCR)               │   │
│  │     │       │      │     │      ├──── Bedrock (LLM + Embeddings)   │   │
│  │     │       │      │     │      ├──── Bedrock Guardrails (Safety)  │   │
│  │     │       │      │     │      └──── pgvector (embeddings)        │   │
│  │     │       │      │     │                                         │   │
│  │     └───────┴──────┴─────┼──→ RDS PostgreSQL (+ pgvector)         │   │
│  │                          └──→ S3 (document storage)                │   │
│  │                                                                     │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌── Event-Driven Pipelines ───────────────────────────────────────────┐   │
│  │                                                                      │   │
│  │  Pipeline 1 (EXISTS): Appointment Events                            │   │
│  │  appointment-service → SQS → Lambda → SES (email notification)      │   │
│  │                          └→ DLQ (failed after 3 retries)            │   │
│  │                                                                      │   │
│  │  Pipeline 2 (NEW): Document AI Processing                           │   │
│  │  document-service → SQS (rag-queue) → rag-service (SQS consumer)   │   │
│  │     → Textract OCR → chunk → Bedrock embed → pgvector store         │   │
│  │     → writes extracted metadata back to health-service              │   │
│  │     → DLQ (failed after 3 retries)                                  │   │
│  │                                                                      │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌── Observability ────────────────────────────────────────────────────┐   │
│  │  CloudWatch Logs (all services) · CloudWatch Alarms (5xx, DLQ)     │   │
│  │  CloudTrail (API audit) · SNS Ops Alerts                           │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
│                                                                             │
│  ┌── Security ─────────────────────────────────────────────────────────┐   │
│  │  KMS (encryption at rest) · Secrets Manager (credentials)          │   │
│  │  VPC Endpoints / PrivateLink · IRSA (pod-level IAM)                │   │
│  │  NetworkPolicies · Pod Security Standards · WAF v2                 │   │
│  │  Bedrock Guardrails (content safety, PII redaction)                │   │
│  └─────────────────────────────────────────────────────────────────────┘   │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Phase-by-Phase Execution Plan

---

### Phase 0: Pre-Migration Fixes (Day 0)

> **⚠️ NEW PHASE** — Fix critical gaps in the current codebase before containerizing. These changes carry over cleanly into the EKS deployment and make the app realistic and secure.

**Goal**: Fix document access control security hole, enable doctors to see full patient document history, and add document categorization.

#### 0.1: Fix Document Download Access Control (Security Hole)

**[MODIFY] `document-service/main.py`** — Fix `GET /documents/{doc_id}` (lines 344-346)

The current code has a `pass` placeholder that allows **any doctor** to download **any patient's** documents:

```python
# BEFORE (BROKEN):
if user["role"] == "doctor":
    # Check doctor-patient relationship in a real app via API
    pass  # <-- ANY doctor can download ANY patient's documents!
```

**Fix**: Verify the doctor has a relationship with the patient by checking if any appointment exists between them:

```python
# AFTER (FIXED):
if user["role"] == "doctor":
    # Verify doctor-patient relationship via appointment history
    import httpx
    INTERNAL_ALB_DNS = os.getenv("INTERNAL_ALB_DNS", "http://internal-alb")
    if not INTERNAL_ALB_DNS.startswith("http"):
        INTERNAL_ALB_DNS = "http://" + INTERNAL_ALB_DNS

    try:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{INTERNAL_ALB_DNS}/appointments/check-relationship",
                params={"doctor_id": user["user_id"], "patient_id": str(doc.patient_id)},
                headers={"Authorization": f"Bearer {user['token']}"},
                timeout=10.0
            )
            if resp.status_code != 200 or not resp.json().get("has_relationship"):
                raise HTTPException(status_code=403, detail="Access denied — no doctor-patient relationship")
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Failed to verify doctor-patient relationship: {e}")
        raise HTTPException(status_code=503, detail="Unable to verify access permissions")
```

#### 0.2: Add Doctor-Patient Relationship Endpoint

**[MODIFY] `appointment-service/main.py`** — Add new endpoint:

```python
@app.get("/appointments/check-relationship")
async def check_doctor_patient_relationship(
    doctor_id: str,
    patient_id: str,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Check if a doctor has ever had an appointment with a patient.
    Used by document-service and health-service to verify access permissions."""

    # Only the requesting doctor, the patient, or system can check
    if user["role"] not in ["doctor", "admin", "system"]:
        raise HTTPException(status_code=403, detail="Access denied")

    result = await db.execute(
        select(Appointment).where(
            Appointment.doctor_id == doctor_id,
            Appointment.patient_id == patient_id,
            Appointment.is_deleted == False
        ).limit(1)
    )
    relationship_exists = result.scalar_one_or_none() is not None

    return {"has_relationship": relationship_exists}
```

#### 0.3: Enable Doctor Access to Full Patient Document History

**[MODIFY] `document-service/main.py`** — Update `GET /documents` for doctors:

Currently, doctors can only see documents tied to a specific appointment. Fix this so doctors can see **all documents** for any patient they have a relationship with:

```python
# BEFORE: Doctor must provide appointment_id, returns [] otherwise
elif user["role"] == "doctor":
    if not appointment_id:
        return []

# AFTER: Doctor can view all docs for a patient they have a relationship with
elif user["role"] == "doctor":
    # If appointment_id provided, filter by that (existing behavior)
    if appointment_id:
        # ... existing appointment validation logic ...
        query = query.where(Document.record_id == UUID(appointment_id))
    elif patient_id:
        # New: doctor wants to see all docs for a patient
        # Verify doctor-patient relationship
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{INTERNAL_ALB_DNS}/appointments/check-relationship",
                params={"doctor_id": user["user_id"], "patient_id": patient_id},
                headers={"Authorization": f"Bearer {user['token']}"},
                timeout=10.0
            )
            if resp.status_code != 200 or not resp.json().get("has_relationship"):
                raise HTTPException(status_code=403, detail="No relationship with this patient")
        query = query.where(Document.patient_id == UUID(patient_id))
    else:
        # No filters — return docs the doctor uploaded
        query = query.where(Document.created_by_user_id == UUID(user["user_id"]))
```

Add `patient_id` as a query parameter to the endpoint:
```python
@app.get("/documents")
async def list_documents(
    appointment_id: str | None = None,
    patient_id: str | None = None,      # ← NEW parameter
    limit: int = 10,
    offset: int = 0,
    user=Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
```

#### 0.4: Add Document Categorization

**[MODIFY] `document-service/main.py`** — Add `category` column to Document model:

```python
class Document(Base):
    __tablename__ = "documents"
    id = Column(PG_UUID(as_uuid=True), primary_key=True, default=uuid4)
    patient_id = Column(PG_UUID(as_uuid=True), nullable=False, index=True)
    record_id = Column(PG_UUID(as_uuid=True), nullable=True, index=True)
    file_name = Column(Text, nullable=False)
    s3_key = Column(Text, nullable=False)
    uploaded_by = Column(Text, nullable=False)
    file_type = Column(Text, nullable=False)
    category = Column(Text, nullable=False, default="other")  # ← NEW
    status = Column(Text, default="PENDING")
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    created_by_user_id = Column(PG_UUID(as_uuid=True), nullable=False)
    created_by_role = Column(Text, nullable=False)
    is_deleted = Column(Boolean, default=False, index=True)
```

Valid categories:
```python
VALID_CATEGORIES = [
    "lab_report",       # Blood tests, urinalysis, etc.
    "prescription",     # Medication prescriptions
    "imaging",          # X-rays, MRI, CT scans
    "discharge_summary",# Hospital discharge papers
    "insurance",        # Insurance cards, claims
    "referral",         # Specialist referral letters
    "consultation",     # Doctor consultation notes
    "other"             # Default catch-all
]
```

**[MODIFY] `document-service/main.py`** — Update `PresignedUrlRequest` schema:

```python
class PresignedUrlRequest(BaseModel):
    file_name: str
    file_type: str
    category: str = "other"            # ← NEW
    appointment_id: str | None = None

    @field_validator("category")
    @classmethod
    def validate_category(cls, v):
        if v not in VALID_CATEGORIES:
            raise ValueError(f"Invalid category. Must be one of: {', '.join(VALID_CATEGORIES)}")
        return v
```

**[MODIFY] `frontend/src/pages/Documents.jsx`** — Add category dropdown to upload form:

```jsx
// Add category selector above the drop zone
<div className="form-group" style={{ marginBottom: '16px' }}>
  <label>Document Category</label>
  <select value={category} onChange={(e) => setCategory(e.target.value)} className="form-input">
    <option value="lab_report">🧪 Lab Report</option>
    <option value="prescription">💊 Prescription</option>
    <option value="imaging">📷 Imaging (X-Ray, MRI)</option>
    <option value="discharge_summary">🏥 Discharge Summary</option>
    <option value="insurance">📋 Insurance</option>
    <option value="referral">📨 Referral</option>
    <option value="consultation">📝 Consultation Notes</option>
    <option value="other">📄 Other</option>
  </select>
</div>
```

And show a category badge on each document card:
```jsx
<span className="doc-category-badge">{getCategoryLabel(doc.category)}</span>
```

#### 0.5: Add Alembic Migration for Category Column

```bash
cd document-service
alembic revision --autogenerate -m "add_category_column"
alembic upgrade head
```

#### 0.6: Refactor User-Service to RS256 for KGateway Auth

**[MODIFY] `user-service/auth.py`**
To allow Envoy (KGateway) to validate our JWTs natively, we must switch from symmetric HS256 (shared secret) to asymmetric RS256 (public/private keypair).

1. Generate an RSA keypair and store it in AWS Secrets Manager.
2. Update `user-service` to sign JWTs using the private key.
3. Expose a new public endpoint: `GET /.well-known/jwks.json` which serves the public key in JWKS format.
4. KGateway's `SecurityPolicy` will hit this `/jwks.json` endpoint to learn how to validate the tokens.

#### Verification:
```bash
# Test 1: Doctor without relationship → 403
curl -H "Authorization: Bearer $DOCTOR_TOKEN" /documents/some-doc-id  # → 403

# Test 2: Doctor with relationship → 200
curl -H "Authorization: Bearer $DOCTOR_TOKEN" "/documents?patient_id=$PATIENT_ID"  # → documents[]

# Test 3: Upload with category
curl -X POST /documents/presigned-url -d '{"file_name":"blood.pdf","file_type":"application/pdf","category":"lab_report"}'

# Test 4: Category shown in document list
curl /documents  # → each doc has "category" field

# Test 5: JWKS endpoint serves public key
curl http://user-service:8001/.well-known/jwks.json  # → {"keys": [{"kty":"RSA",...}]}

# Test 6: RS256 token works with all services
export RS256_TOKEN=$(curl -X POST /login -d '{"email":"doc@test.com","password":"pass"}' | jq -r .access_token)
curl -H "Authorization: Bearer $RS256_TOKEN" /appointments  # → 200
```

---

### Phase 1: EKS Cluster + ECR via Terraform (Day 1-2)

**Goal**: Replace EC2 ASG deployment with EKS. Get the cluster running and images in ECR.

#### Step 1.0: Configure Terraform Remote State
**[MODIFY] `terraform/providers.tf`**
- Configure an S3 backend (`backend "s3"`) with a DynamoDB lock table for remote state storage.
- *Why*: Running `terraform apply` in CI/CD without remote state locking will corrupt your state if two actions run simultaneously.

#### Step 1.1: Add ECR repositories

**[NEW] `terraform/ecr.tf`**

Create one ECR repo per microservice:
```
medilink/user-service
medilink/appointment-service
medilink/health-service
medilink/document-service
medilink/rag-service
medilink/rag-worker
medilink/frontend
```

Each repo gets:
- Image scanning on push (vulnerability detection)
- Lifecycle policy: keep last 10 tagged images, expire untagged after 1 day
- Encryption with your existing KMS key

#### Step 1.2: Add EKS cluster

**[NEW] `terraform/eks.tf`**

Using the `terraform-aws-modules/eks/aws` module:
- EKS cluster in your existing private subnets (`private_back_a`, `private_back_b`)
- Managed node group: 2x `t3.medium` (min 2, max 4, desired 2)
- OIDC provider enabled (required for IRSA)
- Add-ons: CoreDNS, kube-proxy, VPC CNI, EBS CSI driver
- Cluster endpoint: private access + public access (for kubectl from your machine)
- Cluster logging: api, audit, authenticator → CloudWatch

#### Step 1.3: Add IRSA (IAM Roles for Service Accounts)

**[NEW] `terraform/irsa.tf`**

Create Kubernetes ServiceAccount-linked IAM roles so pods get **least-privilege** AWS access without hardcoded credentials:

| Service Account | IAM Permissions |
|----------------|----------------|
| `sa-user-service` | Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents) |
| `sa-health-service` | Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents) |
| `sa-appointment-service` | SQS (SendMessage), Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents), KMS |
| `sa-document-service` | S3 (PutObject, GetObject), KMS (Decrypt, GenerateDataKey), Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents) |
| `sa-rag-service` | Bedrock (InvokeModel, InvokeModelWithGuardrail), KMS, Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents) |
| `sa-rag-worker` | S3 (GetObject), Textract (StartDocumentAnalysis, GetDocumentAnalysis), Bedrock (InvokeModel), SQS (ReceiveMessage, DeleteMessage), KMS, Secrets Manager (GetSecretValue), CloudWatch Logs (PutLogEvents) |
| `sa-keda` | SQS (GetQueueAttributes, GetQueueUrl) — KEDA needs this to read queue depth for autoscaling |

*Note: A Kubernetes pod can only have one ServiceAccount. Therefore, shared permissions like Secrets Manager (for RDS credentials) and CloudWatch Logs (for centralized logging) are attached directly to each individual service's IRSA role.*

This replaces the EC2 instance profile approach. Each pod gets only the permissions it needs.

#### Step 1.4: Modify existing Terraform

**[MODIFY] `terraform/vpc.tf`**
- Add EKS subnet tags:
  - Public subnets: `kubernetes.io/role/elb = 1`
  - Private subnets: `kubernetes.io/role/internal-elb = 1`
  - All EKS subnets: `kubernetes.io/cluster/medilink-eks = shared`

**[MODIFY] `terraform/providers.tf`**
- Add `kubernetes` and `helm` providers (authenticated via EKS cluster endpoint)

**[DELETE] `terraform/autoscaling.tf`**
- Remove EC2 Launch Templates, ASGs, ASG scaling policies (replaced by EKS node groups + HPA)

**[MODIFY] `terraform/load_balancers.tf`**
- Remove internal ALB + all target groups + listener rules (replaced by KGateway inside EKS).
- **Keep the WAFv2 ACL resource** (`aws_wafv2_web_acl`) — move it to a new `terraform/waf.tf` file.
- **Delete** the ALB, target groups, listeners, and `aws_wafv2_web_acl_association` (the old ALB no longer exists in Terraform).
- The new ALB is auto-created by the AWS Load Balancer Controller when KGateway’s `Gateway` resource requests a `LoadBalancer` Service. WAF is attached via a Service annotation on that Gateway (see Phase 2).

> **Traffic flow (single path, no ambiguity):**
> `Internet → ALB (auto-created, WAF attached) → KGateway Envoy pods (JWT + routing + rate limiting) → Backend Services`
> There is NO separate Ingress resource. KGateway IS the ingress. The ALB is just the cloud infrastructure that exposes KGateway to the internet.

**[NEW] `terraform/lb_controller.tf`**
- IAM policy + role for AWS Load Balancer Controller
- Helm release for `aws-load-balancer-controller`

#### Step 1.5: Add SQS queue for RAG processing

**[MODIFY] `terraform/sqs.tf`**
- Add new queue: `medilink-rag-processing` (with DLQ: `medilink-rag-processing-dlq`)
- Same KMS encryption as existing queue
- Visibility timeout: 300s (Textract OCR can take time)

#### Step 1.6: Update S3 & Add AI Services Configuration

**[MODIFY] `terraform/s3.tf`**
- **Enable S3 Versioning**: Prevents accidental deletion or overwriting of medical records (HIPAA compliance).
- **Add S3 Lifecycle Rule**: Cost optimization for medical records. Transition objects to `STANDARD_IA` after 30 days, and to `GLACIER` after 365 days.
- Add S3 event notification (Optional): when object is created in `medilink-docs-production-bucket` → send message to `medilink-rag-processing` SQS queue (or trigger directly from `document-service`).

**[NEW] `terraform/bedrock.tf`**
- IAM permissions for Bedrock model access (Amazon Nova Lite v1 for generation, Titan for embeddings)
- Bedrock Guardrail resource (`aws_bedrock_guardrail`) — see Phase 6 for configuration details
- No infrastructure to provision — Bedrock is serverless

#### Step 1.7: Enable pgvector on RDS

**[MODIFY] `terraform/rds.tf`**
- Ensure RDS PostgreSQL version supports pgvector natively.
- *Note: You do not need to modify `shared_preload_libraries` for pgvector on RDS.*
- The `rag-service` will simply run `CREATE EXTENSION IF NOT EXISTS vector;` on startup.
- Set `backup_retention_period = 7` (healthcare app — backups must be enabled).
- Note: `multi_az` remains `false` for cost. If asked: "Production would enable Multi-AZ for automatic failover."

#### Step 1.8: Build and push Docker images

```bash
# Login to ECR
aws ecr get-login-password --region us-east-1 | docker login --username AWS --password-stdin <account>.dkr.ecr.us-east-1.amazonaws.com

# Build + push each service
for svc in user-service appointment-service health-service document-service rag-service rag-worker frontend; do
  docker build -t medilink/$svc:v1 ./$svc/
  docker tag medilink/$svc:v1 <account>.dkr.ecr.us-east-1.amazonaws.com/medilink/$svc:v1
  docker push <account>.dkr.ecr.us-east-1.amazonaws.com/medilink/$svc:v1
done
```

#### Verification:
```bash
terraform plan   # Should show: EKS cluster, ECR repos, IRSA roles, modified VPC
terraform apply
aws eks update-kubeconfig --name medilink-eks --region us-east-1
kubectl get nodes  # Should show 2 ready nodes
aws ecr describe-repositories  # Should show 7 repos (including rag-worker)
```

---

### Phase 2: Helm Charts + KGateway (Day 2-3)

**Goal**: Deploy all existing services to EKS via Helm with KGateway for API routing.

#### Step 2.1: Install Envoy Gateway (KGateway) + KEDA on EKS

```bash
# Install KGateway
helm install eg oci://docker.io/envoyproxy/gateway-helm \
  --version v1.3.0 \
  -n envoy-gateway-system --create-namespace

# Install KEDA (for event-driven autoscaling of rag-worker)
helm repo add kedacore https://kedacore.github.io/charts
helm repo update
helm install keda kedacore/keda -n keda --create-namespace
```

#### Step 2.2: Create Helm umbrella chart

**[NEW] `helm/medilink/Chart.yaml`**

Umbrella chart structure (modeled after your MediTrack pattern):
```
helm/medilink/
├── Chart.yaml              # Umbrella chart
├── values.yaml             # Production defaults
├── values-dev.yaml         # Dev overrides
├── templates/
│   ├── _helpers.tpl
│   ├── configmap.yaml
│   ├── namespaces/
│   ├── gateway/            # KGateway resources
│   │   ├── gatewayclass.yaml
│   │   ├── gateway.yaml
│   │   ├── httproute-public.yaml   # /login, /register, /health
│   │   ├── httproute-protected.yaml # Everything else (JWT required)
│   │   ├── securitypolicy.yaml     # JWT validation config
│   │   └── ratelimit.yaml
│   ├── network/
│   │   └── networkpolicy.yaml
│   └── rbac/
│       └── resource-quota.yaml
└── charts/
    ├── user-service/       # Subchart
    ├── appointment-service/
    ├── health-service/
    ├── document-service/
    ├── rag-service/        # NEW (API only)
    ├── rag-worker/         # NEW (SQS consumer + ScaledObject)
    ├── frontend/
    └── redis/              # NOTE: Demo only. Prod uses ElastiCache.
```

Each subchart contains:
- `deployment.yaml` — Pod spec with IRSA serviceAccount, resource limits, probes
- `service.yaml` — ClusterIP service
- `hpa.yaml` — HorizontalPodAutoscaler
- `pdb.yaml` — PodDisruptionBudget
- `serviceaccount.yaml` — With IRSA annotation

> **How WAF attaches (no separate Ingress needed):**
> KGateway’s `Gateway` resource creates a `LoadBalancer` Service. The AWS Load Balancer Controller auto-provisions an ALB for it. WAF attaches to this ALB via a **Service annotation**:
> ```yaml
> # In gateway/gateway.yaml — the auto-created Service gets this annotation:
> service.beta.kubernetes.io/aws-load-balancer-wafv2-acl-arn: arn:aws:wafv2:us-east-1:<account>:regional/webacl/medilink-production-waf/<id>
> ```
> There is **no `ingress.yaml`** in any subchart. KGateway’s HTTPRoute resources handle all routing.

The `rag-worker` subchart is special — it has no `service.yaml` or `hpa.yaml`. Instead it has:
- `deployment.yaml` — Pod spec running the SQS consumer loop
- `serviceaccount.yaml` — With `sa-rag-worker` IRSA annotation
- `scaledobject.yaml` — KEDA ScaledObject:
  ```yaml
  apiVersion: keda.sh/v1alpha1
  kind: ScaledObject
  metadata:
    name: rag-worker-scaledobject
  spec:
    scaleTargetRef:
      name: rag-worker
    minReplicaCount: 0        # Scale to zero when queue is empty
    maxReplicaCount: 10
    pollingInterval: 15       # Check queue every 15 seconds
    triggers:
      - type: aws-sqs-queue
        metadata:
          queueURL: <SQS_QUEUE_URL>
          queueLength: "5"    # 1 pod per 5 messages
          awsRegion: us-east-1
          identityOwner: operator  # Uses KEDA's own IRSA role (sa-keda)
  ```

#### Step 2.3: KGateway routing configuration

**Public routes (no JWT required):**
```
POST /login           → user-service:8001
POST /register        → user-service:8001
GET  /health          → (any service)
GET  /docs/*          → Swagger
```

**Protected routes (JWT validated by KGateway):**
```
GET/POST /appointments/*    → appointment-service:8002
GET/POST /health-records/*  → health-service:8003
GET/POST /documents/*       → document-service:8004
POST     /rag/*             → rag-service:8005
GET      /me                → user-service:8001
GET      /doctors           → user-service:8001
```

KGateway SecurityPolicy validates JWT and injects `X-User-ID` and `X-User-Role` headers into downstream requests — services no longer need to independently validate JWT (but keep the code for local dev compatibility).

#### Step 2.4: values.yaml key configuration

```yaml
global:
  registry: "<account>.dkr.ecr.us-east-1.amazonaws.com/medilink"
  imageTag: "v1"

  userService:
    replicas: 2
    resources:
      requests: { cpu: 100m, memory: 128Mi }
      limits: { cpu: 500m, memory: 512Mi }
    hpa:
      enabled: true
      minReplicas: 2
      maxReplicas: 5
      cpuUtilization: 70

  ragService:
    replicas: 2
    resources:
      requests: { cpu: 200m, memory: 256Mi }  # Higher — embedding work
      limits: { cpu: 1000m, memory: 1Gi }
    hpa:
      enabled: true
      minReplicas: 2
      maxReplicas: 6
      cpuUtilization: 60  # Lower threshold — scale sooner
```

#### Verification:
```bash
helm lint helm/medilink/ -f helm/medilink/values.yaml
helm install medilink-dev helm/medilink/ -n medilink-dev --create-namespace -f helm/medilink/values-dev.yaml
kubectl get pods -n medilink-dev  # All pods Running
kubectl get gateway -n medilink-dev  # Gateway Programmed
curl https://<alb-dns>/health  # 200 OK
curl https://<alb-dns>/appointments  # 401 Unauthorized (no JWT)
```

---

### Phase 3: RAG Service — Core Microservice (Day 3-4)

**Goal**: Build the new `rag-service` that handles OCR, embeddings, vector search, and LLM generation.

#### Step 3.1: Service structure

**[NEW] `rag-service/`**
```
rag-service/
├── Dockerfile
├── requirements.txt
├── app/
│   ├── main.py              # FastAPI app + lifespan
│   ├── config.py            # Environment/settings
│   ├── models.py            # SQLAlchemy models (document_chunks table)
│   ├── api/
│   │   ├── routes.py        # REST endpoints
│   │   └── schemas.py       # Pydantic models
│   ├── services/
│   │   ├── embedding_service.py # Bedrock Titan embeddings
│   │   ├── vector_store.py      # pgvector CRUD operations
│   │   ├── retriever.py         # Similarity search + reranking
│   │   ├── generator.py         # Bedrock Nova for answer generation (with Guardrails)
│   │   └── chunker.py           # Text chunking logic
│   └── utils/
│       ├── auth.py           # JWT validation (shared pattern)
│       ├── aws_utils.py      # Secrets Manager helper (shared)
│       └── confidence.py     # Confidence scoring logic
```

> **Note**: `rag-service` is **API-only**. It has no `workers/` folder. All SQS/Textract processing lives in the separate `rag-worker/` service (see Phase 4.2).

#### Step 3.2: REST API endpoints

| Method | Path | Auth | Description |
|--------|------|------|-------------|
| `POST` | `/rag/ingest` | Doctor | Manually trigger document ingestion (alternative to SQS) |
| `POST` | `/rag/query` | Doctor, Patient | Ask a question grounded in patient documents |
| `GET` | `/rag/documents/{patient_id}` | Doctor, Patient | List ingested/processed documents for a patient |
| `POST` | `/rag/report/{patient_id}` | Doctor | Generate AI clinical summary from all patient documents |
| `GET` | `/rag/status/{document_id}` | Doctor, Patient | Check processing status of a document |
| `GET` | `/health` | Public | Health check |

#### Step 3.3: Database schema (pgvector)

```sql
-- Run on startup via SQLAlchemy
CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE document_chunks (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    document_id UUID NOT NULL,        -- FK to document-service's documents table
    patient_id UUID NOT NULL,
    chunk_index INTEGER NOT NULL,
    chunk_text TEXT NOT NULL,
    embedding vector(1536) NOT NULL,  -- Titan embedding dimension
    metadata JSONB DEFAULT '{}',      -- page_number, source_file, section_header, category
    created_at TIMESTAMP DEFAULT NOW()
);

-- HNSW index for fast similarity search
CREATE INDEX ON document_chunks
  USING hnsw (embedding vector_cosine_ops)
  WITH (m = 16, ef_construction = 64);

CREATE TABLE document_processing_status (
    document_id UUID PRIMARY KEY,
    patient_id UUID NOT NULL,
    status TEXT DEFAULT 'pending',     -- pending, processing, completed, failed
    chunks_count INTEGER DEFAULT 0,
    category TEXT DEFAULT 'other',     -- Carried over from document-service
    extracted_metadata JSONB DEFAULT '{}',  -- diagnoses, medications, allergies extracted
    error_message TEXT,
    started_at TIMESTAMP,
    completed_at TIMESTAMP
);
```

Note: The `category` field from Phase 0 is carried into the RAG pipeline metadata, enabling category-filtered queries like "search only lab reports."

#### Step 3.4: RAG pipeline implementation

**Ingestion flow** (runs in `rag-worker/`, NOT in rag-service — see Phase 4.2):
```
1. Poll SQS queue (medilink-rag-processing)
2. Parse message → get S3 key, document_id, patient_id, category
3. Download document from S3
4. Call Textract:
   - If PDF: use start_document_analysis (async) for multi-page
   - If image: use analyze_document (sync)
   - Extract: raw text + tables + forms
5. Chunk extracted text:
   - Strategy: RecursiveCharacterTextSplitter
   - Chunk size: 512 tokens
   - Overlap: 50 tokens
   - Preserve paragraph boundaries
6. Embed each chunk:
   - Model: amazon.titan-embed-text-v2:0
   - Dimension: 1536
   - Batch embed (up to 25 chunks per API call)
7. Store chunks + embeddings in pgvector (with category in metadata)
8. Extract structured metadata:
   - Use Amazon Nova Lite v1 to extract: diagnoses, medications, allergies, lab results
   - Store as JSONB in document_processing_status
9. Update status to 'completed'
10. Delete SQS message
```

**Query flow** (`services/retriever.py` + `services/generator.py`):
```
1. Receive query + patient_id + optional category filter
2. Embed the query using Titan
3. pgvector similarity search:
   - WHERE patient_id = :patient_id
   - AND (category filter if provided, e.g., "lab_report" only)
   - ORDER BY embedding <=> query_embedding
   - LIMIT 5 (top-K)
   - Return: chunk_text, metadata, similarity_score
4. Calculate confidence score (see Phase 6)
5. Build prompt with retrieved chunks as context
6. Call Amazon Nova Lite v1 with constrained prompt + Guardrails
7. Post-process: extract citations, verify grounding
8. Return: answer, citations[], confidence_score, sources[]
```

---

### Phase 4: Async Event-Driven Pipeline Inside EKS (Day 4-5)

**Goal**: Make the RAG processing truly asynchronous and event-driven — not just another sync API call.

#### Step 4.1: Document upload → SQS message flow

**[MODIFY] `document-service/main.py`** — After `confirm_upload`:

```python
# After document status is set to COMPLETED in the database:
import boto3
sqs = boto3.client('sqs', region_name='us-east-1')
sqs.send_message(
    QueueUrl=os.getenv('RAG_QUEUE_URL'),
    MessageBody=json.dumps({
        'document_id': str(doc.id),
        'patient_id': str(doc.patient_id),
        's3_key': doc.s3_key,
        'file_type': doc.file_type,
        'category': doc.category,          # ← Category from Phase 0
        'uploaded_by': doc.uploaded_by,
        'timestamp': datetime.utcnow().isoformat()
    })
)
```

**What this achieves**: The doctor uploads a document → gets immediate "upload successful" response → walks away. The RAG pipeline processes it in the background. No waiting. No timeout risk.

#### Step 4.2: SQS consumer (Standalone Worker)

**[NEW] `rag-worker/main.py`**

Instead of running as a background thread inside the API pod, the SQS consumer runs as a **standalone Kubernetes Deployment**. This allows it to scale independently based on SQS queue depth using KEDA, rather than scaling on HTTP CPU load.

```python
async def sqs_consumer_loop():
    """Standalone worker that processes documents from SQS."""
    sqs = boto3.client('sqs')
    textract = boto3.client('textract')
    while True:
        response = sqs.receive_message(
            QueueUrl=RAG_QUEUE_URL,
            MaxNumberOfMessages=1,
            WaitTimeSeconds=20,  # Long polling
            VisibilityTimeout=300
        )
        for message in response.get('Messages', []):
            try:
                body = json.loads(message['Body'])
                
                # 1. Start Async Textract
                job = textract.start_document_analysis(
                    DocumentLocation={'S3Object': {'Bucket': BUCKET, 'Name': body['s3_key']}},
                    FeatureTypes=['TABLES', 'FORMS']
                )
                
                # 2. Polling Loop for Async Textract
                while True:
                    status = textract.get_document_analysis(JobId=job['JobId'])
                    if status['JobStatus'] in ['SUCCEEDED', 'FAILED']:
                        break
                    await asyncio.sleep(5)
                
                if status['JobStatus'] == 'SUCCEEDED':
                    await process_document(status, body)  # chunk → embed → store
                    sqs.delete_message(QueueUrl=RAG_QUEUE_URL, ReceiptHandle=message['ReceiptHandle'])
                elif status['JobStatus'] == 'FAILED':
                    logger.error(f"Textract job failed for doc {body['document_id']}")
                    # Don't delete → message returns to queue → retries → eventually DLQ
            except Exception as e:
                logger.error(f"Processing failed: {e}")
```

**`rag-worker/` full directory structure:**
```
rag-worker/
├── Dockerfile
├── requirements.txt          # boto3, asyncio, sqlalchemy, pgvector, etc.
├── main.py                   # Entry point: runs sqs_consumer_loop()
├── services/
│   ├── ocr_service.py        # Amazon Textract integration (sync + async)
│   ├── embedding_service.py  # Bedrock Titan embeddings (shared with rag-service)
│   ├── chunker.py            # Text chunking logic (shared with rag-service)
│   └── vector_store.py       # pgvector write operations
└── utils/
    └── aws_utils.py          # Secrets Manager helper
```

**`rag-worker/Dockerfile`:**
```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
RUN adduser --disabled-password --gecos '' appuser
USER appuser
CMD ["python", "main.py"]
```

> **Key difference from other services**: `rag-worker` runs `python main.py` (infinite loop), NOT `uvicorn` (web server). It has no HTTP endpoints, no FastAPI, no `service.yaml` in Helm.

#### Step 4.3: Processing status tracking

The frontend can poll `GET /rag/status/{document_id}` to show a progress indicator:

```
PENDING → PROCESSING → COMPLETED (or FAILED)
```

The doctor sees: "🔄 Processing your document..." → "✅ Document analyzed — 3 pages, 12 chunks extracted"

#### Why this matters for evaluators:

This shows you understand:
- **Decoupled producers and consumers** (document-service doesn't know about rag-service)
- **At-least-once delivery** (SQS guarantees the message is processed)
- **Failure handling** (retries + DLQ for poison messages)
- **Backpressure** (if rag-service is slow, messages queue up instead of failing)
- **Horizontal scaling** (add more rag-service pods → they all poll the same queue → parallel processing)

---

### Phase 5: RAG Query Flow — Category-Aware Search (Day 5)

> **⚠️ ENHANCED** — The RAG query flow now supports category-based filtering, leveraging the categorization added in Phase 0.

**Goal**: Enable doctors and patients to query documents with optional category filters.

#### 5.1: Category-filtered vector search

When a doctor asks "What were the latest lab results?", the system can:
1. Auto-detect the intent → filter to `category = "lab_report"` chunks only
2. Or let the user explicitly select a category scope in the chatbot UI

```python
async def search_similar_chunks(
    query_embedding: list[float],
    patient_id: str,
    category: str | None = None,  # ← Optional category filter
    top_k: int = 5,
    db: AsyncSession
):
    sql = """
        SELECT id, chunk_text, metadata, 1 - (embedding <=> :query_embedding) as similarity
        FROM document_chunks
        WHERE patient_id = :patient_id
    """
    if category:
        sql += " AND metadata->>'category' = :category"
    sql += " ORDER BY embedding <=> :query_embedding LIMIT :top_k"

    result = await db.execute(text(sql), {
        "query_embedding": str(query_embedding),
        "patient_id": patient_id,
        "category": category,
        "top_k": top_k
    })
    return result.fetchall()
```

#### 5.2: RAG query endpoint with category support

```python
class RAGQueryRequest(BaseModel):
    patient_id: str
    query: str
    category: str | None = None  # ← "lab_report", "prescription", etc. or None for all
    scope: str = "patient"       # "patient" (this patient only) or "all" (all accessible docs)
```

---

### Phase 6: Anti-Hallucination, Confidence Scoring & Guardrails (Day 6)

**Goal**: Make the AI answers trustworthy and evidence-grounded — with platform-level safety.

This is the most important differentiator from a typical chatbot project.

#### The 8-Layer Anti-Hallucination Strategy

```
Layer 1: RETRIEVAL GATING
├── If no documents exist for patient → "No medical documents found"
├── If similarity scores all < 0.3 → "No relevant information found in documents"
└── Never generate from general knowledge

Layer 2: CONSTRAINED SYSTEM PROMPT
├── "Answer ONLY based on the provided CONTEXT sections"
├── "If the context doesn't contain the answer, say 'This information is not available in the uploaded documents'"
├── "NEVER provide medical information from your training data"
└── "Every factual claim MUST reference a [Source X] tag"

Layer 3: CONTEXT INJECTION
├── Each retrieved chunk is labeled: [Source 1: report_2024.pdf, Page 3]
├── Chunks are provided verbatim — LLM cannot modify them
└── Maximum 5 chunks to prevent context confusion

Layer 4: CITATION ENFORCEMENT
├── Output format requires: { "answer": "...", "citations": [...] }
├── Each citation maps to a specific Source ID
└── Post-processing validates that cited sources actually exist in retrieved chunks

Layer 5: CONFIDENCE SCORING
├── Based on cosine similarity of retrieved chunks:
│   ├── All top-5 chunks similarity > 0.75 → confidence: "high" (green)
│   ├── At least 2 chunks > 0.6 → confidence: "medium" (yellow)
│   ├── Best chunk < 0.5 → confidence: "low" (red) + disclaimer
│   └── No chunks above 0.3 → "insufficient_evidence" → refuse to answer
└── Displayed prominently in the UI next to the answer

Layer 6: GROUNDING VERIFICATION (post-processing)
├── Extract medical entities from the answer (medications, diagnoses, values)
├── Check if each entity appears in at least one retrieved chunk
├── Flag ungrounded claims: "⚠️ This claim could not be verified against uploaded documents"
└── If >30% claims ungrounded → downgrade confidence to "low"

Layer 7: TEMPERATURE CONTROL
├── Temperature: 0.1 (near-deterministic)
├── Top-p: 0.9
└── No creative generation — factual extraction only

Layer 8: BEDROCK GUARDRAILS (NEW — platform-level safety)
├── Content Filters: Block hate, violence, sexual, misconduct (all HIGH)
├── Denied Topics:
│   ├── Self-harm or suicide methods
│   ├── Drug dosage recommendations without physician context
│   ├── Diagnosis confirmation → redirect: "Please consult your treating physician"
│   └── Non-medical topics (keeps AI focused on healthcare)
├── PII Filters (critical for healthcare):
│   ├── SSN → ANONYMIZE
│   ├── Phone numbers → ANONYMIZE
│   ├── Email addresses → ANONYMIZE
│   └── Credit card numbers → BLOCK
├── Word Filters: Block profanity, slurs
└── Guardrail intervention shown in UI: "⚠️ This query was blocked for patient safety"
```

> **Why Layer 8 matters**: Layers 1-7 are prompt-level — the LLM *might* ignore them. Layer 8 (Bedrock Guardrails) operates at the **AWS API level** — it intercepts requests and responses *before and after* the LLM processes them. The LLM cannot bypass it. This is defense-in-depth.

#### Terraform for Bedrock Guardrails

**[NEW] `terraform/bedrock.tf`** — Add Guardrail resource:

```hcl
resource "aws_bedrock_guardrail" "medilink" {
  name                      = "medilink-healthcare-guardrail"
  description               = "Content safety guardrails for MediLink medical AI assistant"
  blocked_input_messaging   = "Your query was blocked for patient safety. Please rephrase your question."
  blocked_output_messaging  = "The AI response was filtered for safety. Please consult your healthcare provider for this information."

  content_policy_config {
    filters_config {
      type            = "HATE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "VIOLENCE"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "SEXUAL"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
    filters_config {
      type            = "MISCONDUCT"
      input_strength  = "HIGH"
      output_strength = "HIGH"
    }
  }

  sensitive_information_policy_config {
    pii_entities_config {
      type   = "US_SOCIAL_SECURITY_NUMBER"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "PHONE"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "EMAIL"
      action = "ANONYMIZE"
    }
    pii_entities_config {
      type   = "CREDIT_DEBIT_CARD_NUMBER"
      action = "BLOCK"
    }
  }

  topic_policy_config {
    topics_config {
      name       = "self-harm"
      definition = "Providing methods or encouragement for self-harm or suicide"
      type       = "DENY"
    }
    topics_config {
      name       = "unsupervised-dosage"
      definition = "Recommending specific drug dosages without explicit physician context in the query"
      type       = "DENY"
    }
    topics_config {
      name       = "diagnosis-confirmation"
      definition = "Confirming or denying a medical diagnosis without physician review"
      type       = "DENY"
    }
    topics_config {
      name       = "off-topic"
      definition = "Questions unrelated to healthcare, medical records, or patient information"
      type       = "DENY"
    }
  }

  tags = {
    Name        = "medilink-healthcare-guardrail"
    Environment = "Production"
  }
}

resource "aws_bedrock_guardrail_version" "medilink" {
  guardrail_arn = aws_bedrock_guardrail.medilink.guardrail_arn
  description   = "Production v1"
}
```

#### Using Guardrails in rag-service code

**[MODIFY] `rag-service/app/services/generator.py`**:

```python
import boto3

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')

GUARDRAIL_ID = os.getenv("BEDROCK_GUARDRAIL_ID")
GUARDRAIL_VERSION = os.getenv("BEDROCK_GUARDRAIL_VERSION", "DRAFT")

async def generate_answer(prompt: str, context_chunks: list) -> dict:
    """Generate answer using Amazon Nova Lite v1 with Guardrails."""

    response = bedrock.converse(
        modelId="amazon.nova-lite-v1:0",
        guardrailConfig={
            "guardrailIdentifier": GUARDRAIL_ID,
            "guardrailVersion": GUARDRAIL_VERSION
        },
        messages=[{"role": "user", "content": [{"text": prompt}]}],
        system=[{"text": SYSTEM_PROMPT}],
        inferenceConfig={
            "maxTokens": 1024,
            "temperature": 0.1,
            "topP": 0.9
        }
    )

    if response['stopReason'] == 'guardrail_intervened':
        return {
            "answer": "The AI response was filtered for safety.",
            "guardrail_blocked": True,
            "confidence": "blocked",
            "citations": []
        }

    return {
        "answer": response['output']['message']['content'][0]['text'],
        "guardrail_blocked": False,
        "confidence": calculate_confidence(context_chunks),
        "citations": extract_citations(response['output']['message']['content'][0]['text'], context_chunks)
    }
```

#### Concrete prompt template:

```python
SYSTEM_PROMPT = """You are MediLink AI, a medical document assistant.

STRICT RULES:
1. Answer ONLY using information from the CONTEXT sections below.
2. If the context doesn't contain the answer, respond: "This information is not available in the uploaded medical documents."
3. NEVER use your general medical knowledge. NEVER speculate.
4. Every factual statement must cite its source using [Source N] notation.
5. For medications, dosages, and diagnoses: quote the exact text from the source.
6. End with a confidence disclaimer based on the provided confidence level.

CONTEXT:
{retrieved_chunks_with_source_labels}

CONFIDENCE LEVEL: {confidence_score}

USER QUESTION: {user_query}

RESPONSE FORMAT:
Provide your answer with inline [Source N] citations. Keep it concise and factual.
"""
```

#### Example response shown to user:

```
╔══════════════════════════════════════════════════════════════╗
║  🔍 AI Answer                                    🟢 High   ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Based on the uploaded records, the patient was prescribed   ║
║  Metformin 500mg twice daily [Source 1] for Type 2 Diabetes  ║
║  diagnosed on 2024-03-15 [Source 2]. The most recent HbA1c  ║
║  was 7.2% [Source 1].                                        ║
║                                                              ║
║  📎 Sources:                                                 ║
║  [1] lab_results_march2024.pdf — Page 2                      ║
║  [2] diagnosis_report.pdf — Page 1                           ║
║                                                              ║
║  🛡️ Verified by Bedrock Guardrails · PII redacted            ║
║  ⚠️ Always verify with the treating physician.               ║
╚══════════════════════════════════════════════════════════════╝
```

#### Example of Guardrails blocking a query:

```
╔══════════════════════════════════════════════════════════════╗
║  🛡️ Query Blocked                                🔴 Blocked ║
╠══════════════════════════════════════════════════════════════╣
║                                                              ║
║  Your query was blocked for patient safety.                  ║
║                                                              ║
║  Reason: MediLink AI cannot confirm or deny diagnoses.       ║
║  Please consult your treating physician directly.            ║
║                                                              ║
║  🛡️ Protected by AWS Bedrock Guardrails                      ║
╚══════════════════════════════════════════════════════════════╝
```

---

### Phase 7: System-Level AI Integration (Day 7)

**Goal**: AI is not just a chatbot page — it's woven into the core workflow.

#### 7.1: Auto-generated Patient Summary on Doctor Dashboard

**[MODIFY] `health-service/main.py`** — Add endpoint:

```
GET /health-records/summary/{patient_id}
```

When a doctor opens a patient's page, the frontend calls this endpoint. The health-service calls rag-service internally to generate:

```json
{
  "patient_summary": {
    "active_diagnoses": ["Type 2 Diabetes", "Hypertension"],
    "current_medications": ["Metformin 500mg", "Lisinopril 10mg"],
    "known_allergies": ["Penicillin"],
    "recent_lab_results": [...],
    "risk_flags": [
      { "flag": "HbA1c trending upward (6.8→7.2)", "severity": "medium", "source": "lab_results_march2024.pdf" }
    ],
    "last_updated": "2024-03-20T10:30:00Z",
    "confidence": "high"
  }
}
```

This is **cached in Redis** (TTL: 1 hour, invalidated on new document upload).

#### 7.2: Risk Flags on Doctor Dashboard

**[MODIFY] `frontend/src/pages/Dashboard.jsx`**

The doctor dashboard shows **proactive AI alerts**:
- 🔴 "Patient X has a potential drug interaction: Metformin + newly prescribed Ibuprofen"
- 🟡 "Patient Y's HbA1c trending upward over last 3 reports"
- 🟢 "Patient Z's blood pressure stable across last 5 visits"

These are generated when documents are ingested (async pipeline) and stored as structured metadata.

#### 7.3: Document Upload → Auto-extraction

When a doctor uploads a PDF (lab report, prescription, etc.):
1. Upload completes → "✅ Uploaded"
2. 10 seconds later (async SQS processing) → "📝 Extracted: 2 diagnoses, 3 medications, 1 allergy"
3. The extracted entities appear as **tags** on the document card in the UI
4. The doctor can correct/approve the AI extractions (human-in-the-loop)
5. The document's `category` badge (from Phase 0) is shown alongside

#### 7.4: Enhanced Chatbot with RAG

**[MODIFY] `frontend/src/pages/Chatbot.jsx`**

The existing chatbot now:
- Shows confidence scores (🟢 🟡 🔴) next to each response
- Shows clickable source citations (click → opens the PDF page)
- Has a scope selector: "Search all documents" vs "Search this patient only"
- Has a **category filter**: "All categories", "Lab Reports only", "Prescriptions only", etc.
- Shows "Processing..." when documents are still being ingested
- Shows Guardrail-blocked messages with clear safety explanations

**What evaluators see**: AI isn't a toy feature. It's the nervous system of the application. Remove it, and the workflow degrades.

---

### Phase 8: CI/CD Pipeline + ArgoCD (Day 8)

**Goal**: Production-grade CI/CD that evaluators can watch run live.

#### 8.1: GitHub Actions CI Pipeline

**[NEW] `.github/workflows/ci.yml`**

```yaml
name: CI Pipeline
on:
  push:
    branches: [dev, main]
  pull_request:
    branches: [main]

# AWS Authentication: Uses GitHub OIDC federation (not long-lived access keys).
# Configure IAM Identity Provider for GitHub Actions + trust policy.
permissions:
  id-token: write   # Required for OIDC
  contents: read

jobs:
  # Stage 1: Code Quality
  lint-and-test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Python Lint (flake8)
        run: pip install flake8 && flake8 ./rag-service/ ./user-service/ ...
      - name: Run unit tests
        run: pytest tests/ -v

  # Stage 2: Security Scan (SAST)
  sonarqube:
    needs: lint-and-test
    # SonarQube analysis (reuse your MediTrack template)
    # NOTE: Requires SONAR_TOKEN secret. If not available, make this stage `continue-on-error: true`

  # Stage 3: Dependency Scan (SCA)
  snyk:
    needs: sonarqube
    # Snyk vulnerability scan (reuse your MediTrack template)
    # NOTE: Requires SNYK_TOKEN secret. If not available, make this stage `continue-on-error: true`

  # Stage 4: Docker Build
  docker-build:
    needs: snyk
    strategy:
      matrix:
        service: [user-service, appointment-service, health-service, document-service, rag-service, rag-worker, frontend]
    steps:
      - name: Build image
        run: docker build -t medilink/${{ matrix.service }}:${{ github.sha }} ./${{ matrix.service }}/
      - name: Trivy scan
        uses: aquasecurity/trivy-action@master
        with:
          image-ref: medilink/${{ matrix.service }}:${{ github.sha }}
          severity: CRITICAL,HIGH
      - name: Push to ECR
        run: |
          aws ecr get-login-password | docker login --username AWS --password-stdin $ECR_REGISTRY
          docker tag medilink/${{ matrix.service }}:${{ github.sha }} $ECR_REGISTRY/medilink/${{ matrix.service }}:${{ github.sha }}
          docker push $ECR_REGISTRY/medilink/${{ matrix.service }}:${{ github.sha }}

  # Stage 5: Update GitOps repo
  update-gitops:
    needs: docker-build
    if: github.ref == 'refs/heads/main'
    steps:
      - name: Update image tags in GitOps repo
        run: |
          # Clone gitops repo, update values.yaml image tags, commit, push
          # ArgoCD detects the change and syncs
```

#### 8.2: Terraform CI/CD

**[NEW] `.github/workflows/terraform.yml`**

```yaml
name: Infrastructure CI/CD
on:
  push:
    paths: ['terraform/**']
    branches: [main]
  pull_request:
    paths: ['terraform/**']

jobs:
  plan:
    runs-on: ubuntu-latest
    steps:
      - name: terraform fmt -check
      - name: terraform init
      - name: terraform validate
      - name: terraform plan
      # Plan output posted as PR comment

  apply:
    needs: plan
    if: github.ref == 'refs/heads/main'
    environment: production  # Requires manual approval in GitHub
    steps:
      - name: terraform apply -auto-approve
```

#### 8.3: ArgoCD Setup

**Install ArgoCD on EKS:**
```bash
kubectl create namespace argocd
kubectl apply -n argocd -f https://raw.githubusercontent.com/argoproj/argo-cd/stable/manifests/install.yaml
```

**[NEW] `argocd/application.yaml`**

```yaml
apiVersion: argoproj.io/v1alpha1
kind: Application
metadata:
  name: medilink-prod
  namespace: argocd
spec:
  project: default
  source:
    repoURL: https://github.com/neerajb03/medilink-gitops
    path: helm/medilink
    targetRevision: main
    helm:
      valueFiles:
        - values.yaml
        - values-prod.yaml
  destination:
    server: https://kubernetes.default.svc
    namespace: medilink-prod
  syncPolicy:
    automated:        # For dev
      prune: true
      selfHeal: true
    # For prod: remove automated, require manual sync
```

**GitOps repo structure** (`medilink-gitops`):
```
medilink-gitops/
├── helm/medilink/
│   ├── Chart.yaml
│   ├── values.yaml
│   ├── values-dev.yaml
│   └── values-prod.yaml   ← CI updates image tags here
└── argocd/
    ├── app-dev.yaml
    └── app-prod.yaml
```

#### 8.4: GitHub OIDC → AWS IAM (Required for CI/CD)

**[NEW] `terraform/github_oidc.tf`**

Without this, GitHub Actions cannot authenticate to AWS. No ECR pushes, no Terraform applies.

```hcl
# IAM OIDC Identity Provider for GitHub Actions
resource "aws_iam_openid_connect_provider" "github_actions" {
  url             = "https://token.actions.githubusercontent.com"
  client_id_list  = ["sts.amazonaws.com"]
  thumbprint_list = ["6938fd4d98bab03faadb97b34396831e3780aea1"]
}

# IAM Role that GitHub Actions assumes
resource "aws_iam_role" "github_actions" {
  name = "medilink-github-actions-role"

  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [{
      Effect = "Allow"
      Principal = {
        Federated = aws_iam_openid_connect_provider.github_actions.arn
      }
      Action = "sts:AssumeRoleWithWebIdentity"
      Condition = {
        StringEquals = {
          "token.actions.githubusercontent.com:aud" = "sts.amazonaws.com"
        }
        StringLike = {
          "token.actions.githubusercontent.com:sub" = "repo:neerajb03/medilink-hub:*"
        }
      }
    }]
  })
}

# Attach policies: ECR push, EKS access, Terraform state
resource "aws_iam_role_policy_attachment" "github_ecr" {
  role       = aws_iam_role.github_actions.name
  policy_arn = "arn:aws:iam::aws:policy/AmazonEC2ContainerRegistryPowerUser"
}
```

In the CI pipeline, the `configure-aws-credentials` step uses this:
```yaml
- uses: aws-actions/configure-aws-credentials@v4
  with:
    role-to-assume: arn:aws:iam::<account>:role/medilink-github-actions-role
    aws-region: us-east-1
```

**Demo flow for evaluators:**
1. Push code change → GitHub Actions runs → builds image → pushes to ECR
2. CI updates `values-prod.yaml` with new image tag → commits to gitops repo
3. ArgoCD detects the change → shows "OutOfSync" in UI
4. Click "Sync" → rolling update happens → pods update one by one
5. Evaluator sees the entire flow in ArgoCD's visual application tree

---

### Phase 9: Kubernetes Security Hardening (Day 9)

**Goal**: Match your AWS-level security with K8s-level security.

#### 9.1: NetworkPolicies

**[NEW] `helm/medilink/templates/network/networkpolicy.yaml`**

Port your MediTrack NetworkPolicies, adapted for MediLink Hub:

```yaml
# Default deny all ingress
apiVersion: networking.k8s.io/v1
kind: NetworkPolicy
metadata:
  name: default-deny-ingress
spec:
  podSelector: {}
  policyTypes: [Ingress]

---
# Allow gateway → all services
# Allow appointment-service → SQS (egress)
# Allow rag-service → S3, Textract, Bedrock, SQS (egress)
# Allow all services → RDS (egress on port 5432)
# Allow all services → Redis (egress on port 6379)
# Deny inter-service communication except explicit
```

#### 9.2: Pod Security Standards

**[MODIFY] Helm namespace templates:**

```yaml
apiVersion: v1
kind: Namespace
metadata:
  name: medilink-prod
  labels:
    pod-security.kubernetes.io/enforce: restricted
    pod-security.kubernetes.io/warn: restricted
```

**[MODIFY] All deployment templates — add securityContext:**

```yaml
securityContext:
  runAsNonRoot: true
  runAsUser: 1000
  readOnlyRootFilesystem: true
  allowPrivilegeEscalation: false
  capabilities:
    drop: [ALL]
```

#### 9.3: Fix Dockerfiles to run as non-root

**[MODIFY] All Python `Dockerfile`s:**

```dockerfile
FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
# Security: run as non-root user
RUN adduser --disabled-password --gecos '' appuser
USER appuser
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8001"]
```

**[MODIFY] `frontend/Dockerfile` (Production Build):**
Ensure the React/Vite app is compiled and served by Nginx, not `npm run dev`.

```dockerfile
# Build Stage
FROM node:18-alpine AS build
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
RUN npm run build

# Serve Stage
FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
```

#### 9.4: IRSA verification

Each pod's service account is annotated with the IAM role ARN:
```yaml
annotations:
  eks.amazonaws.com/role-arn: arn:aws:iam::<account>:role/medilink-rag-service-role
```

When the pod calls `boto3.client('textract')`, it automatically uses the IRSA role — no hardcoded credentials, no instance profile shared across all pods.

---

### Phase 10: Resilience & Failure Scenarios (Day 10)

**Goal**: Be able to answer "What happens if X fails?" for every component.

#### 10.1: Failure Scenario Table (for your architecture doc)

| What Fails | What Happens | How It Recovers |
|------------|-------------|-----------------|
| **rag-worker pod crashes** mid-OCR | SQS message becomes visible again after visibility timeout (300s) | Another rag-worker pod picks it up. After 3 failures → DLQ. |
| **Textract API returns error** | rag-worker catches exception, logs it, doesn't delete SQS message | SQS retries. DLQ after 3 attempts. CloudWatch alarm fires. |
| **Bedrock API rate limited** | Circuit breaker activates (60s cooldown). Returns cached summary if available. | Exponential backoff retry. Falls back to "Summary unavailable, try again later." |
| **Bedrock Guardrails blocks a query** | User sees clear "Query blocked for safety" message with reason. | User rephrases query. Blocked query logged for audit. |
| **RDS goes down** | All services return 503. Health checks fail. | Kubernetes restarts pods (liveness probe). RDS is single-AZ for cost; production would enable Multi-AZ for automatic failover. |
| **Redis goes down** | Cache miss. Services fall back to direct DB queries. AI summaries regenerated. | Kubernetes restarts Redis pod. Cache rebuilds on demand (no data loss). |
| **S3 unreachable** | Document upload fails with clear error. RAG processing pauses. | S3 is 99.999999999% durable. VPC endpoint ensures private connectivity. |
| **One EKS node goes down** | Pods reschedule to remaining nodes. PDB ensures min availability. | EKS managed node group auto-replaces the node. |
| **SQS queue fills up** | Messages queue. Processing delayed but no data loss. | KEDA scales rag-worker pods based on queue depth → faster drain. |
| **Doctor-patient check fails** | Document access returns 503 (fail-closed, not fail-open). | Retry. If appointment-service is down, no documents served — secure default. |

#### 10.2: Add retry logic to inter-service HTTP calls

**[NEW] `shared/http_client.py`** (shared across services)

```python
import httpx
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=1, max=10),
    retry=retry_if_exception_type((httpx.ConnectTimeout, httpx.ReadTimeout))
)
async def resilient_get(url: str, headers: dict = None, timeout: float = 10.0):
    async with httpx.AsyncClient() as client:
        response = await client.get(url, headers=headers, timeout=timeout)
        response.raise_for_status()
        return response.json()
```

#### 10.3: Liveness vs Readiness probes in Helm charts

```yaml
livenessProbe:
  httpGet:
    path: /health
    port: 8005
  initialDelaySeconds: 15
  periodSeconds: 10
  failureThreshold: 3      # 3 failures → restart pod

readinessProbe:
  httpGet:
    path: /health/ready     # Checks DB + Redis connectivity
    port: 8005
  initialDelaySeconds: 5
  periodSeconds: 5
  failureThreshold: 2      # 2 failures → stop sending traffic
```

The key difference:
- **Liveness** = "Is the process alive?" → Restart if not
- **Readiness** = "Can it serve traffic?" → Remove from Service if not (but don't restart)

#### 10.4: Circuit breaker (reuse + formalize)

You already have this pattern in health-service with the `hf_down_until` timer. Move it to a proper reusable class:

```python
class CircuitBreaker:
    def __init__(self, failure_threshold=3, recovery_timeout=60):
        self.failures = 0
        self.threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.last_failure_time = 0
        self.state = "CLOSED"  # CLOSED → OPEN → HALF_OPEN

    async def call(self, func, *args, **kwargs):
        if self.state == "OPEN":
            if time.time() - self.last_failure_time > self.recovery_timeout:
                self.state = "HALF_OPEN"
            else:
                raise CircuitOpenError("Circuit breaker is open")
        try:
            result = await func(*args, **kwargs)
            self.failures = 0
            self.state = "CLOSED"
            return result
        except Exception as e:
            self.failures += 1
            if self.failures >= self.threshold:
                self.state = "OPEN"
                self.last_failure_time = time.time()
            raise
```

#### 10.5: Redis Distributed Lock for Concurrent Booking Prevention

**[MODIFY] `appointment-service/main.py`** — Add distributed locking for `POST /appointments`

To prevent double-booking when two patients try to book the same doctor at the same exact time, implement a Redis distributed lock:

```python
import redis.asyncio as redis

# Add to lifepsan/startup
redis_client = redis.from_url(os.getenv("REDIS_URL", "redis://redis.medilink-prod.svc.cluster.local:6379/0"))

@app.post("/appointments", status_code=201)
async def create_appointment(data: AppointmentCreate, user=Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    # Create a unique lock key for this doctor and time slot
    lock_key = f"lock:appt:{data.doctor_id}:{data.datetime.isoformat()}"
    
    # Try to acquire the lock with a 5-second expiration (NX = only if not exists)
    lock_acquired = await redis_client.set(lock_key, "locked", nx=True, ex=5)
    
    if not lock_acquired:
        raise HTTPException(
            status_code=409, 
            detail="This time slot is currently being booked by someone else."
        )
        
    try:
        # 1. Double check DB to ensure slot is still free
        # 2. Insert into DB
        # ... existing logic ...
    finally:
        # Release the lock when done
        await redis_client.delete(lock_key)
```
This is a highly impressive feature to explain to evaluators, showing you understand race conditions and distributed state management.

---

### Phase 11: Load Testing + Scaling Demo (Day 10)

**Goal**: Produce a visual demo of pods scaling under load.

#### 11.1: Write load test script

**[NEW] `tests/load/locustfile.py`**

```python
from locust import HttpUser, task, between

class MediLinkUser(HttpUser):
    wait_time = between(0.5, 2)

    def on_start(self):
        # Login and get JWT
        response = self.client.post("/login", json={
            "email": "doctor@medilink.com",
            "password": "password123"
        })
        self.token = response.json()["token"]
        self.headers = {"Authorization": f"Bearer {self.token}"}

    @task(3)
    def query_rag(self):
        """CPU-intensive — triggers HPA scaling"""
        self.client.post("/rag/query", json={
            "patient_id": "...",
            "query": "What medications is this patient currently taking?"
        }, headers=self.headers)

    @task(2)
    def list_records(self):
        self.client.get("/health-records", headers=self.headers)

    @task(1)
    def list_documents(self):
        self.client.get("/documents", headers=self.headers)
```

#### 11.2: Demo recording setup

Run in **split terminal** (record with screen capture):

```bash
# Terminal 1: Watch pods and HPA live
watch -n 2 'kubectl get hpa -n medilink-prod && echo "---" && kubectl get pods -n medilink-prod'

# Terminal 2: Run load test
locust -f tests/load/locustfile.py --host https://<alb-dns> --users 50 --spawn-rate 5 --run-time 5m --headless

# Terminal 3: Watch CloudWatch metrics (optional)
# Open CloudWatch dashboard in browser
```

**Expected demo outcome:**
```
Time 0:00 — rag-service: 2 pods, CPU: 15%
Time 1:00 — rag-service: 2 pods, CPU: 65%  ← HPA threshold hit
Time 1:30 — rag-service: 4 pods, CPU: 45%  ← Scaled out!
Time 3:00 — rag-service: 5 pods, CPU: 55%  ← Max reached
Time 5:00 — Load test ends
Time 8:00 — rag-service: 3 pods, CPU: 20%  ← Scaling in
Time 12:00 — rag-service: 2 pods, CPU: 10% ← Back to baseline
```

---

### Phase 12: AI-Driven Cloud Operations (AIOps) (Day 11)

**Goal**: Fulfill the "Adopt AI-Driven Cloud Operations Practices" requirement by building an AI agent that analyzes Kubernetes logs and identifies issues automatically.

#### Step 12.1: Create Lambda Function for Log Analysis

**[NEW] `terraform/lambda_aiops.tf`**
Create an EventBridge rule that triggers a Lambda function when an EKS pod crashes (e.g., matching CloudWatch log patterns for `OOMKilled` or `Error`).

```hcl
resource "aws_lambda_function" "eks_log_analyzer" {
  filename      = "lambda_aiops.zip"
  function_name = "medilink-eks-log-analyzer"
  role          = aws_iam_role.lambda_aiops.arn
  handler       = "index.handler"
  runtime       = "python3.11"
  
  environment {
    variables = {
      SNS_TOPIC_ARN = aws_sns_topic.alerts.arn
    }
  }
}
```

#### Step 12.2: Lambda Python Code

**[NEW] `lambda/aiops_analyzer/index.py`**
```python
import boto3
import json
import os

bedrock = boto3.client('bedrock-runtime', region_name='us-east-1')
sns = boto3.client('sns', region_name='us-east-1')

def handler(event, context):
    # 1. Parse EventBridge event for the failed Pod logs
    log_messages = str(event.get('detail', 'Log stream empty'))
    
    # 2. Call Amazon Nova to diagnose the issue
    prompt = f"You are an expert DevOps engineer. Analyze these Kubernetes logs and explain in one sentence why the pod crashed, and suggest a fix:\n\n{log_messages}"
    
    response = bedrock.converse(
        modelId="amazon.nova-lite-v1:0",
        messages=[{"role": "user", "content": [{"text": prompt}]}]
    )
    
    diagnosis = response['output']['message']['content'][0]['text']
    
    # 3. Publish AI Diagnosis to SNS
    sns.publish(
        TopicArn=os.environ['SNS_TOPIC_ARN'],
        Subject="EKS Pod Crash - AI Diagnosis",
        Message=f"An EKS pod crashed. Here is the AI diagnosis:\n\n{diagnosis}"
    )
```

**Why evaluators will love this**: It seamlessly integrates CloudWatch, EventBridge, Lambda, Amazon Nova, and SNS to create a self-diagnosing Kubernetes cluster.

---

## Summary: What You'll Demo to Evaluators

| Demo Moment | What You Show | Time |
|-------------|---------------|------|
| 1. **Architecture walkthrough** | Mermaid diagram with 23 AWS services | 3 min |
| 2. **Terraform apply** | `terraform plan` showing 50+ resources (incl. Bedrock Guardrails) | 2 min |
| 3. **CI/CD pipeline** | Push code → GitHub Actions runs 6 stages → image in ECR | 3 min |
| 4. **ArgoCD sync** | ArgoCD UI detecting change → syncing → pods updating | 2 min |
| 5. **KGateway JWT** | Request without token → 401. With token → 200. | 1 min |
| 6. **Document upload + categorization** | Upload PDF with category → SQS → rag-service processes → extracted entities appear | 3 min |
| 7. **RAG query with citations** | Ask "What medications?" → get answer with sources + confidence + Guardrails badge | 2 min |
| 8. **Guardrails safety demo** | Ask an unsafe query → show clear "blocked for safety" response | 1 min |
| 9. **Auto-generated patient summary** | Open patient → AI summary already there with risk flags | 2 min |
| 10. **Doctor-patient access control** | Doctor without relationship → 403. Doctor with appointment → full doc access | 1 min |
| 11. **Load test + HPA scaling** | Pods scaling 2 → 5 live on screen | 3 min |
| 12. **Failure scenario** | Kill a pod → show self-healing → circuit breaker activating | 2 min |
| 13. **Security** | IRSA, NetworkPolicies, Pod Security, WAF, KMS, Secrets Manager, Guardrails | 2 min |
| 14. **AIOps Log Analysis** | Intentionally crash a pod → Show email alert with AI diagnosis | 2 min |

**Total demo time: ~29 minutes** — packed, impressive, tells a cohesive story.

---

## Files Changed Summary

| Action | File/Directory | Component |
|--------|---------------|-----------|
| **[MODIFY]** | `document-service/main.py` | Phase 0: Fix security hole, add category, add patient_id filter, add SQS trigger |
| **[MODIFY]** | `appointment-service/main.py` | Phase 0: Add `/appointments/check-relationship` endpoint |
| **[MODIFY]** | `frontend/src/pages/Documents.jsx` | Phase 0: Add category dropdown + category badges |
| **[NEW]** | `terraform/ecr.tf` | Phase 1: ECR repositories |
| **[NEW]** | `terraform/eks.tf` | Phase 1: EKS cluster |
| **[NEW]** | `terraform/irsa.tf` | Phase 1: IRSA roles |
| **[NEW]** | `terraform/lb_controller.tf` | Phase 1: AWS LB Controller |
| **[NEW]** | `terraform/bedrock.tf` | Phase 1 + 6: Bedrock IAM + Guardrails |
| **[MODIFY]** | `terraform/vpc.tf` | Phase 1: EKS subnet tags |
| **[MODIFY]** | `terraform/providers.tf` | Phase 1: K8s + Helm providers |
| **[DELETE]** | `terraform/autoscaling.tf` | Phase 1: Remove EC2 ASG |
| **[DELETE]** | `terraform/load_balancers.tf` | Phase 1: Remove ALB (replaced by LB Controller) |
| **[MODIFY]** | `terraform/sqs.tf` | Phase 1: RAG processing queue |
| **[MODIFY]** | `terraform/rds.tf` | Phase 1: pgvector parameter group |
| **[NEW]** | `helm/medilink/` | Phase 2: Helm umbrella chart |
| **[NEW]** | `rag-service/` | Phase 3: New RAG microservice (API only) |
| **[NEW]** | `rag-worker/` | Phase 4: Standalone SQS consumer (Dockerfile, main.py, services/) |
| **[MODIFY]** | `health-service/main.py` | Phase 7: Patient summary endpoint |
| **[MODIFY]** | `frontend/src/pages/Dashboard.jsx` | Phase 7: Risk flags UI |
| **[MODIFY]** | `frontend/src/pages/Chatbot.jsx` | Phase 7: RAG chatbot with citations + Guardrails + categories |
| **[NEW]** | `.github/workflows/ci.yml` | Phase 8: CI pipeline |
| **[NEW]** | `.github/workflows/terraform.yml` | Phase 8: Terraform CI/CD |
| **[NEW]** | `argocd/application.yaml` | Phase 8: ArgoCD config |
| **[NEW]** | `terraform/github_oidc.tf` | Phase 8: GitHub Actions OIDC → IAM |
| **[NEW]** | `terraform/waf.tf` | Phase 1: WAFv2 ACL (moved from load_balancers.tf) |
| **[NEW]** | `shared/http_client.py` | Phase 10: Resilient HTTP client |
| **[NEW]** | `tests/load/locustfile.py` | Phase 11: Load testing |
| **[MODIFY]** | All `Dockerfile`s | Phase 9: Non-root user |
| **[NEW]** | `terraform/lambda_aiops.tf` | Phase 12: AIOps EventBridge + Lambda |
| **[NEW]** | `lambda/aiops_analyzer/index.py` | Phase 12: AI log analyzer code |

---

## Changelog (Additions vs Original Plan)

> This section documents what was added to the original plan.

### ✅ Phase 0: Pre-Migration Fixes (NEW PHASE)
- **0.1**: Fixed `pass` security hole in `GET /documents/{doc_id}` — any doctor could download any patient's documents
- **0.2**: Added `/appointments/check-relationship` endpoint — derives doctor-patient relationship from appointment history
- **0.3**: Enabled doctor access to full patient document history — no longer limited to per-appointment only
- **0.4**: Added document categorization — `category` column (lab_report, prescription, imaging, etc.) + frontend dropdown + badges
- **0.5**: Alembic migration for the new column

### ✅ Phase 6: Bedrock Guardrails (NEW LAYER 8)
- Added Layer 8 to the anti-hallucination strategy: **Bedrock Guardrails**
- Platform-level content safety (content filters, PII redaction, denied topics, word filters)
- Terraform resource for `aws_bedrock_guardrail` with healthcare-specific configuration
- Integration in `rag-service/generator.py` via `guardrailIdentifier` parameter
- Frontend shows Guardrails-blocked messages with clear safety explanations
- Failure scenario added for Guardrails intervention
- AWS services count updated: 22 → 23+
- Demo summary updated: added Guardrails safety demo (Demo Moment #8)

### ✅ Phase 10: Redis Distributed Locks (NEW SECTION 10.5)
- Added Redis distributed locking to prevent concurrent double-booking of appointments.
- Upgrades the appointment-service to use Redis (NX flag with TTL) to handle race conditions.
- Showcases understanding of high-concurrency distributed systems.

### ✅ Phase 1: S3 Versioning & Lifecycle Rules
- Added S3 Versioning to `terraform/s3.tf` to prevent accidental deletion of medical records (compliance).
- Added S3 Lifecycle Rules to transition older documents to Standard-IA (30 days) and Glacier (365 days) for cost optimization.

### ✅ Cross-cutting: Amazon Nova Upgrade
- Upgraded the text generation model in the RAG pipeline from Anthropic Claude 3 Sonnet to **Amazon Nova Lite v1** (`amazon.nova-lite-v1:0`).
- Updated the Bedrock Python integration to use the modern `converse` API which natively supports Nova and Guardrails.

### ✅ Cross-cutting: Category Integration
- Phase 0 categories flow into Phase 3 (RAG metadata), Phase 4 (SQS messages), Phase 5 (filtered search), Phase 7 (chatbot category filter)

### ✅ Phase 12: AI-Driven Cloud Operations (NEW PHASE)
- Added an AIOps pipeline (CloudWatch → EventBridge → Lambda → Bedrock Nova → SNS).
- Automatically diagnoses Kubernetes pod crashes using Amazon Nova Lite v1.
- Directly fulfills the requirement: "Build AI agents that analyze Kubernetes logs, identify issues, and notify engineering teams."

### ✅ Defense/Architecture Refinements
- **State Locking**: Added S3/DynamoDB remote state for Terraform to prevent CI/CD corruption.
- **KGateway JWT (RS256)**: Kept auth inside KGateway, but added a Phase 0.6 migration to refactor `user-service` to use RS256 asymmetric keys and expose a `/jwks.json` endpoint for Envoy.
- **SQS Scaling**: Moved SQS consumer to a standalone `rag-worker` Deployment (scaled by KEDA) instead of an API background thread.
- **Textract Async**: Added the missing polling loop `get_document_analysis` to the SQS worker.
- **Frontend Build**: Clarified the Dockerfile uses a multi-stage Nginx production build, not `npm run dev`.
- **Database / Cache**: Removed unnecessary `shared_preload_libraries` for RDS pgvector. Flagged Redis as demo-only vs production ElastiCache.
