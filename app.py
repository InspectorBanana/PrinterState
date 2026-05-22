import os
import datetime as dt

import streamlit as st
import pandas as pd
import plotly.express as px
import psycopg2
from streamlit_autorefresh import st_autorefresh
from dotenv import load_dotenv


load_dotenv()

st.set_page_config(page_title="PrinterState — Real-time Dashboard", layout="wide", page_icon=":printer:")


def get_conn():
    """Create a psycopg2 connection using DATABASE_URL or individual env vars."""
    database_url = os.getenv("DATABASE_URL")
    if database_url:
        return psycopg2.connect(database_url)

    params = dict(
        host=os.getenv("NEON_HOST", ""),
        port=os.getenv("NEON_PORT", "5432"),
        dbname=os.getenv("NEON_DB", ""),
        user=os.getenv("NEON_USER", ""),
        password=os.getenv("NEON_PASSWORD", ""),
        sslmode=os.getenv("NEON_SSLMODE", "require"),
    )
    host_val = params["host"]
    if host_val:
        host_val_str = str(host_val)
        if "=" in host_val_str or "://" in host_val_str or host_val_str.startswith("postgres"):
            try:
                return psycopg2.connect(host_val_str)
            except Exception:
                pass

    conn_str = "host={host} port={port} dbname={dbname} user={user} password={password} sslmode={sslmode}".format(**params)
    try:
        return psycopg2.connect(conn_str)
    except Exception as e:
        raise RuntimeError(
            "Database connection failed. Check your .env: set DATABASE_URL="
            "postgres://user:password@host:port/dbname OR set NEON_HOST,NEON_DB,NEON_USER,NEON_PASSWORD separately. "
            f"Original error: {e}"
        )


def has_column(conn, table, column):
    query = """
        SELECT 1
        FROM information_schema.columns
        WHERE table_name = %s AND column_name = %s
        LIMIT 1
    """
    with conn.cursor() as cur:
        cur.execute(query, (table, column))
        return cur.fetchone() is not None


def render_kpis(kpis):
    col1, col2, col3, col4, col5 = st.columns(5)
    col1.metric("Total Pages Printed Today", f"{kpis['kpi_total_pages_today']:,}")
    col2.metric("Total Print Jobs Today", f"{kpis['kpi_total_jobs_today']:,}")
    col3.metric("Active Printers Today", f"{kpis['kpi_active_printers_today']}")
    col4.metric("Active Employees Today", f"{kpis['kpi_active_employees_today']}")
    col5.metric("Most Used Printer", kpis["most_used_printer_today"])
    if kpis.get("printer_health"):
        st.markdown("---")
        st.metric("Printer Health", kpis["printer_health"])


def render_charts(dept_today, top_users_today, top_users_month, usage_distribution):
    if dept_today.empty and top_users_today.empty and top_users_month.empty and usage_distribution.empty:
        st.info("No printing data available for the selected filters.")
        return

    fig1 = px.bar(dept_today, x="department", y="pages", title="Department-wise Printing Today", template="plotly_dark")
    fig1.update_layout(xaxis_tickangle=-45, margin=dict(l=10, r=10, t=40, b=80))

    fig2 = px.bar(top_users_today, x="employee_name", y="pages", title="Top 5 Print Users Today", template="plotly_dark")
    fig2.update_layout(xaxis_tickangle=-45, margin=dict(l=10, r=10, t=40, b=80))

    fig3 = px.bar(top_users_month, x="employee_name", y="pages", title="Top 5 Print Users This Month", template="plotly_dark")
    fig3.update_layout(xaxis_tickangle=-45, margin=dict(l=10, r=10, t=40, b=80))

    fig4 = px.pie(usage_distribution, values="pages", names="printer_name", title="Printer Usage Distribution", hole=0.35, template="plotly_dark")
    fig4.update_traces(textposition="inside", textinfo="percent+label")
    fig4.update_layout(margin=dict(l=10, r=10, t=40, b=10))

    st.plotly_chart(fig1, use_container_width=True)
    row = st.columns(2)
    row[0].plotly_chart(fig2, use_container_width=True)
    row[1].plotly_chart(fig3, use_container_width=True)
    st.plotly_chart(fig4, use_container_width=True)


def render_recent_table(df):
    if df.empty:
        st.write("No recent print jobs found for the selected filters.")
        return
    df["print_time"] = pd.to_datetime(df["print_time"])
    df = df.sort_values("print_time", ascending=False)
    st.dataframe(df, use_container_width=True)


def main():
    st_autorefresh(interval=30 * 1000, key="autorefresh")
    st.markdown("### PrinterState — Real-time Dashboard")
    st.sidebar.header("Filters")

    try:
        conn = get_conn()
    except Exception as e:
        st.sidebar.error("Database connection error: " + str(e))
        st.stop()

    with conn:
        supports_department = has_column(conn, "employees", "department")
        printers_health_column = None
        for candidate in ("health_status", "status", "health"):
            if has_column(conn, "printers", candidate):
                printers_health_column = candidate
                break

        employees = pd.read_sql_query(
            "SELECT id, employee_name" + (", department" if supports_department else "") + " FROM employees ORDER BY employee_name",
            conn,
        )
        printers = pd.read_sql_query(
            "SELECT id, printer_name" + (f", {printers_health_column}" if printers_health_column else "") + " FROM printers ORDER BY printer_name",
            conn,
        )

    emp_options = ["All"] + employees["employee_name"].tolist()
    pr_options = ["All"] + printers["printer_name"].tolist()
    dept_options = ["All"] + sorted(employees["department"].dropna().unique().tolist()) if supports_department else ["All"]

    selected_employee = st.sidebar.selectbox("Employee", emp_options, index=0)
    selected_department = st.sidebar.selectbox("Department", dept_options, index=0)
    selected_printer = st.sidebar.selectbox("Printer", pr_options, index=0)

    default_end = dt.date.today()
    default_start = default_end - dt.timedelta(days=30)
    date_range = st.sidebar.date_input("Date Range", [default_start, default_end])
    if isinstance(date_range, (list, tuple)) and len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date = end_date = date_range

    employee_id = "all"
    printer_id = "all"
    department = "all"
    if selected_employee != "All":
        row = employees[employees["employee_name"] == selected_employee]
        if not row.empty:
            employee_id = int(row.iloc[0]["id"])
    if selected_printer != "All":
        row = printers[printers["printer_name"] == selected_printer]
        if not row.empty:
            printer_id = int(row.iloc[0]["id"])
    if supports_department and selected_department != "All":
        department = selected_department

    today = dt.date.today()
    tomorrow = today + dt.timedelta(days=1)
    month_start = today.replace(day=1)
    if today.month == 12:
        month_end = dt.date(today.year + 1, 1, 1)
    else:
        month_end = dt.date(today.year, today.month + 1, 1)

    def build_filters(base_filter, params):
        filters = [base_filter] if base_filter else []
        if employee_id != "all":
            filters.append("p.employee_id = %(employee)s")
            params["employee"] = employee_id
        if printer_id != "all":
            filters.append("p.printer_id = %(printer)s")
            params["printer"] = printer_id
        if supports_department and department != "all":
            filters.append("e.department = %(department)s")
            params["department"] = department
        return " AND ".join(filters), params

    range_clause, range_params = build_filters(
        "p.print_time >= %(start)s AND p.print_time < %(end)s",
        {"start": start_date, "end": end_date + dt.timedelta(days=1)},
    )
    today_clause, today_params = build_filters(
        "p.print_time >= %(today)s AND p.print_time < %(tomorrow)s",
        {"today": today, "tomorrow": tomorrow},
    )
    month_clause, month_params = build_filters(
        "p.print_time >= %(month_start)s AND p.print_time < %(month_end)s",
        {"month_start": month_start, "month_end": month_end},
    )

    with conn:
        try:
            results = {}

            results["kpi_total_pages_today"] = int(
                pd.read_sql_query(
                    f"SELECT COALESCE(SUM(p.pages_printed), 0) AS total_pages FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause}",
                    conn,
                    params=today_params,
                ).iloc[0]["total_pages"]
            )
            results["kpi_total_jobs_today"] = int(
                pd.read_sql_query(
                    f"SELECT COUNT(*) AS total_jobs FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause}",
                    conn,
                    params=today_params,
                ).iloc[0]["total_jobs"]
            )
            results["kpi_active_printers_today"] = int(
                pd.read_sql_query(
                    f"SELECT COUNT(DISTINCT p.printer_id) AS active_printers FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause}",
                    conn,
                    params=today_params,
                ).iloc[0]["active_printers"]
            )
            results["kpi_active_employees_today"] = int(
                pd.read_sql_query(
                    f"SELECT COUNT(DISTINCT p.employee_id) AS active_employees FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause}",
                    conn,
                    params=today_params,
                ).iloc[0]["active_employees"]
            )
            most_printer = pd.read_sql_query(
                f"SELECT r.printer_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN printers r ON p.printer_id = r.id JOIN employees e ON p.employee_id = e.id WHERE {today_clause} GROUP BY r.printer_name ORDER BY pages DESC LIMIT 1",
                conn,
                params=today_params,
            )
            results["most_used_printer_today"] = most_printer.iloc[0]["printer_name"] if not most_printer.empty else "No prints today"

            if printers_health_column:
                health_df = pd.read_sql_query(
                    f"SELECT {printers_health_column} AS health_status FROM printers",
                    conn,
                )
                if not health_df.empty:
                    values = health_df["health_status"].astype(str).str.lower().fillna("unknown")
                    healthy = values.isin({"ok", "healthy", "online", "good"})
                    percent = int(healthy.mean() * 100)
                    results["printer_health"] = f"{percent}% good"
                else:
                    results["printer_health"] = "Unknown"

            if supports_department:
                results["dept_today"] = pd.read_sql_query(
                    f"SELECT e.department, SUM(p.pages_printed) AS pages FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause} GROUP BY e.department ORDER BY pages DESC",
                    conn,
                    params=today_params,
                )
            else:
                results["dept_today"] = pd.DataFrame(columns=["department", "pages"])

            results["top_users_today"] = pd.read_sql_query(
                f"SELECT e.employee_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {today_clause} GROUP BY e.employee_name ORDER BY pages DESC LIMIT 5",
                conn,
                params=today_params,
            )
            results["top_users_month"] = pd.read_sql_query(
                f"SELECT e.employee_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {month_clause} GROUP BY e.employee_name ORDER BY pages DESC LIMIT 5",
                conn,
                params=month_params,
            )
            results["printer_usage_distribution"] = pd.read_sql_query(
                f"SELECT r.printer_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN printers r ON p.printer_id = r.id JOIN employees e ON p.employee_id = e.id WHERE {range_clause} GROUP BY r.printer_name ORDER BY pages DESC",
                conn,
                params=range_params,
            )
            results["recent"] = pd.read_sql_query(
                f"SELECT p.id, e.employee_name, r.printer_name, p.document_name, p.pages_printed, p.print_time FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {range_clause} ORDER BY p.print_time DESC LIMIT 50",
                conn,
                params=range_params,
            )
        except Exception as e:
            st.error("Failed to load data: " + str(e))
            st.stop()

    st.markdown("---")
    render_kpis(results)

    st.markdown("---")
    render_charts(
        results.get("dept_today", pd.DataFrame()),
        results["top_users_today"],
        results["top_users_month"],
        results["printer_usage_distribution"],
    )

    st.markdown("---")
    st.subheader("Recent Print Jobs")
    render_recent_table(results["recent"])

    st.sidebar.markdown("---")
    st.sidebar.write("Auto-refresh: every 30 seconds")


if __name__ == "__main__":
    main()
