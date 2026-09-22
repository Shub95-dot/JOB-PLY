"""Map resume, cover letter, and candidate profile to standard job application form fields."""

from src.core.models import Profile, Job, ResumeVersion, CoverLetter, FormSubmissionPayload
from src.core.utils import setup_logger

logger = setup_logger("form_filler")


class FormFiller:
    """Prepares structured form submission payload mapping candidate details to application fields."""

    def build_submission_payload(
        self,
        profile: Profile,
        job: Job,
        resume: ResumeVersion,
        cover_letter: CoverLetter
    ) -> FormSubmissionPayload:
        """Map candidate profile, tailored resume, and cover letter into form submission payload."""
        names = profile.name.strip().split(" ", 1)
        first_name = names[0]
        last_name = names[1] if len(names) > 1 else ""

        payload = FormSubmissionPayload(
            job_id=job.job_id or "job_default",
            first_name=first_name,
            last_name=last_name,
            email=profile.contact.get("email", ""),
            phone=profile.contact.get("phone", ""),
            linkedin_url=profile.contact.get("linkedin", ""),
            github_url=profile.contact.get("github", ""),
            portfolio_url=profile.contact.get("portfolio", ""),
            resume_text=resume.text,
            cover_letter_text=cover_letter.text,
            custom_fields={
                "job_title": job.title,
                "company": job.company,
                "work_type": job.work_type,
                "ats_score": resume.score,
                "cover_letter_words": cover_letter.length_words
            }
        )
        logger.info(f"Generated form submission payload for {job.title} at {job.company}")
        return payload
