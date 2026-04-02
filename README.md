# Job Application Agent

An AI-powered automation tool that applies to jobs on your behalf across **LinkedIn**, **Indeed**, and **company career pages** (Greenhouse, Lever, Workday, Ashby, and more).

## Features

- **LinkedIn Easy Apply** — Searches for jobs using your keywords and filters, navigates the multi-step Easy Apply flow, fills all form fields automatically
- **Indeed Apply** — Searches and applies to "Easily Apply" jobs on Indeed
- **Company Career Pages** — Handles direct applications on Greenhouse, Lever, Workday, Ashby, iCIMS, and generic ATS platforms
- **AI-Powered Form Filling** — Uses OpenAI to intelligently answer custom application questions based on your profile
- **Anti-Detection** — Human-like typing, random delays, stealth browser settings
- **Application Tracker** — Logs every application to CSV with status, timestamps, and error details
- **Deduplication** — Never applies to the same job twice
- **Configurable Filters** — Blacklist companies, filter by title patterns, set experience level and job type
- **Dry Run Mode** — Search and preview jobs without applying
- **Screenshots on Error** — Captures browser screenshots when something goes wrong

## Project Structure

```
job-apply-agent/
├── main.py                  # CLI entry point & orchestrator
├── config.yaml              # All configuration (profile, search, credentials)
├── requirements.txt         # Python dependencies
├── platforms/
│   ├── base.py              # Abstract base class for platforms
│   ├── linkedin.py          # LinkedIn automation
│   ├── indeed.py            # Indeed automation
│   └── career_pages.py      # Greenhouse, Lever, Workday, etc.
├── utils/
│   ├── config_loader.py     # YAML config + env var loading
│   ├── logger.py            # Rich console + file logging
│   ├── browser_manager.py   # Playwright browser with stealth
│   ├── ai_helper.py         # OpenAI-powered form filling
│   └── tracker.py           # CSV application tracker
├── data/
│   └── applications.csv     # Generated — all application records
├── resumes/
│   └── resume.pdf           # Place your resume here
└── logs/
    ├── run_*.log            # Run logs
    └── screenshots/         # Error screenshots
```

## Setup

### 1. Install Dependencies

```bash
cd job-apply-agent
pip install -r requirements.txt
playwright install chromium
```

### 2. Configure Your Profile

Edit `config.yaml` and fill in:

- **Your personal info** (name, email, phone, location, education)
- **Job search preferences** (keywords, locations, experience levels, job types)
- **Platform credentials** (LinkedIn and/or Indeed login)
- **OpenAI API key** (for AI-powered form filling)
- **Skills summary** (so the AI can answer questions about your experience)

### 3. Add Your Resume

Place your resume PDF in the `resumes/` folder:
```bash
cp ~/your-resume.pdf resumes/resume.pdf
```

### 4. Set Credentials Securely (Recommended)

Instead of putting passwords in `config.yaml`, use environment variables:

```bash
export LINKEDIN_EMAIL="your@email.com"
export LINKEDIN_PASSWORD="your-password"
export INDEED_EMAIL="your@email.com"
export INDEED_PASSWORD="your-password"
export OPENAI_API_KEY="sk-..."
```

Or create a `.env` file in the project root:
```
LINKEDIN_EMAIL=your@email.com
LINKEDIN_PASSWORD=your-password
INDEED_EMAIL=your@email.com
INDEED_PASSWORD=your-password
OPENAI_API_KEY=sk-...
```

## Usage

### Run All Platforms
```bash
python main.py
```

### Run a Specific Platform
```bash
python main.py --platform linkedin
python main.py --platform indeed
```

### Apply to Specific Career Page URLs
Create a file with one URL per line:
```
# urls.txt
https://boards.greenhouse.io/company/jobs/12345
https://jobs.lever.co/company/abcdef
https://company.wd5.myworkdayjobs.com/careers/job/12345
```

Then run:
```bash
python main.py --urls urls.txt
python main.py --platform career_pages --urls urls.txt
```

### Dry Run (Search Only, No Applications)
```bash
python main.py --dry-run
```

### Run Headless (No Browser Window)
```bash
python main.py --headless
```

### Limit Applications Per Run
```bash
python main.py --max-apps 10
```

### Combine Options
```bash
python main.py --platform linkedin --max-apps 20 --headless
```

## How It Works

### Application Flow

1. **Login** — Authenticates with the platform (handles CAPTCHAs by pausing for manual input)
2. **Search** — Queries jobs using your configured keywords, location, and filters
3. **Filter** — Skips blacklisted companies, title mismatches, and duplicates
4. **Apply** — Navigates each application form:
   - Uploads your resume
   - Fills standard fields (name, email, phone) from your config
   - Uses OpenAI to answer custom/unexpected questions
   - Handles multi-step forms (Next → Next → Submit)
5. **Track** — Logs every attempt to `data/applications.csv`

### AI Form Filling

When the agent encounters a form field it can't fill from your profile config, it calls OpenAI with:
- The question/label text
- The field type and available options
- Your full profile and skills summary
- The job title and company for context

This handles questions like:
- "Why are you interested in this role?"
- "Describe your experience with Python"
- "What is your expected salary range?"
- "Are you willing to relocate?"

### Anti-Detection

The agent includes several measures to avoid bot detection:
- Random delays between actions (configurable range)
- Character-by-character typing with variable speed
- Browser fingerprint masking (webdriver, plugins, languages)
- Realistic viewport and user agent
- Cookie-based session persistence

## Application Tracker

All applications are logged to `data/applications.csv` with columns:
- Timestamp
- Platform (linkedin, indeed, career_pages)
- Company name
- Job title
- Job URL
- Location
- Status (applied, skipped, failed, duplicate)
- Error message (if failed)
- Resume used
- Whether a cover letter was generated

## Important Notes

- **Security Checkpoints** — LinkedIn and Indeed may trigger CAPTCHAs or email verification. The agent will pause and wait for you to complete these manually in the browser window.
- **Rate Limits** — Running too many applications too fast can get your account flagged. Use conservative `slow_mo` and delay settings.
- **Review First** — Always do a `--dry-run` first to verify the search results look correct before running live applications.
- **Account Risk** — Automated applications may violate platform ToS. Use at your own discretion.
- **Keep Config Updated** — Update your skills summary and profile regularly for best AI form-filling results.

## Troubleshooting

| Issue | Solution |
|-------|----------|
| Login fails | Check credentials in config.yaml or env vars. Try logging in manually first. |
| CAPTCHA blocks login | Run without `--headless` and solve it manually when prompted. |
| Forms not filling correctly | Update your `skills_summary` in config.yaml for better AI answers. |
| "No Easy Apply button" | The job requires an external application. Use `--urls` for direct career pages. |
| Browser crashes | Increase `timeout` in config.yaml. Ensure Playwright is installed: `playwright install chromium`. |
| Too many skipped jobs | Adjust `title_exclude_patterns` and `blacklist_companies` in config. |
