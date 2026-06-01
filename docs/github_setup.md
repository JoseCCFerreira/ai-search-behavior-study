# GitHub Setup

This file explains how to create the repository and publish the project.

## Create a repository

1. Open GitHub and log in.
2. Click **New repository**.
3. Set the repository name to `ai-search-behavior-study`.
4. Add a description and choose public or private.
5. Do not initialize with a README if you will push this project.

## First commit

```bash
git init
git add .
git commit -m "Initial commit - AI Search Behavior Study"
```

## Push to GitHub

```bash
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/ai-search-behavior-study.git
git push -u origin main
```

## Enable GitHub Pages

1. Go to the repository on GitHub.
2. Open **Settings**.
3. Select **Pages**.
4. Choose **Deploy from branch**.
5. Select branch `main`.
6. Select folder `/portfolio_site`.
7. Save the configuration.
8. Open the generated site link.

## Add screenshots to README

- Capture screenshots of the Streamlit dashboard or site.
- Save them under `portfolio_site/assets/screenshots/`.
- Reference them in `README.md` or the portfolio page.

## Maintain the project

- Keep issues organized by feature or bug.
- Use branches for new work.
- Create pull requests for reviews.
- Tag releases with semantic versioning.
- Update documentation when adding new features.
