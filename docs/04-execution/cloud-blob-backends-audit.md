# Cloud Blob Backends — Design Audit

Step 0 of production backend implementation.
Analysis only — no code changes.

---

## 1. Current State

### Files

| File | Role |
|------|------|
| `apps/api/app/storage/base.py` | `BlobRef` dataclass, `compute_sha256`, `BlobStore` Protocol |
| `apps/api/app/storage/local.py` | `LocalBlobStore` — filesystem backend |
| `apps/api/app/storage/factory.py` | `create_blob_store(settings)` — backend selector |
| `apps/api/app/storage/__init__.py` | Re-exports |
| `apps/api/app/config.py` | `Settings` with `blob_backend`, `blob_local_root`, `blob_inline_threshold_bytes` |
| `apps/api/app/dependencies.py` | `get_blob_store()` — lru_cache singleton for FastAPI DI |
| `apps/api/app/services/ingestion.py` | `_persist_artifact` — write path; `_blob_key()` — key generation |
| `apps/api/app/routes/artifacts.py` | `_resolve_data` — read path (inline or blob→get→json.loads) |

### BlobStore Protocol

```python
class BlobStore(Protocol):
    provider_name: str  # property
    def put(self, key: str, data: bytes, *, content_type: str = "application/json") -> BlobRef
    def get(self, key: str) -> bytes                # raises FileNotFoundError
    def delete(self, key: str) -> bool              # True if deleted, False if missing
    def exists(self, key: str) -> bool
```

### BlobRef

```python
@dataclass(frozen=True, slots=True)
class BlobRef:
    provider: str
    key: str
    size_bytes: int
    content_type: str
    sha256: str
    created_at: datetime
```

### Key generation

```python
def _blob_key(project_id, run_id, artifact_id) -> str:
    return f"projects/{project_id}/runs/{run_id}/artifacts/{artifact_id}.json"
```

### DB model (Artifact)

- `storage_kind`: `"inline"` or `"blob"` (check constraint)
- `inline_data`: JSONB, NULL when blob
- `blob_path`: Text, NULL when inline (stores the key string)
- `size_bytes`, `sha256`: always populated when data exists
- Check constraint: `ck_artifacts_storage_consistency` enforces mutual exclusivity

### Write path

`_persist_artifact` → serializes `inline_data` → checks `size > threshold` → calls `blob_store.put(key, raw)` → sets `blob_path = key`, `inline_data = None`.

### Read path

`_resolve_data` → if `"blob"` → `blob_store.get(artifact.blob_path)` → `json.loads(raw)`.

### Tests

| File | Coverage |
|------|----------|
| `test_blob_storage.py` | BlobRef, compute_sha256, LocalBlobStore (CRUD, nested keys, path safety, large payload, root creation), Settings defaults, factory (local, unknown, case-insensitive) |
| `test_blob_offload.py` | End-to-end ingest with low threshold, inline vs blob, file on disk, size/sha256, GET /v1/artifacts/{id}, NULL semantics, preview, boundary, key shape, timeline storage_kind |
| `test_artifacts.py` | Artifact fetch for blob rows, missing blob → 404, timeline ref storage_kind |

---

## 2. Current Abstraction Fitness

### Is BlobStore sufficient for S3 and Azure?

**Yes.** The four methods (`put`, `get`, `delete`, `exists`) map directly to both providers:

| BlobStore | S3 | Azure |
|-----------|-----|-------|
| `put(key, data)` | `put_object(Bucket, Key, Body)` | `upload_blob(data)` |
| `get(key)` | `get_object(Bucket, Key)['Body'].read()` | `download_blob().readall()` |
| `delete(key)` | `delete_object(Bucket, Key)` | `delete_blob()` |
| `exists(key)` | `head_object(Bucket, Key)` | `get_blob_properties()` |

The `bytes`-in / `bytes`-out contract is the right level of abstraction for Leer's current needs. No streaming upload/download is needed yet — payloads are already fully materialized in `_persist_artifact` before calling `put`.

### Is BlobRef sufficient?

**Mostly yes, with one gap.** The spec (blob-storage.md §Blob Object Abstraction) lists "bucket / container" as a minimum conceptual field, but `BlobRef` does not include it. However:

- `BlobRef` is currently only used as a return value from `put` — it is **not persisted** in the DB. The DB stores `blob_path` (the key) and nothing else.
- The bucket/container is a backend configuration concern, not an artifact concern.
- Adding `bucket` to `BlobRef` is optional but recommended for debugging and future migration tooling.

**Recommendation:** Add an optional `bucket: str | None = None` field to `BlobRef`. Not blocking, but useful. Can be deferred.

### Should provider-specific metadata stay out of the DB model?

**Yes.** The current model is correct:
- `blob_path` stores the portable object key
- No bucket, region, endpoint, or credentials in artifact rows
- Provider config lives entirely in `Settings`

No DB model changes are needed for cloud backends.

---

## 3. S3 Adapter Design

### Module

`apps/api/app/storage/s3.py` → class `S3BlobStore`

### Client

Use `boto3` S3 client (not resource). Create a `boto3.client("s3")` at init time.

```python
class S3BlobStore:
    def __init__(self, bucket: str, prefix: str = "", region: str | None = None):
        self._bucket = bucket
        self._prefix = prefix
        self._client = boto3.client("s3", region_name=region)
```

### Auth / config model

Rely entirely on the boto3 credential chain (env vars, shared config, instance profile, ECS task role, IRSA). Do NOT accept `aws_access_key_id` / `aws_secret_access_key` as Leer settings. Developers who need explicit keys use standard AWS env vars (`AWS_ACCESS_KEY_ID`, etc.) which boto3 reads automatically.

This avoids:
- Leer-specific secret fields that duplicate AWS convention
- Accidental logging of secrets through Settings repr
- Config sprawl

### Required settings

| Setting | Type | Default | Notes |
|---------|------|---------|-------|
| `blob_s3_bucket` | `str` | (required when backend=s3) | Bucket name |
| `blob_s3_region` | `str \| None` | `None` | Passed to boto3; None = use SDK default |
| `blob_s3_prefix` | `str` | `""` | Prepended to all keys |

### Key strategy

The existing `_blob_key()` returns `projects/{pid}/runs/{rid}/artifacts/{aid}.json`.
S3 adapter prepends the prefix: `{blob_s3_prefix}{blob_key}`.

This is fully compatible — S3 keys are arbitrary UTF-8 strings up to 1024 bytes, and the hierarchical `/`-separated structure works naturally with S3 console navigation.

### Content-type handling

`put_object` accepts `ContentType`. The adapter should pass through the `content_type` parameter from `BlobStore.put`.

### Error mapping

| S3 error | BlobStore contract |
|----------|-------------------|
| `ClientError` with `NoSuchKey` on `get_object` | → `FileNotFoundError` |
| `ClientError` with `NoSuchKey` on `head_object` | → return `False` from `exists` |
| `ClientError` with `NoSuchKey` on `delete_object` | S3 `delete_object` is idempotent — returns 204 even if missing → return `False` only if we confirm non-existence (use `head_object` before or accept S3's idempotent delete and always return `True`; recommend returning `True` to match S3 semantics and avoid an extra HEAD call) |
| Other `ClientError` / `BotoCoreError` | Let propagate — caller handles |

**Recommendation for `delete`:** S3 `delete_object` does not error on missing keys. Two options:
- (a) Always return `True` (simpler, one API call)
- (b) `head_object` first, then `delete_object` (matches LocalBlobStore semantics exactly)

**Choose (a)** — simpler, cheaper, and the return value of `delete` is not used for correctness anywhere in Leer. Document the behavioral difference.

### Caveats

- **Retries:** boto3 has built-in retry with exponential backoff. Default retry config (max_attempts=3 in standard mode) is sufficient.
- **Multipart:** Not relevant. Leer payloads are JSON blobs, typically < 10 MB even for very large stream histories. `put_object` handles up to 5 GB in a single call.
- **Consistency:** S3 provides strong read-after-write consistency since December 2020. No stale-read concern.
- **Eventual delete visibility:** After `delete_object`, subsequent reads may briefly succeed in edge cases. Not a practical concern for Leer.

---

## 4. Azure Adapter Design

### Module

`apps/api/app/storage/azure.py` → class `AzureBlobStore`

### Client

Use `azure-storage-blob` SDK. Create a `ContainerClient` at init time.

```python
from azure.storage.blob import ContainerClient

class AzureBlobStore:
    def __init__(self, container_client: ContainerClient, prefix: str = ""):
        self._container = container_client
        self._prefix = prefix
```

The constructor takes a `ContainerClient` rather than raw strings, so the factory can build it using either auth method.

### Auth / config model

Support two auth modes (factory decides which to use):

1. **Connection string** (dev/simple): `BLOB_AZURE_CONNECTION_STRING` → `ContainerClient.from_connection_string(conn_str, container_name)`
2. **Account URL + DefaultAzureCredential** (production): `BLOB_AZURE_ACCOUNT_URL` → `ContainerClient(account_url + "/" + container, credential=DefaultAzureCredential())`

Priority: if connection string is set, use it. Otherwise, require account URL and use `DefaultAzureCredential`.

### Required settings

| Setting | Type | Default | Notes |
|---------|------|---------|-------|
| `blob_azure_container` | `str` | (required when backend=azure) | Container name |
| `blob_azure_account_url` | `str \| None` | `None` | Required if no connection string |
| `blob_azure_connection_string` | `str \| None` | `None` | Takes precedence over account_url |
| `blob_azure_prefix` | `str` | `""` | Prepended to all keys |

### Key strategy

Same as S3 — Azure blob names support `/` separators and are up to 1024 chars. The existing `_blob_key()` output is fully compatible.

Adapter prepends prefix: `{blob_azure_prefix}{blob_key}`.

### Content-type handling

`upload_blob` accepts `content_type` via `ContentSettings(content_type=...)`. Pass through from `BlobStore.put`.

### Error mapping

| Azure error | BlobStore contract |
|-------------|-------------------|
| `ResourceNotFoundError` on download | → `FileNotFoundError` |
| `ResourceNotFoundError` on `get_blob_properties` | → return `False` from `exists` |
| `ResourceNotFoundError` on `delete_blob` | → return `False` from `delete` |
| Other `Azure*Error` | Let propagate |

Azure's `delete_blob` raises `ResourceNotFoundError` when the blob doesn't exist (unlike S3's idempotent delete). This maps cleanly to returning `False`, matching `LocalBlobStore` semantics exactly.

### Caveats

- **Transfer options:** `upload_blob(overwrite=True)` must be set — Azure defaults to failing on existing blobs. Leer's `put` should be idempotent.
- **Max blob size:** Block blobs support up to ~190 GB via `upload_blob` (SDK handles chunking internally). Not a concern.
- **Consistency:** Azure Blob Storage provides strong consistency. No stale-read concern.
- **DefaultAzureCredential chain:** Works with managed identity, Azure CLI, env vars, workload identity. Suitable for production. May be slow on first call in local dev if no Azure credentials are configured — acceptable since Azure backend is not the dev default.

---

## 5. Settings / Config Design

### Proposed Settings additions

```python
class Settings(BaseSettings):
    # --- App ---
    app_name: str = "leer-api"
    app_env: str = "development"

    # --- Database ---
    database_url: str

    # --- Blob storage (shared) ---
    blob_backend: str = "local"                         # "local" | "s3" | "azure"
    blob_inline_threshold_bytes: int = 256 * 1024

    # --- Blob storage: local ---
    blob_local_root: str = ".leer/blobs"

    # --- Blob storage: S3 ---
    blob_s3_bucket: str | None = None
    blob_s3_region: str | None = None
    blob_s3_prefix: str = ""

    # --- Blob storage: Azure ---
    blob_azure_container: str | None = None
    blob_azure_account_url: str | None = None
    blob_azure_connection_string: str | None = None
    blob_azure_prefix: str = ""

    # --- Optional ---
    log_level: str = "info"
```

### Design notes

- All cloud settings default to `None` — they are only required when the corresponding backend is selected.
- The factory validates that required fields are present for the selected backend and raises a clear error otherwise.
- `blob_s3_prefix` and `blob_azure_prefix` default to `""` (no prefix). This is the simplest starting point.
- AWS credentials are NOT Leer settings — they flow through standard `AWS_*` env vars that boto3 reads.
- Azure connection string is a Leer setting because the factory needs it to choose the auth method.

### Mutual exclusivity

Settings themselves are not mutually exclusive — you can have S3 and Azure fields defined simultaneously. Only `blob_backend` determines which adapter is created. This is deliberate:
- Avoids validation complexity
- Supports config files that pre-define all backends for environment switching
- The factory is the single enforcement point

### Env var mapping

```
BLOB_BACKEND=s3
BLOB_S3_BUCKET=leer-artifacts-prod
BLOB_S3_REGION=eu-west-1
BLOB_S3_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

```
BLOB_BACKEND=azure
BLOB_AZURE_CONTAINER=leer-artifacts
BLOB_AZURE_ACCOUNT_URL=https://myaccount.blob.core.windows.net
BLOB_AZURE_PREFIX=artifacts/
BLOB_INLINE_THRESHOLD_BYTES=262144
```

---

## 6. Factory Design

### Proposed `create_blob_store`

```python
def create_blob_store(settings: Settings) -> BlobStore:
    backend = settings.blob_backend.lower()

    if backend == "local":
        return LocalBlobStore(root=settings.blob_local_root)

    if backend == "s3":
        if not settings.blob_s3_bucket:
            raise ValueError("blob_s3_bucket is required when blob_backend='s3'")
        return S3BlobStore(
            bucket=settings.blob_s3_bucket,
            prefix=settings.blob_s3_prefix,
            region=settings.blob_s3_region,
        )

    if backend == "azure":
        if not settings.blob_azure_container:
            raise ValueError("blob_azure_container is required when blob_backend='azure'")
        container_client = _build_azure_container_client(settings)
        return AzureBlobStore(
            container_client=container_client,
            prefix=settings.blob_azure_prefix,
        )

    raise ValueError(
        f"Unknown blob_backend: {settings.blob_backend!r}. "
        "Supported: 'local', 's3', 'azure'."
    )
```

### Validation strategy

**Eager at startup.** The factory is called once via `_blob_store_singleton()` during the first request (lru_cache). If config is wrong, the first request fails with a clear ValueError. This is acceptable because:
- The singleton pattern means the error surfaces immediately
- Misconfigured storage should fail fast, not silently on the first blob write
- No extra startup probe needed

### Test simplicity

- Tests override `get_blob_store` dependency with a `LocalBlobStore(tmp_path)` — no change needed.
- Factory tests use `Settings(database_url="sqlite:///:memory:", blob_backend="s3", blob_s3_bucket="test")` with mocked boto3 client.
- Cloud adapters are tested with mocked SDK clients, never real cloud calls.

---

## 7. Security and Deployment Notes

### Recommended auth methods

| Provider | Production | Local dev |
|----------|-----------|-----------|
| AWS S3 | IAM role / IRSA / ECS task role (no explicit keys) | `AWS_ACCESS_KEY_ID` + `AWS_SECRET_ACCESS_KEY` env vars, or `aws sso login` |
| Azure | Managed identity–based auth for Azure-hosted deployments (see note below) | Connection string via `BLOB_AZURE_CONNECTION_STRING`, or `az login` |

### Azure production credential note

The adapter uses `DefaultAzureCredential` for broad compatibility — it covers managed identity, workload identity, Azure CLI, and env vars automatically. This is the correct default for Step 1 implementation. However, for Azure-hosted production deployments, docs should recommend that teams consider replacing the default chain with a more specific credential such as `ManagedIdentityCredential` for tighter control and faster auth resolution. This aligns with current Microsoft guidance that `DefaultAzureCredential` is ideal for development and general-purpose use, but production-deployed services benefit from a known, narrower credential path.

### What to recommend in docs

- Production: never use long-lived access keys. Use IAM roles (AWS) or managed identity (Azure).
- Azure-hosted production: prefer `ManagedIdentityCredential` over the full `DefaultAzureCredential` chain when the deployment environment is known.
- Local dev: use the `local` backend. Only use cloud backends locally if actively testing cloud integration.
- Buckets/containers should be **private** (no public access).
- All artifact reads go through the Leer API — no direct browser-to-storage access.

### What to explicitly avoid storing in DB

- Cloud credentials of any kind
- Signed URLs
- Public URLs
- Bucket/container names (the key alone is sufficient; bucket is config)
- Provider endpoint URLs

### Secrets handling guidance

- Never log `Settings` repr in production (connection strings would leak). Pydantic's `SecretStr` is an option for `blob_azure_connection_string` but adds friction. Recommend relying on log-level discipline and redaction middleware instead.
- Do not pass secrets through Leer API request/response payloads.

---

## 8. Testing Plan

### Pure unit tests for adapters

**`test_blob_storage.py` additions:**

For each cloud adapter (S3, Azure):
- `test_protocol_conformance` — `isinstance(store, BlobStore)` ✓
- `test_provider_name` — returns `"s3"` / `"azure"` ✓
- `test_put_calls_sdk_correctly` — mock SDK client, verify call args (key, body, content_type)
- `test_get_returns_bytes` — mock SDK client to return known bytes
- `test_get_missing_raises_file_not_found` — mock SDK to raise provider error → assert `FileNotFoundError`
- `test_delete_existing_returns_true`
- `test_delete_missing_returns_false` (Azure) / `test_delete_returns_true_always` (S3, document difference)
- `test_exists_true` / `test_exists_false`
- `test_prefix_prepended_to_key` — verify all methods prepend prefix
- `test_content_type_passed_through` — verify `put` forwards content_type to SDK

### Config / factory tests

**`test_blob_storage.py` additions:**

- `test_creates_s3_backend` — `Settings(blob_backend="s3", blob_s3_bucket="b")` → `isinstance(S3BlobStore)`
- `test_s3_missing_bucket_raises` — `Settings(blob_backend="s3")` → `ValueError`
- `test_creates_azure_backend_with_connection_string`
- `test_creates_azure_backend_with_account_url`
- `test_azure_missing_container_raises`
- `test_azure_no_auth_raises` — neither connection string nor account URL set
- Existing unknown-backend and case-insensitive tests remain unchanged

### Mock strategy

- S3: `unittest.mock.patch("boto3.client")` or pass a mock client to constructor
- Azure: pass a mock `ContainerClient` directly to `AzureBlobStore.__init__`

### What NOT to test in CI

- No real S3 calls
- No real Azure calls
- No localstack / Azurite containers (can be added later as optional integration tests)

### Parity with LocalBlobStore tests

Every behavioral test in `TestLocalBlobStoreBasic` should have a corresponding mock-based test for S3 and Azure adapters:
- put + get roundtrip (mocked)
- get missing → FileNotFoundError
- delete existing → True
- delete missing → False (or True for S3, documented)
- exists → True / False
- content_type forwarding
- prefix handling (cloud-specific, no local equivalent)

---

## 9. Non-Goals for This Step

Explicitly NOT doing:
- No code implementation of S3 or Azure adapters
- No cloud provisioning guide (Terraform, CloudFormation, ARM templates)
- No signed URL / presigned URL generation
- No streaming direct-to-cloud upload (client → S3/Azure bypass)
- No encryption-at-rest / KMS / BYOK abstraction
- No lifecycle / retention / archival policies
- No provider-specific UI badges or controls
- No GCS adapter (can follow the same pattern later)
- No S3-compatible backends (MinIO, R2, Backblaze) — these would work through the S3 adapter with an endpoint override, but that is future scope

---

## 10. Risks / Edge Cases

| Risk | Mitigation |
|------|-----------|
| boto3 / azure-storage-blob become heavy dependencies | Make them optional imports — only import when the backend is selected. Factory raises `ImportError` with install instructions if the SDK is missing. |
| `delete` semantics differ between S3 and Local/Azure | Document the difference. S3 adapter returns `True` always from `delete`; this is acceptable since Leer never branches on the return value. |
| Connection string in env var leaks in logs | Do not log full Settings. Consider `SecretStr` for connection_string field if needed later. |
| Azure `upload_blob` defaults to error on existing blob | Always pass `overwrite=True`. |
| Large payloads approaching S3's 5 GB put_object limit | Not a realistic concern for JSON artifacts. Monitor `size_bytes` in production. |
| Factory creates client at import time if misconfigured | Factory is called lazily (lru_cache on first request). Misconfiguration fails fast on first request, which is the correct behavior. |
| Tests import boto3/azure-sdk even when not needed | Guard cloud adapter imports behind backend selection. Test files can use `pytest.importorskip("boto3")` for adapter-specific tests. |

---

## 11. Recommended Implementation Order

| Step | What | Why |
|------|------|-----|
| 1a | Add S3/Azure settings to `config.py` | Foundation — no behavioral change, all defaults are None |
| 1b | Implement `S3BlobStore` in `storage/s3.py` | S3 is the most common cloud storage; boto3 is well-understood |
| 1c | Add S3 branch to `create_blob_store` in `factory.py` | Wires S3 into the system |
| 1d | Add S3 adapter tests (mocked) | Verify behavior before moving on |
| 2a | Implement `AzureBlobStore` in `storage/azure.py` | Same pattern, second provider |
| 2b | Add Azure branch to `factory.py` | Wires Azure in |
| 2c | Add Azure adapter tests (mocked) | Verify behavior |
| 3 | Update `__init__.py` exports | Expose new classes |
| 4 | Update setup docs + env examples | Make it usable |

**S3 first, then Azure.** Rationale:
- S3 is simpler (fewer auth modes, idempotent delete, no `overwrite` flag needed)
- Validates the pattern before tackling Azure's slightly more complex auth
- Can ship S3 support independently if Azure is not urgent

---

## 12. Direct Answers

### Is the current BlobStore abstraction good enough as-is?

**Yes.** `put` / `get` / `delete` / `exists` with `bytes` payloads map directly to both S3 and Azure. No method additions needed. The only optional improvement is adding `bucket: str | None = None` to `BlobRef` for observability — not blocking.

### What exact settings should be added?

```
blob_s3_bucket: str | None = None
blob_s3_region: str | None = None
blob_s3_prefix: str = ""
blob_azure_container: str | None = None
blob_azure_account_url: str | None = None
blob_azure_connection_string: str | None = None
blob_azure_prefix: str = ""
```

Seven new fields. All default to `None` or `""`. No existing fields change.

### Should we implement S3 first, Azure first, or both together?

**S3 first.** It validates the cloud adapter pattern with the simpler provider. Azure follows the identical structure.

### What is the lowest-risk implementation order?

1. Settings additions (zero behavioral change)
2. S3 adapter + factory branch + tests
3. Azure adapter + factory branch + tests
4. Docs and env examples

Each step is independently shippable and testable. No step changes existing behavior.
