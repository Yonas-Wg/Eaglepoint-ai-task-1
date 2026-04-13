import csv
import io
import json
import logging
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from jose import JWTError, jwt
from passlib.context import CryptContext
from sqlalchemy import DateTime, create_engine, func, text
from sqlalchemy.orm import Session, sessionmaker

from app.models import (
    AuditLog,
    Base,
    DataCollectionBatch,
    FundingAccount,
    MaterialChecklistItem,
    MaterialVersion,
    QualityValidationResult,
    RegistrationAccess,
    Registration,
    ReviewRecord,
    Transaction,
    User,
)
from app.schemas import AccessAssignIn, BatchIn, BatchReviewIn, BudgetUpdateIn, CorrectionIn, DeadlineIn, LoginIn, RegistrationIn, TransactionIn


def parse_bool(raw: str | None, default: bool = False) -> bool:
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def decrypt_config_value(raw: str, encryption_key: str | None) -> str:
    if not raw.startswith("ENC:"):
        return raw
    if not encryption_key:
        raise ValueError("Encrypted config value provided but CONFIG_ENCRYPTION_KEY is missing")
    from cryptography.fernet import Fernet, InvalidToken
    try:
        token = raw.removeprefix("ENC:").encode("utf-8")
        return Fernet(encryption_key.encode("utf-8")).decrypt(token).decode("utf-8")
    except InvalidToken as exc:
        raise ValueError("Unable to decrypt config value with provided key") from exc


def load_secret_key() -> str:
    raw_secret = os.getenv("SECRET_KEY")
    if not raw_secret:
        raise RuntimeError("SECRET_KEY must be configured")
    encryption_key = os.getenv("CONFIG_ENCRYPTION_KEY")
    return decrypt_config_value(raw_secret, encryption_key)


SECRET_KEY = load_secret_key()
ALGORITHM = "HS256"
MAX_ATTEMPTS = 10
LOCK_MINUTES = 30
WINDOW_MINUTES = 5
APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL must be configured")
SIMILARITY_CHECK_ENABLED = parse_bool(os.getenv("SIMILARITY_CHECK_ENABLED"), default=False)
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/app/storage"))
AUTO_BACKUP_ENABLED = parse_bool(os.getenv("AUTO_BACKUP_ENABLED"), default=True)
AUTO_BACKUP_HOUR_UTC = int(os.getenv("AUTO_BACKUP_HOUR_UTC", "2"))
ALERT_APPROVAL_RATE_MIN = float(os.getenv("ALERT_APPROVAL_RATE_MIN", "0.3"))
ALERT_CORRECTION_RATE_MAX = float(os.getenv("ALERT_CORRECTION_RATE_MAX", "0.7"))
ALERT_OVERSPENDING_RATE_MAX = float(os.getenv("ALERT_OVERSPENDING_RATE_MAX", "1.1"))
DEV_SEED_DEMO_USERS = parse_bool(os.getenv("DEV_SEED_DEMO_USERS"), default=False)
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)
_last_auto_backup_date: str | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


def to_serializable(value: Any) -> Any:
    if isinstance(value, datetime):
        return value.isoformat()
    return value


def restore_value(value: Any, column_type: Any) -> Any:
    if value is None:
        return None
    if isinstance(column_type, DateTime):
        return datetime.fromisoformat(value)
    return value


def create_database_backup(target: Path) -> None:
    tables: dict[str, list[dict[str, Any]]] = {}
    with SessionLocal() as db:
        for model in [User, Registration, RegistrationAccess, MaterialChecklistItem, MaterialVersion, ReviewRecord, FundingAccount, Transaction, AuditLog, DataCollectionBatch, QualityValidationResult]:
            rows: list[dict[str, Any]] = []
            for item in db.query(model).all():
                rows.append({column.name: to_serializable(getattr(item, column.name)) for column in model.__table__.columns})
            tables[model.__tablename__] = rows
    (target / "database_backup.json").write_text(json.dumps(tables, ensure_ascii=True, indent=2), encoding="utf-8")


def restore_database_backup(source: Path) -> None:
    payload_path = source / "database_backup.json"
    if not payload_path.exists():
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "No database backup found"})
    data = json.loads(payload_path.read_text(encoding="utf-8"))
    model_map = {
        User.__tablename__: User,
        Registration.__tablename__: Registration,
        RegistrationAccess.__tablename__: RegistrationAccess,
        MaterialChecklistItem.__tablename__: MaterialChecklistItem,
        MaterialVersion.__tablename__: MaterialVersion,
        ReviewRecord.__tablename__: ReviewRecord,
        FundingAccount.__tablename__: FundingAccount,
        Transaction.__tablename__: Transaction,
        AuditLog.__tablename__: AuditLog,
        DataCollectionBatch.__tablename__: DataCollectionBatch,
        QualityValidationResult.__tablename__: QualityValidationResult,
    }
    ordered = [QualityValidationResult, DataCollectionBatch, Transaction, FundingAccount, ReviewRecord, MaterialVersion, MaterialChecklistItem, RegistrationAccess, Registration, AuditLog, User]
    with SessionLocal() as db:
        for model in ordered:
            db.query(model).delete()
        for table_name, model in model_map.items():
            for row in data.get(table_name, []):
                values = {}
                for column in model.__table__.columns:
                    values[column.name] = restore_value(row.get(column.name), column.type)
                db.add(model(**values))
        db.commit()


def create_storage_backup(tag: str = "manual") -> str:
    backup_dir = STORAGE_ROOT / "_backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%d%H%M%S")
    target = backup_dir / f"storage_backup_{tag}_{ts}"
    if STORAGE_ROOT.exists():
        # Avoid recursively copying backups into backup snapshots.
        shutil.copytree(STORAGE_ROOT, target, dirs_exist_ok=True, ignore=shutil.ignore_patterns("_backups"))
    return str(target)


def start_daily_backup_worker() -> None:
    def _worker() -> None:
        global _last_auto_backup_date
        while True:
            try:
                now = datetime.now(timezone.utc)
                today = now.date().isoformat()
                if now.hour >= AUTO_BACKUP_HOUR_UTC and _last_auto_backup_date != today:
                    target = Path(create_storage_backup("auto"))
                    create_database_backup(target)
                    _last_auto_backup_date = today
            except Exception as exc:
                # Keep backup worker non-fatal for the API process.
                logger.exception("Daily backup worker failed: %s", exc)
            time.sleep(300)
    threading.Thread(target=_worker, daemon=True).start()


app = FastAPI(title="Activity Registration and Funding Audit Platform")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:3001",
        "http://127.0.0.1:3001",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(bind=engine, autoflush=False, autocommit=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def token_for_user(user_id: int) -> str:
    payload = {"sub": str(user_id), "exp": datetime.now(timezone.utc) + timedelta(hours=1)}
    return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)


def current_user(authorization: str = Header(default=""), db: Session = Depends(get_db)) -> User:
    if not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Missing token"})
    token = authorization.split(" ", 1)[1]
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        user_id = int(payload["sub"])
    except (JWTError, KeyError, ValueError):
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Invalid token"})
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "User not found"})
    return user


def require_roles(*roles: str):
    def checker(user: User = Depends(current_user)) -> User:
        if user.role not in roles:
            raise HTTPException(status_code=403, detail={"code": 403, "msg": "Permission denied"})
        return user
    return checker


def ensure_registration_access(user: User, reg: Registration) -> None:
    if user.role == "Applicant" and reg.applicant_id != user.id:
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "Permission denied"})


def ensure_domain_access(db: Session, user: User, registration_id: int, domain: str) -> None:
    if user.role == "System Administrator":
        return
    allowed = db.query(RegistrationAccess).filter_by(
        registration_id=registration_id,
        user_id=user.id,
        domain=domain,
    ).first()
    if not allowed:
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "Permission denied"})


def masked_sensitive(value: str) -> str:
    if len(value) <= 4:
        return "***"
    return f"{value[:2]}***{value[-2:]}"


def audit_event(db: Session, action: str, detail: str | None = None) -> None:
    db.add(AuditLog(action=action, detail=detail))
    db.commit()


def ensure_default_checklist(db: Session, registration_id: int) -> None:
    required_items = ["proposal", "id_document", "budget_plan"]
    existing = {
        row.material_type
        for row in db.query(MaterialChecklistItem).filter_by(registration_id=registration_id).all()
    }
    for item in required_items:
        if item in existing:
            continue
        db.add(
            MaterialChecklistItem(
                registration_id=registration_id,
                material_type=item,
                status_label="Pending Submission",
            )
        )
    db.commit()


def emit_quality_alerts(db: Session, metrics: dict[str, float]) -> list[str]:
    alerts: list[str] = []
    current_day = datetime.now(timezone.utc).date().isoformat()
    rules = [
        ("approval_rate.low", metrics["approval_rate"] < ALERT_APPROVAL_RATE_MIN, f"approval_rate={metrics['approval_rate']:.4f} threshold={ALERT_APPROVAL_RATE_MIN}"),
        ("correction_rate.high", metrics["correction_rate"] > ALERT_CORRECTION_RATE_MAX, f"correction_rate={metrics['correction_rate']:.4f} threshold={ALERT_CORRECTION_RATE_MAX}"),
        ("overspending_rate.high", metrics["overspending_rate"] > ALERT_OVERSPENDING_RATE_MAX, f"overspending_rate={metrics['overspending_rate']:.4f} threshold={ALERT_OVERSPENDING_RATE_MAX}"),
    ]
    for action, should_emit, detail in rules:
        if not should_emit:
            continue
        existing = db.query(AuditLog).filter_by(action=f"quality.alert.{action}", detail=f"{current_day}|{detail}").first()
        if existing:
            continue
        db.add(AuditLog(action=f"quality.alert.{action}", detail=f"{current_day}|{detail}"))
        alerts.append(action)
    if alerts:
        db.commit()
    return alerts


@app.on_event("startup")
def startup() -> None:
    Base.metadata.create_all(bind=engine)
    db = SessionLocal()
    try:
        # Lightweight schema evolution for existing volumes without Alembic migrations.
        db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS deadline TIMESTAMP WITH TIME ZONE"))
        db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS supplementary_deadline TIMESTAMP WITH TIME ZONE"))
        db.execute(text("ALTER TABLE registrations ADD COLUMN IF NOT EXISTS supplementary_used BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE material_versions ADD COLUMN IF NOT EXISTS needs_correction BOOLEAN DEFAULT FALSE"))
        db.execute(text("ALTER TABLE material_versions ADD COLUMN IF NOT EXISTS correction_reason TEXT"))
        db.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS created_at TIMESTAMP WITH TIME ZONE DEFAULT NOW()"))
        db.execute(text("ALTER TABLE transactions ADD COLUMN IF NOT EXISTS invoice_path VARCHAR(500)"))
        db.commit()
        if not db.query(User).filter(User.username == "admin").first():
            admin_password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD")
            if not admin_password:
                raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD must be configured")
            db.add(User(username="admin", password_hash=pwd_context.hash(admin_password), role="System Administrator"))
            if APP_ENV == "dev" and DEV_SEED_DEMO_USERS:
                reviewer_password = os.getenv("REVIEWER_BOOTSTRAP_PASSWORD")
                finance_password = os.getenv("FINANCE_BOOTSTRAP_PASSWORD")
                applicant_password = os.getenv("APPLICANT_BOOTSTRAP_PASSWORD")
                if not reviewer_password or not finance_password or not applicant_password:
                    raise RuntimeError("Demo user bootstrap passwords must be configured when DEV_SEED_DEMO_USERS is enabled")
                db.add(User(username="reviewer", password_hash=pwd_context.hash(reviewer_password), role="Reviewer"))
                db.add(User(username="finance", password_hash=pwd_context.hash(finance_password), role="Financial Administrator"))
                db.add(User(username="applicant", password_hash=pwd_context.hash(applicant_password), role="Applicant"))
            db.commit()
    finally:
        db.close()
    if AUTO_BACKUP_ENABLED:
        start_daily_backup_worker()


@app.get("/health")
def health() -> dict:
    return {"status": "ok"}


@app.post("/api/auth/login")
def login(data: LoginIn, db: Session = Depends(get_db)) -> dict:
    user = db.query(User).filter(User.username == data.username).first()
    if not user:
        audit_event(db, "auth.login.failed", f"username={data.username}|reason=user_not_found")
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Invalid credentials"})
    now = datetime.now(timezone.utc)
    if user.lock_until and user.lock_until > now:
        audit_event(db, "auth.login.locked", f"user_id={user.id}|lock_until={user.lock_until.isoformat()}")
        raise HTTPException(status_code=423, detail={"code": 423, "msg": "Account is locked"})
    if not user.window_started_at or user.window_started_at + timedelta(minutes=WINDOW_MINUTES) < now:
        user.window_started_at = now
        user.failed_attempts = 0
    if not pwd_context.verify(data.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_ATTEMPTS:
            user.lock_until = now + timedelta(minutes=LOCK_MINUTES)
        db.commit()
        audit_event(db, "auth.login.failed", f"user_id={user.id}|failed_attempts={user.failed_attempts}")
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Invalid credentials"})
    user.failed_attempts = 0
    user.lock_until = None
    db.commit()
    audit_event(db, "auth.login.success", f"user_id={user.id}")
    return {"access_token": token_for_user(user.id)}


@app.post("/api/registrations")
def create_registration(data: RegistrationIn, db: Session = Depends(get_db), user: User = Depends(require_roles("Applicant", "System Administrator"))) -> dict:
    reg = Registration(
        applicant_id=user.id,
        title=data.title,
        id_number=data.id_number,
        contact=data.contact,
        status="Submitted",
        supplementary_used=False,
    )
    db.add(reg)
    db.commit()
    db.refresh(reg)
    ensure_default_checklist(db, reg.id)
    audit_event(db, "registration.create", f"user_id={user.id}|registration_id={reg.id}")
    return {"id": reg.id}


@app.get("/api/registrations/{registration_id}")
def get_registration(registration_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    id_number = reg.id_number
    contact = reg.contact
    if user.role != "System Administrator" and reg.applicant_id != user.id:
        id_number = masked_sensitive(id_number)
        contact = masked_sensitive(contact)
    return {"id": reg.id, "title": reg.title, "status": reg.status, "id_number": id_number, "contact": contact}


@app.post("/api/materials/upload")
def upload_material(
    registration_id: int,
    material_type: str,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Applicant", "System Administrator")),
) -> dict:
    return _upload_material_core(
        registration_id=registration_id,
        material_type=material_type,
        upload=upload,
        db=db,
        user=user,
        enforce_deadline=True,
    )


def _upload_material_core(
    registration_id: int,
    material_type: str,
    upload: UploadFile,
    db: Session,
    user: User,
    enforce_deadline: bool,
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    ensure_default_checklist(db, registration_id)
    checklist_item = db.query(MaterialChecklistItem).filter_by(
        registration_id=registration_id,
        material_type=material_type,
    ).first()
    if not checklist_item:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Material type is not in checklist"})
    if enforce_deadline and reg.deadline and datetime.now(timezone.utc) > reg.deadline:
        raise HTTPException(status_code=423, detail={"code": 423, "msg": "Materials are locked after deadline"})
    ext = (upload.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "jpg", "jpeg", "png"}:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Invalid file type"})
    content = upload.file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Single file exceeds 20MB"})
    total = sum(x.file_size for x in db.query(MaterialVersion).filter_by(registration_id=registration_id, is_deleted=False).all())
    if total + len(content) > 200 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Total files exceed 200MB"})
    digest = sha256(content).hexdigest()
    if db.query(MaterialVersion).filter_by(registration_id=registration_id, file_hash=digest, is_deleted=False).first():
        raise HTTPException(status_code=409, detail={"code": 409, "msg": "Duplicate file for this activity"})

    folder = STORAGE_ROOT / str(registration_id) / material_type
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{digest}_{upload.filename}"
    file_path.write_bytes(content)

    history = db.query(MaterialVersion).filter_by(registration_id=registration_id, material_type=material_type, is_deleted=False).order_by(MaterialVersion.version_no.desc()).all()
    version_no = history[0].version_no + 1 if history else 1
    if len(history) >= 3:
        history[-1].is_deleted = True
    mv = MaterialVersion(
        registration_id=registration_id,
        material_type=material_type,
        version_no=version_no,
        file_name=upload.filename or "unknown",
        file_hash=digest,
        file_size=len(content),
        file_path=str(file_path),
        status_label="Submitted",
    )
    db.add(mv)
    checklist_item.status_label = "Submitted"
    checklist_item.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mv)
    audit_event(db, "material.upload", f"user_id={user.id}|registration_id={registration_id}|material_id={mv.id}|version={mv.version_no}")
    return {"id": mv.id, "version_no": mv.version_no}


@app.post("/api/registrations/{registration_id}/deadline")
def set_deadline(
    registration_id: int,
    data: DeadlineIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    try:
        reg.deadline = datetime.fromisoformat(data.deadline_iso.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Invalid datetime format"})
    db.commit()
    audit_event(db, "registration.deadline.set", f"registration_id={reg.id}|deadline={reg.deadline.isoformat()}")
    return {"id": reg.id, "deadline": reg.deadline.isoformat()}


@app.post("/api/materials/{material_id}/mark-correction")
def mark_material_for_correction(
    material_id: int,
    data: CorrectionIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Reviewer", "System Administrator")),
) -> dict:
    material = db.query(MaterialVersion).filter_by(id=material_id, is_deleted=False).first()
    if not material:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Material not found"})
    material.needs_correction = True
    material.correction_reason = data.reason
    material.status_label = "Needs Correction"
    checklist_item = db.query(MaterialChecklistItem).filter_by(
        registration_id=material.registration_id,
        material_type=material.material_type,
    ).first()
    if checklist_item:
        checklist_item.status_label = "Needs Correction"
        checklist_item.updated_at = datetime.now(timezone.utc)
    db.commit()
    audit_event(db, "material.mark_correction", f"material_id={material.id}|reason={data.reason}")
    return {"id": material.id, "status_label": material.status_label}


@app.post("/api/registrations/{registration_id}/supplementary/start")
def start_supplementary(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Applicant", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    if reg.supplementary_used:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Supplementary submission already used"})
    reg.supplementary_used = True
    reg.supplementary_deadline = datetime.now(timezone.utc) + timedelta(hours=72)
    reg.status = "Supplemented"
    db.commit()
    audit_event(db, "registration.supplementary.start", f"user_id={user.id}|registration_id={reg.id}|deadline={reg.supplementary_deadline.isoformat()}")
    return {"registration_id": reg.id, "supplementary_deadline": reg.supplementary_deadline.isoformat()}


@app.post("/api/materials/{material_id}/supplementary-upload")
def supplementary_upload(
    material_id: int,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Applicant", "System Administrator")),
) -> dict:
    old = db.query(MaterialVersion).filter_by(id=material_id, is_deleted=False).first()
    if not old:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Material not found"})
    reg = db.query(Registration).filter_by(id=old.registration_id).first()
    if reg:
        ensure_registration_access(user, reg)
    now = datetime.now(timezone.utc)
    if not reg or not reg.supplementary_deadline or now > reg.supplementary_deadline:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Supplementary window closed"})
    if not old.needs_correction:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Only materials marked for correction can be replaced"})

    return _upload_material_core(
        registration_id=old.registration_id,
        material_type=old.material_type,
        upload=upload,
        db=db,
        user=user,
        enforce_deadline=False,
    )


@app.get("/api/materials/checklist/{registration_id}")
def get_material_checklist(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    ensure_default_checklist(db, registration_id)
    rows = db.query(MaterialChecklistItem).filter_by(registration_id=registration_id).order_by(MaterialChecklistItem.id.asc()).all()
    items = [{"material_type": row.material_type, "status_label": row.status_label} for row in rows]
    return {"registration_id": registration_id, "items": items}


@app.get("/api/materials/usage/{registration_id}")
def get_material_usage(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    total = sum(x.file_size for x in db.query(MaterialVersion).filter_by(registration_id=registration_id, is_deleted=False).all())
    return {"registration_id": registration_id, "total_size_bytes": total, "max_total_size_bytes": 200 * 1024 * 1024}


@app.post("/api/reviews/batch")
def review_batch(
    data: BatchReviewIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Reviewer", "System Administrator")),
) -> dict:
    if len(data.items) > 50:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Batch limit is 50"})
    allowed = {
        "Submitted": {"Supplemented", "Approved", "Rejected", "Canceled"},
        "Supplemented": {"Approved", "Rejected", "Canceled"},
        "Rejected": {"Promoted from Waitlist", "Canceled"},
    }
    results = []
    for item in data.items:
        reg = db.query(Registration).filter_by(id=item.registration_id).first()
        if not reg:
            results.append({"registration_id": item.registration_id, "ok": False, "error": "Not found"})
            continue
        if user.role == "Reviewer":
            try:
                ensure_domain_access(db, user, reg.id, "review")
            except HTTPException:
                results.append({"registration_id": reg.id, "ok": False, "error": "Permission denied"})
                continue
        if item.to_state not in allowed.get(reg.status, set()):
            results.append({"registration_id": item.registration_id, "ok": False, "error": "Invalid transition"})
            continue
        old = reg.status
        reg.status = item.to_state
        db.add(ReviewRecord(registration_id=reg.id, reviewer_id=user.id, from_state=old, to_state=reg.status, comment=item.comment))
        results.append({"registration_id": reg.id, "ok": True})
    db.commit()
    audit_event(db, "review.batch", f"user_id={user.id}|items={len(data.items)}|accepted={sum(1 for item in results if item['ok'])}")
    return {"results": results}


@app.get("/api/reviews/queue")
def review_queue(
    status: str | None = None,
    page: int = 1,
    page_size: int = 20,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Reviewer", "System Administrator")),
) -> dict:
    page = max(page, 1)
    page_size = max(1, min(page_size, 50))
    q = db.query(Registration)
    if _user.role == "Reviewer":
        assigned_ids = [
            row.registration_id
            for row in db.query(RegistrationAccess).filter_by(user_id=_user.id, domain="review").all()
        ]
        if not assigned_ids:
            return {"total": 0, "page": page, "page_size": page_size, "items": []}
        q = q.filter(Registration.id.in_(assigned_ids))
    if status:
        q = q.filter(Registration.status == status)
    total = q.count()
    rows = q.order_by(Registration.id.desc()).offset((page - 1) * page_size).limit(page_size).all()
    items = [{"registration_id": row.id, "title": row.title, "status": row.status, "created_at": row.created_at.isoformat()} for row in rows]
    return {"total": total, "page": page, "page_size": page_size, "items": items}


@app.get("/api/reviews/logs/{registration_id}")
def get_review_logs(registration_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    if user.role not in {"Applicant", "Reviewer", "System Administrator"}:
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "Permission denied"})
    ensure_registration_access(user, reg)
    if user.role == "Reviewer":
        ensure_domain_access(db, user, reg.id, "review")
    rows = db.query(ReviewRecord).filter_by(registration_id=registration_id).all()
    return {"logs": [{"from": r.from_state, "to": r.to_state, "comment": r.comment} for r in rows]}


@app.post("/api/transactions")
def create_transaction(
    data: TransactionIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=data.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    if user.role == "Financial Administrator":
        ensure_domain_access(db, user, reg.id, "finance")
    account = db.query(FundingAccount).filter_by(registration_id=data.registration_id).first()
    if not account or float(account.budget) <= 0:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Budget must be configured before transactions"})
    expense = float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter_by(registration_id=data.registration_id, tx_type="expense").scalar() or 0)
    projected = expense + data.amount if data.tx_type == "expense" else expense
    if float(account.budget) > 0 and projected > float(account.budget) * 1.1 and not data.secondary_confirmation:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Expenses exceed budget by 10%; secondary confirmation required"})
    tx = Transaction(registration_id=data.registration_id, tx_type=data.tx_type, category=data.category, amount=data.amount)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    audit_event(db, "finance.transaction.create", f"registration_id={data.registration_id}|transaction_id={tx.id}|type={data.tx_type}|amount={data.amount}")
    return {"id": tx.id}


@app.get("/api/funding/{registration_id}")
def get_budget(
    registration_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    if user.role == "Financial Administrator":
        ensure_domain_access(db, user, reg.id, "finance")
    account = db.query(FundingAccount).filter_by(registration_id=registration_id).first()
    return {"registration_id": registration_id, "budget": float(account.budget) if account else 0.0}


@app.post("/api/funding/{registration_id}/budget")
def set_budget(
    registration_id: int,
    data: BudgetUpdateIn,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    if user.role == "Financial Administrator":
        ensure_domain_access(db, user, reg.id, "finance")
    account = db.query(FundingAccount).filter_by(registration_id=registration_id).first()
    if not account:
        account = FundingAccount(registration_id=registration_id, budget=data.budget)
        db.add(account)
    else:
        account.budget = data.budget
    db.commit()
    audit_event(db, "finance.budget.set", f"user_id={user.id}|registration_id={registration_id}|budget={data.budget}")
    return {"registration_id": registration_id, "budget": float(data.budget)}


@app.post("/api/transactions/{transaction_id}/invoice")
def upload_invoice(
    transaction_id: int,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    tx = db.query(Transaction).filter_by(id=transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Transaction not found"})
    if user.role == "Financial Administrator":
        ensure_domain_access(db, user, tx.registration_id, "finance")
    ext = (upload.filename or "").rsplit(".", 1)[-1].lower()
    if ext not in {"pdf", "jpg", "jpeg", "png"}:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Invalid file type"})
    content = upload.file.read()
    if len(content) > 20 * 1024 * 1024:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Single file exceeds 20MB"})
    digest = sha256(content).hexdigest()
    folder = STORAGE_ROOT / str(tx.registration_id) / "invoices"
    folder.mkdir(parents=True, exist_ok=True)
    file_path = folder / f"{tx.id}_{digest}_{upload.filename}"
    file_path.write_bytes(content)
    tx.invoice_path = str(file_path)
    db.commit()
    audit_event(db, "finance.invoice.upload", f"transaction_id={tx.id}|path={tx.invoice_path}")
    return {"transaction_id": tx.id, "invoice_path": tx.invoice_path}


@app.get("/api/transactions/stats")
def transaction_stats(
    registration_id: int,
    start_iso: str | None = None,
    end_iso: str | None = None,
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    if user.role == "Financial Administrator":
        ensure_domain_access(db, user, reg.id, "finance")
    q = db.query(
        Transaction.category.label("category"),
        func.coalesce(func.sum(Transaction.amount), 0).label("total_amount"),
        func.count(Transaction.id).label("count"),
    ).filter(Transaction.registration_id == registration_id)
    if start_iso:
        try:
            start_dt = datetime.fromisoformat(start_iso.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": 400, "msg": "Invalid start_iso"})
        q = q.filter(Transaction.created_at >= start_dt)
    if end_iso:
        try:
            end_dt = datetime.fromisoformat(end_iso.replace("Z", "+00:00"))
        except ValueError:
            raise HTTPException(status_code=400, detail={"code": 400, "msg": "Invalid end_iso"})
        q = q.filter(Transaction.created_at <= end_dt)
    rows = q.group_by(Transaction.category).all()
    stats = [{"category": row.category, "total_amount": float(row.total_amount), "count": int(row.count)} for row in rows]
    return {"registration_id": registration_id, "stats": stats}


@app.get("/api/reports/summary")
def reports_summary(
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Reviewer", "Financial Administrator", "System Administrator")),
) -> dict:
    total = db.query(Registration).count()
    approved = db.query(Registration).filter_by(status="Approved").count()
    corrected = db.query(Registration).filter_by(status="Supplemented").count()
    total_expense = float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter_by(tx_type="expense").scalar() or 0)
    total_budget = float(db.query(func.coalesce(func.sum(FundingAccount.budget), 0)).scalar() or 0)
    payload = {
        "approval_rate": (approved / total) if total else 0,
        "correction_rate": (corrected / total) if total else 0,
        "overspending_rate": (total_expense / total_budget) if total_budget else 0,
    }
    if total:
        first_reg = db.query(Registration).order_by(Registration.id.asc()).first()
        if first_reg:
            q = QualityValidationResult(
                registration_id=first_reg.id,
                approval_rate=payload["approval_rate"],
                correction_rate=payload["correction_rate"],
                overspending_rate=payload["overspending_rate"],
            )
            db.add(q)
            db.commit()
    alerts = emit_quality_alerts(db, payload)
    if alerts:
        audit_event(db, "quality.alert.emit", f"alerts={','.join(alerts)}")
    return payload


@app.get("/api/reports/{report_type}/export")
def export_report(
    report_type: str,
    format: str = "csv",
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Reviewer", "Financial Administrator", "System Administrator")),
):
    if report_type not in {"audit", "compliance", "reconciliation"}:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Unsupported report type"})
    logs = db.query(AuditLog).all()
    if format == "csv":
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(["action", "detail"])
        for row in logs:
            writer.writerow([row.action, row.detail or ""])
        output.seek(0)
        return StreamingResponse(iter([output.getvalue()]), media_type="text/csv", headers={"Content-Disposition": f"attachment; filename={report_type}.csv"})
    if format == "pdf":
        pdf = FPDF()
        pdf.set_auto_page_break(auto=True, margin=15)
        pdf.add_page()
        pdf.set_font("Helvetica", style="B", size=14)
        pdf.cell(0, 10, f"{report_type.upper()} REPORT", ln=True)
        pdf.set_font("Helvetica", size=11)
        pdf.cell(0, 8, f"Generated: {datetime.now(timezone.utc).isoformat()}", ln=True)
        pdf.cell(0, 8, f"Rows: {len(logs)}", ln=True)
        pdf.ln(4)
        effective_width = pdf.w - pdf.l_margin - pdf.r_margin
        for idx, row in enumerate(logs, start=1):
            detail = (row.detail or "").replace("\n", " ").strip()
            line = f"{idx}. {row.action} - {detail}" if detail else f"{idx}. {row.action}"
            # Keep cursor at left margin to avoid zero-width rendering failures.
            pdf.set_x(pdf.l_margin)
            pdf.multi_cell(effective_width, 7, line)
        pdf_payload = pdf.output(dest="S")
        if isinstance(pdf_payload, bytearray):
            pdf_bytes = bytes(pdf_payload)
        elif isinstance(pdf_payload, str):
            pdf_bytes = pdf_payload.encode("latin-1")
        else:
            pdf_bytes = pdf_payload
        return StreamingResponse(iter([pdf_bytes]), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename={report_type}.pdf"})
    raise HTTPException(status_code=400, detail={"code": 400, "msg": "Unsupported format"})


@app.get("/api/similarity-check")
def similarity_check(_user: User = Depends(require_roles("System Administrator"))) -> dict:
    if not SIMILARITY_CHECK_ENABLED:
        raise HTTPException(status_code=403, detail={"code": 403, "msg": "Feature disabled"})
    return {"status": "enabled"}


@app.get("/api/whitelist-policies/export")
def whitelist_export(_user: User = Depends(require_roles("System Administrator"))) -> dict:
    return {
        "policies": [
            {"scope": "activity", "rule": "Allow only approved data collection templates"},
            {"scope": "field", "rule": "Sensitive personal fields require privileged role"},
        ]
    }


@app.post("/api/batches")
def create_batch(data: BatchIn, db: Session = Depends(get_db), _user: User = Depends(require_roles("System Administrator"))) -> dict:
    reg = db.query(Registration).filter_by(id=data.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    batch = DataCollectionBatch(registration_id=data.registration_id, batch_name=data.batch_name, whitelist_scope=data.whitelist_scope)
    db.add(batch)
    db.commit()
    db.refresh(batch)
    audit_event(db, "batch.create", f"registration_id={data.registration_id}|batch_id={batch.id}|scope={data.whitelist_scope}")
    return {"id": batch.id}


@app.post("/api/access/assign")
def assign_registration_access(
    data: AccessAssignIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=data.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    target = db.query(User).filter_by(username=data.username).first()
    if not target:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "User not found"})
    expected_role = "Reviewer" if data.domain == "review" else "Financial Administrator"
    if target.role != expected_role:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Target user role does not match access domain"})
    existing = db.query(RegistrationAccess).filter_by(
        registration_id=data.registration_id,
        user_id=target.id,
        domain=data.domain,
    ).first()
    if existing:
        return {"registration_id": data.registration_id, "username": target.username, "domain": data.domain, "assigned": False}
    db.add(RegistrationAccess(registration_id=data.registration_id, user_id=target.id, domain=data.domain))
    db.commit()
    audit_event(db, "access.assign", f"registration_id={data.registration_id}|user_id={target.id}|domain={data.domain}")
    return {"registration_id": data.registration_id, "username": target.username, "domain": data.domain, "assigned": True}


@app.post("/api/system/backup")
def create_backup(_user: User = Depends(require_roles("System Administrator"))) -> dict:
    target = create_storage_backup("manual")
    backup_path = Path(target)
    create_database_backup(backup_path)
    with SessionLocal() as db:
        audit_event(db, "system.backup.create", f"path={target}")
    return {"backup_path": target, "database_backup": str(backup_path / "database_backup.json")}


@app.post("/api/system/recovery")
def one_click_recovery(_user: User = Depends(require_roles("System Administrator"))) -> dict:
    backup_dir = STORAGE_ROOT / "_backups"
    if not backup_dir.exists():
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "No backup found"})
    candidates = sorted(backup_dir.glob("storage_backup_*"), reverse=True)
    if not candidates:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "No backup found"})
    latest = candidates[0]
    restored = STORAGE_ROOT / "_restored_latest"
    shutil.copytree(latest, restored, dirs_exist_ok=True)
    STORAGE_ROOT.mkdir(parents=True, exist_ok=True)
    for item in STORAGE_ROOT.iterdir():
        if item.name in {"_backups", "_restored_latest"}:
            continue
        if item.is_dir():
            shutil.rmtree(item)
        else:
            item.unlink()
    for item in latest.iterdir():
        if item.name in {"database_backup.json", "_backups"}:
            continue
        target = STORAGE_ROOT / item.name
        if item.is_dir():
            shutil.copytree(item, target, dirs_exist_ok=True)
        else:
            shutil.copy2(item, target)
    restore_database_backup(latest)
    with SessionLocal() as db:
        audit_event(db, "system.recovery.run", f"source={latest}|target={restored}")
    return {"restored_from": str(latest), "restored_to": str(restored), "database_restored": True}
