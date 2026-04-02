"""
AI Helper - Uses OpenAI to intelligently fill form fields and generate content.
"""

import json
from openai import OpenAI
from utils.config_loader import get_config
from utils.logger import get_logger


class AIHelper:
    """Handles AI-powered form field answering and content generation."""

    def __init__(self, config: dict = None):
        self.config = config or get_config()
        self.logger = get_logger()
        ai_config = self.config.get("openai", {})
        self.client = OpenAI(api_key=ai_config.get("api_key", ""))
        self.model = ai_config.get("model", "gpt-4o")
        self.skills_summary = ai_config.get("skills_summary", "")
        self.profile = self.config.get("profile", {})

    def _build_profile_context(self) -> str:
        """Build a text representation of the user's profile for AI context."""
        p = self.profile
        edu = p.get("education", [{}])[0] if p.get("education") else {}
        wa = p.get("work_authorization", {})

        return f"""
CANDIDATE PROFILE:
- Name: {p.get('first_name', '')} {p.get('last_name', '')}
- Email: {p.get('email', '')}
- Phone: {p.get('phone', '')}
- Location: {p.get('location', '')}
- Years of Experience: {p.get('years_of_experience', '')}
- Education: {edu.get('degree', '')} in {edu.get('field', '')} from {edu.get('university', '')}, {edu.get('graduation_year', '')}
- GPA: {edu.get('gpa', '')}
- US Work Authorization: {wa.get('authorized_us', '')}
- Requires Sponsorship: {wa.get('require_sponsorship', '')}
- LinkedIn: {p.get('linkedin_url', '')}
- GitHub: {p.get('github_url', '')}

SKILLS & EXPERIENCE SUMMARY:
{self.skills_summary}
"""

    def answer_form_question(
        self,
        question: str,
        field_type: str = "text",
        options: list = None,
        job_title: str = "",
        company: str = "",
    ) -> str:
        """
        Use AI to answer a form question based on the user's profile.
        
        Args:
            question: The form question/label text
            field_type: Type of field (text, textarea, select, radio, checkbox)
            options: Available options for select/radio/checkbox fields
            job_title: The job title being applied for
            company: The company name
            
        Returns:
            The answer string
        """
        profile_context = self._build_profile_context()

        system_prompt = f"""You are filling out a job application form on behalf of a candidate.
Answer the question accurately based on the candidate's profile below.
Be concise and professional. If the question is about salary expectations, 
provide a reasonable range for the role. If you genuinely don't know, respond with 
a reasonable default that won't disqualify the candidate.

{profile_context}

APPLYING FOR: {job_title} at {company}
"""

        user_prompt = f"Form Question: {question}\nField Type: {field_type}"
        if options:
            user_prompt += f"\nAvailable Options: {json.dumps(options)}"
        user_prompt += "\n\nProvide ONLY the answer value, nothing else. If it's a select/radio field, return the exact option text that best matches."

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                temperature=0.3,
                max_tokens=500,
            )
            answer = response.choices[0].message.content.strip()
            self.logger.debug(f"AI answered '{question}': {answer}")
            return answer
        except Exception as e:
            self.logger.error(f"AI form answer failed: {e}")
            return ""

    def generate_cover_letter(
        self, job_title: str, company: str, job_description: str
    ) -> str:
        """Generate a tailored cover letter for a specific job."""
        profile_context = self._build_profile_context()

        prompt = f"""Write a professional, concise cover letter for the following job.
Keep it to 3-4 paragraphs. Be specific about why this candidate is a great fit.
Do NOT use generic filler. Match the candidate's actual skills to the job requirements.

{profile_context}

JOB TITLE: {job_title}
COMPANY: {company}
JOB DESCRIPTION:
{job_description[:3000]}

Write the cover letter now:"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.7,
                max_tokens=1000,
            )
            return response.choices[0].message.content.strip()
        except Exception as e:
            self.logger.error(f"Cover letter generation failed: {e}")
            return ""

    def should_apply(self, job_title: str, company: str, description: str) -> bool:
        """Use AI to decide if this job is a good match."""
        profile_context = self._build_profile_context()

        prompt = f"""Based on the candidate profile and job posting below, should the candidate apply?
Consider skill match, experience level, and career alignment.
Respond with ONLY "yes" or "no".

{profile_context}

JOB: {job_title} at {company}
DESCRIPTION: {description[:2000]}

Should the candidate apply? (yes/no):"""

        try:
            response = self.client.chat.completions.create(
                model=self.model,
                messages=[{"role": "user", "content": prompt}],
                temperature=0.2,
                max_tokens=10,
            )
            answer = response.choices[0].message.content.strip().lower()
            return answer.startswith("yes")
        except Exception as e:
            self.logger.error(f"AI match check failed: {e}")
            return True  # Default to applying if AI fails
