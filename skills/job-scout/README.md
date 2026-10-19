# job-scout (skill)

Finds open roles that fit your resume by reading employer job boards directly — Greenhouse,
Ashby and Lever — after you confirm a short search brief. Each result is checked open today,
links straight to the employer, and explains its fit with quotes from the job description.

> **Status: in development.** The confirmation gate and network check work; the search,
> results and memory steps arrive in later milestones. See the repo `ROADMAP.md`.

- **What it reads:** your resume (text, PDF, Markdown, HTML, .docx) or a description of what you do.
- **What leaves your machine:** only list requests to the job boards. Your resume and brief stay local (`~/.job-scout/`).
- **What it never does:** apply, message anyone, write cover letters, or read LinkedIn or sites behind a login.
- **Best for:** tech and startup roles. Coverage is thin for healthcare, retail, government and large non-tech employers.

Entry point: [`SKILL.md`](SKILL.md). Field notes on each job board: [`references/ats-notes.md`](references/ats-notes.md).
