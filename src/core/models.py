"""Domain models for job application agent using Pydantic."""

from typing import List, Dict, Any, Optional
from pydantic import BaseModel, Field
import hashlib
from datetime import datetime


class Job(BaseModel):
    """Represents a job posting."""
    job_id: Optional[str] = Field(default=None, description="Unique identifier for the job")
    title: str = Field(..., description="Job title")
    company: str = Field(..., description="Company name")
    location: str = Field(default="Unspecified", description="Job location")
    work_type: str = Field(default="Unspecified", description="Remote, Hybrid, On-site, or Unspecified")
    description: str = Field(..., description="Full text description of the job posting")
    url: str = Field(..., description="URL to the job posting")
    source: str = Field(default="unknown", description="Source provider or board")
    posted_date: Optional[str] = Field(default=None, description="Posting date string")

    def model_post_init(self, __context: Any) -> None:
        """Generate unique job_id if not provided."""
        if not self.job_id:
            raw_id = f"{self.company.lower().strip()}_{self.title.lower().strip()}_{self.url.strip()}"
            self.job_id = hashlib.md5(raw_id.encode("utf-8")).hexdigest()[:12]


class Profile(BaseModel):
    """User profile containing candidate background, skills, and preferences."""
    name: str
    contact: Dict[str, str] = Field(default_factory=dict)
    education: List[Dict[str, Any]] = Field(default_factory=list)
    skills: List[str] = Field(default_factory=list)
    projects: List[Dict[str, Any]] = Field(default_factory=list)
    experience: List[Dict[str, Any]] = Field(default_factory=list)
    preferences: Dict[str, Any] = Field(default_factory=dict)


class ResumeVersion(BaseModel):
    """Tailored version of the resume for a specific job."""
    job_id: str
    text: str
    keywords: List[str] = Field(default_factory=list)
    score: float = Field(..., ge=0.0, le=1.0, description="Match score between 0.0 and 1.0")


class CoverLetter(BaseModel):
    """Job-tailored cover letter."""
    job_id: str
    text: str
    tone: str = "professional"
    length_words: int = Field(..., description="Word count of cover letter text")


class ApplicationLog(BaseModel):
    """Log entry tracking application status and follow-ups."""
    job_id: str
    status: str = Field(..., description="prepared, submitted, or error")
    submitted_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    notes: str = ""
    follow_up_date: Optional[str] = None


class FormSubmissionPayload(BaseModel):
    """Mapped fields for job portal form submission."""
    job_id: str
    first_name: str
    last_name: str
    email: str
    phone: str
    linkedin_url: str
    github_url: str
    portfolio_url: str
    resume_text: str
    cover_letter_text: str
    custom_fields: Dict[str, Any] = Field(default_factory=dict)


class WorkflowJobResult(BaseModel):
    """Structured JSON output for a processed job application."""
    job: Dict[str, str]
    match_reason: str
    required_skills: List[str]
    resume_version: Dict[str, Any]
    cover_letter: Dict[str, Any]
    application: Dict[str, str]
