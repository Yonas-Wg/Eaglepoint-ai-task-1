import csv
import io
import os
import shutil
import threading
import time
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path

from fastapi import Depends, FastAPI, File, Header, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fpdf import FPDF
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, create_engine, func, text
from sqlalchemy.orm import DeclarativeBase, Mapped, Session, mapped_column, sessionmaker


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
    raw_secret = os.getenv("SECRET_KEY", "super_secret_change_me")
    encryption_key = os.getenv("CONFIG_ENCRYPTION_KEY")
    return decrypt_config_value(raw_secret, encryption_key)


SECRET_KEY = load_secret_key()
ALGORITHM = "HS256"
MAX_ATTEMPTS = 10
LOCK_MINUTES = 30
WINDOW_MINUTES = 5
APP_ENV = os.getenv("APP_ENV", "dev").strip().lower()
SIMILARITY_CHECK_ENABLED = parse_bool(os.getenv("SIMILARITY_CHECK_ENABLED"), default=False)
STORAGE_ROOT = Path(os.getenv("STORAGE_ROOT", "/app/storage"))
AUTO_BACKUP_ENABLED = parse_bool(os.getenv("AUTO_BACKUP_ENABLED"), default=True)
AUTO_BACKUP_HOUR_UTC = int(os.getenv("AUTO_BACKUP_HOUR_UTC", "2"))
_last_auto_backup_date: str | None = None

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class Base(DeclarativeBase):
    pass


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
                    create_storage_backup("auto")
                    _last_auto_backup_date = today
            except Exception:
                # Keep backup worker non-fatal for the API process.
                pass
            time.sleep(300)
    threading.Thread(target=_worker, daemon=True).start()


class User(Base):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(64), nullable=False)
    failed_attempts: Mapped[int] = mapped_column(Integer, default=0)
    window_started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    lock_until: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Registration(Base):
    __tablename__ = "registrations"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    applicant_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    title: Mapped[str] = mapped_column(String(200), nullable=False)
    id_number: Mapped[str] = mapped_column(String(64), nullable=False)
    contact: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[str] = mapped_column(String(32), default="Submitted")
    deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supplementary_deadline: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    supplementary_used: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MaterialVersion(Base):
    __tablename__ = "material_versions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    material_type: Mapped[str] = mapped_column(String(64), nullable=False)
    version_no: Mapped[int] = mapped_column(Integer, nullable=False)
    file_name: Mapped[str] = mapped_column(String(255), nullable=False)
    file_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    file_path: Mapped[str] = mapped_column(String(500), nullable=False)
    status_label: Mapped[str] = mapped_column(String(32), default="Submitted")
    needs_correction: Mapped[bool] = mapped_column(Boolean, default=False)
    correction_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_deleted: Mapped[bool] = mapped_column(Boolean, default=False)


class ReviewRecord(Base):
    __tablename__ = "review_records"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    reviewer_id: Mapped[int] = mapped_column(ForeignKey("users.id"), nullable=False)
    from_state: Mapped[str] = mapped_column(String(32), nullable=False)
    to_state: Mapped[str] = mapped_column(String(32), nullable=False)
    comment: Mapped[str | None] = mapped_column(Text, nullable=True)


class FundingAccount(Base):
    __tablename__ = "funding_accounts"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False, unique=True)
    budget: Mapped[float] = mapped_column(Numeric(12, 2), default=0)


class Transaction(Base):
    __tablename__ = "transactions"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    tx_type: Mapped[str] = mapped_column(String(16), nullable=False)
    category: Mapped[str] = mapped_column(String(64), nullable=False)
    amount: Mapped[float] = mapped_column(Numeric(12, 2), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    invoice_path: Mapped[str | None] = mapped_column(String(500), nullable=True)


class AuditLog(Base):
    __tablename__ = "audit_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    action: Mapped[str] = mapped_column(String(120), nullable=False)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)


class DataCollectionBatch(Base):
    __tablename__ = "data_collection_batches"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    batch_name: Mapped[str] = mapped_column(String(128), nullable=False)
    whitelist_scope: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QualityValidationResult(Base):
    __tablename__ = "quality_validation_results"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    registration_id: Mapped[int] = mapped_column(ForeignKey("registrations.id"), nullable=False)
    approval_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    correction_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    overspending_rate: Mapped[float] = mapped_column(Numeric(6, 4), default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class LoginIn(BaseModel):
    username: str
    password: str


class RegistrationIn(BaseModel):
    title: str
    id_number: str
    contact: str


class ReviewItem(BaseModel):
    registration_id: int
    to_state: str
    comment: str | None = None


class BatchReviewIn(BaseModel):
    items: list[ReviewItem]


class TransactionIn(BaseModel):
    registration_id: int
    tx_type: str
    category: str
    amount: float
    secondary_confirmation: bool = False


class DeadlineIn(BaseModel):
    deadline_iso: str


class CorrectionIn(BaseModel):
    reason: str


class BatchIn(BaseModel):
    registration_id: int
    batch_name: str
    whitelist_scope: str


class TransactionStatsOut(BaseModel):
    category: str
    total_amount: float
    count: int


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
engine = create_engine("postgresql+psycopg2://postgres:postgres@db:5432/activity_audit", pool_pre_ping=True)
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


@app.on_event("startup")
def startup() -> None:
    if APP_ENV != "dev" and SECRET_KEY == "super_secret_change_me":
        raise RuntimeError("SECRET_KEY must be configured outside dev environment")
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
            admin_password = os.getenv("ADMIN_BOOTSTRAP_PASSWORD", "admin123")
            if APP_ENV != "dev" and admin_password == "admin123":
                raise RuntimeError("ADMIN_BOOTSTRAP_PASSWORD must be configured outside dev environment")
            db.add(User(username="admin", password_hash=pwd_context.hash(admin_password), role="System Administrator"))
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
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Invalid credentials"})
    now = datetime.now(timezone.utc)
    if user.lock_until and user.lock_until > now:
        raise HTTPException(status_code=423, detail={"code": 423, "msg": "Account is locked"})
    if not user.window_started_at or user.window_started_at + timedelta(minutes=WINDOW_MINUTES) < now:
        user.window_started_at = now
        user.failed_attempts = 0
    if not pwd_context.verify(data.password, user.password_hash):
        user.failed_attempts += 1
        if user.failed_attempts >= MAX_ATTEMPTS:
            user.lock_until = now + timedelta(minutes=LOCK_MINUTES)
        db.commit()
        raise HTTPException(status_code=401, detail={"code": 401, "msg": "Invalid credentials"})
    user.failed_attempts = 0
    user.lock_until = None
    db.commit()
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
    db.add(AuditLog(action="registration.create", detail=f"{user.id}:{reg.id}"))
    db.commit()
    return {"id": reg.id}


@app.get("/api/registrations/{registration_id}")
def get_registration(registration_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    reg = db.query(Registration).filter(Registration.id == registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    id_number = reg.id_number
    contact = reg.contact
    if user.role == "Reviewer":
        id_number = f"{id_number[:2]}***{id_number[-2:]}"
        contact = f"{contact[:2]}***{contact[-2:]}"
    return {"id": reg.id, "title": reg.title, "status": reg.status, "id_number": id_number, "contact": contact}


@app.post("/api/materials/upload")
def upload_material(
    registration_id: int,
    material_type: str,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    user: User = Depends(require_roles("Applicant", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    if reg.deadline and datetime.now(timezone.utc) > reg.deadline:
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
    db.commit()
    db.refresh(mv)
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
    db.commit()
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

    return upload_material(registration_id=old.registration_id, material_type=old.material_type, upload=upload, db=db, user=user)


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
        if item.to_state not in allowed.get(reg.status, set()):
            results.append({"registration_id": item.registration_id, "ok": False, "error": "Invalid transition"})
            continue
        old = reg.status
        reg.status = item.to_state
        db.add(ReviewRecord(registration_id=reg.id, reviewer_id=user.id, from_state=old, to_state=reg.status, comment=item.comment))
        results.append({"registration_id": reg.id, "ok": True})
    db.commit()
    return {"results": results}


@app.get("/api/reviews/logs/{registration_id}")
def get_review_logs(registration_id: int, db: Session = Depends(get_db), user: User = Depends(current_user)) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    ensure_registration_access(user, reg)
    rows = db.query(ReviewRecord).filter_by(registration_id=registration_id).all()
    return {"logs": [{"from": r.from_state, "to": r.to_state, "comment": r.comment} for r in rows]}


@app.post("/api/transactions")
def create_transaction(
    data: TransactionIn,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=data.registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
    account = db.query(FundingAccount).filter_by(registration_id=data.registration_id).first()
    if not account:
        account = FundingAccount(registration_id=data.registration_id, budget=0)
        db.add(account)
        db.commit()
        db.refresh(account)
    expense = float(db.query(func.coalesce(func.sum(Transaction.amount), 0)).filter_by(registration_id=data.registration_id, tx_type="expense").scalar() or 0)
    projected = expense + data.amount if data.tx_type == "expense" else expense
    if float(account.budget) > 0 and projected > float(account.budget) * 1.1 and not data.secondary_confirmation:
        raise HTTPException(status_code=400, detail={"code": 400, "msg": "Expenses exceed budget by 10%; secondary confirmation required"})
    tx = Transaction(registration_id=data.registration_id, tx_type=data.tx_type, category=data.category, amount=data.amount)
    db.add(tx)
    db.commit()
    db.refresh(tx)
    return {"id": tx.id}


@app.post("/api/transactions/{transaction_id}/invoice")
def upload_invoice(
    transaction_id: int,
    upload: UploadFile = File(...),
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    tx = db.query(Transaction).filter_by(id=transaction_id).first()
    if not tx:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Transaction not found"})
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
    return {"transaction_id": tx.id, "invoice_path": tx.invoice_path}


@app.get("/api/transactions/stats")
def transaction_stats(
    registration_id: int,
    start_iso: str | None = None,
    end_iso: str | None = None,
    db: Session = Depends(get_db),
    _user: User = Depends(require_roles("Financial Administrator", "System Administrator")),
) -> dict:
    reg = db.query(Registration).filter_by(id=registration_id).first()
    if not reg:
        raise HTTPException(status_code=404, detail={"code": 404, "msg": "Registration not found"})
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
def reports_summary(db: Session = Depends(get_db), _user: User = Depends(current_user)) -> dict:
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
    return payload


@app.get("/api/reports/{report_type}/export")
def export_report(report_type: str, format: str = "csv", db: Session = Depends(get_db), _user: User = Depends(current_user)):
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
    return {"id": batch.id}


@app.post("/api/system/backup")
def create_backup(_user: User = Depends(require_roles("System Administrator"))) -> dict:
    target = create_storage_backup("manual")
    return {"backup_path": target}


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
    return {"restored_from": str(latest), "restored_to": str(restored)}
