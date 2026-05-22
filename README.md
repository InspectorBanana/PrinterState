# PrinterState

Simple real-time Power BI-style dashboard built with Streamlit that connects directly to a Neon PostgreSQL database.

Features:
- Real-time auto-refresh every 30 seconds
- KPI cards: Total Pages, Active Printers, Total Employees
- Charts: Daily print trends, Top employees, Printer usage (Plotly)
- Recent print jobs table
- Sidebar filters: Employee, Printer, Date range

Quick start
1. Copy `.env.example` to `.env` and fill in your Neon Postgres credentials, or set `DATABASE_URL`.
2. Create a virtualenv and install dependencies:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

3. Run the app:

```bash
streamlit run app.py
```

Notes
- The app queries tables `employees`, `printers`, `print_logs`, and `collected_jobs` (see your schema). The provided queries aggregate and join only what's necessary for the dashboard to keep performance good.
- Caching and a 30-second auto-refresh are used to balance real-time updates with performance.

If you want improvements (auth, more KPIs, exports), tell me which features to add.
