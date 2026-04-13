from typing import Literal

from pydantic import BaseModel, Field, field_validator


class LoginIn(BaseModel):
    username: str
    password: str


class RegistrationIn(BaseModel):
    title: str = Field(min_length=1, max_length=200)
    id_number: str = Field(min_length=1, max_length=64)
    contact: str = Field(min_length=1, max_length=128)

    @field_validator("title", "id_number", "contact")
    @classmethod
    def reject_blank_values(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class ReviewItem(BaseModel):
    registration_id: int
    to_state: Literal["Supplemented", "Approved", "Rejected", "Canceled", "Promoted from Waitlist"]
    comment: str | None = Field(default=None, max_length=2000)


class BatchReviewIn(BaseModel):
    items: list[ReviewItem]


class TransactionIn(BaseModel):
    registration_id: int
    tx_type: Literal["income", "expense"]
    category: str = Field(min_length=1, max_length=64)
    amount: float = Field(gt=0)
    secondary_confirmation: bool = False

    @field_validator("category")
    @classmethod
    def reject_blank_category(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class DeadlineIn(BaseModel):
    deadline_iso: str = Field(min_length=1, max_length=64)


class CorrectionIn(BaseModel):
    reason: str = Field(min_length=1, max_length=500)

    @field_validator("reason")
    @classmethod
    def reject_blank_reason(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BatchIn(BaseModel):
    registration_id: int
    batch_name: str = Field(min_length=1, max_length=128)
    whitelist_scope: str = Field(min_length=1, max_length=128)

    @field_validator("batch_name", "whitelist_scope")
    @classmethod
    def reject_blank_batch_fields(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value


class BudgetUpdateIn(BaseModel):
    budget: float = Field(gt=0)


class AccessAssignIn(BaseModel):
    registration_id: int
    username: str = Field(min_length=1, max_length=64)
    domain: Literal["review", "finance"]

    @field_validator("username")
    @classmethod
    def normalize_username(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("must not be blank")
        return value
