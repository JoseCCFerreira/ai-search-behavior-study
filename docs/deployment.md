# Deployment

## Local deployment

1. Install dependencies:

```bash
pip install -r requirements.txt
```

2. Generate demo data:

```bash
python src/data_ingestion/create_demo_data.py
```

3. Create the DuckDB database:

```bash
python src/database/create_database.py
```

4. Load raw data into DuckDB:

```bash
python src/database/load_to_duckdb.py
```

5. Run the Streamlit dashboard:

```bash
streamlit run app/streamlit_app.py
```

## GitHub Pages deployment

1. Push the repository to GitHub.
2. In repository **Settings**, go to **Pages**.
3. Set source to branch `main` and folder `/portfolio_site`.
4. Save and wait for the site to build.
5. Visit the generated URL.

## Streamlit Community Cloud

1. Log in to Streamlit Community Cloud.
2. Create a new app and connect it to the GitHub repository.
3. Set the main file path to `app/streamlit_app.py`.
4. Confirm `requirements.txt` is present.
5. Configure secrets if needed.
6. Deploy the app.

## Updating the app

- Push changes to GitHub.
- GitHub Pages and Streamlit Cloud will rebuild automatically.
- If there are errors, inspect logs on the service.

## Notes

- Keep raw data in `data/raw/` and processed tables in DuckDB.
- For large data, avoid committing raw exports to the repository.
