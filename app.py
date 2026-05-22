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
    conn_str = "host={host} port={port} dbname={dbname} user={user} password={password} sslmode={sslmode}".format(**params)
    return psycopg2.connect(conn_str)


@st.cache_data(ttl=25)
def load_reference_lists(conn):
    employees = pd.read_sql_query("SELECT id, employee_name FROM employees ORDER BY employee_name", conn)
    printers = pd.read_sql_query("SELECT id, printer_name FROM printers ORDER BY printer_name", conn)
    return employees, printers


@st.cache_data(ttl=25)
def query_dashboard_data(conn, start_date, end_date, employee_id=None, printer_id=None):
    params = {"start": start_date, "end": end_date}
    filters = ["print_time BETWEEN %(start)s AND %(end)s"]
    if employee_id and employee_id != "all":
        filters.append("employee_id = %(employee)s")
        params["employee"] = int(employee_id)
    if printer_id and printer_id != "all":
        filters.append("printer_id = %(printer)s")
        params["printer"] = int(printer_id)

    where_clause = " AND ".join(filters)

    # KPIs
    total_pages_q = f"SELECT COALESCE(SUM(pages_printed),0) AS total_pages FROM print_logs WHERE {where_clause}"
    active_printers_q = f"SELECT COUNT(DISTINCT printer_id) AS active_printers FROM print_logs WHERE {where_clause}"
    total_employees_q = "SELECT COUNT(*) AS total_employees FROM employees"

    # Daily trends
    daily_q = f"SELECT date_trunc('day', print_time) AS day, SUM(pages_printed) AS pages FROM print_logs WHERE {where_clause} GROUP BY day ORDER BY day"

    # Top employees
    top_employees_q = f"SELECT e.employee_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN employees e ON p.employee_id = e.id WHERE {where_clause} GROUP BY e.employee_name ORDER BY pages DESC LIMIT 10"

    # Printer usage
    printer_usage_q = f"SELECT r.printer_name, SUM(p.pages_printed) AS pages FROM print_logs p JOIN printers r ON p.printer_id = r.id WHERE {where_clause} GROUP BY r.printer_name ORDER BY pages DESC LIMIT 20"

    # Recent print jobs
    recent_q = f"SELECT p.id, e.employee_name, r.printer_name, p.document_name, p.pages_printed, p.print_time FROM print_logs p JOIN employees e ON p.employee_id = e.id JOIN printers r ON p.printer_id = r.id WHERE {where_clause} ORDER BY p.print_time DESC LIMIT 50"

    results = {}
    results["kpi_total_pages"] = pd.read_sql_query(total_pages_q, conn, params=params).iloc[0]["total_pages"]
    results["kpi_active_printers"] = int(pd.read_sql_query(active_printers_q, conn, params=params).iloc[0]["active_printers"])
    results["kpi_total_employees"] = int(pd.read_sql_query(total_employees_q, conn).iloc[0]["total_employees"])
    results["daily"] = pd.read_sql_query(daily_q, conn, params=params)
    results["top_employees"] = pd.read_sql_query(top_employees_q, conn, params=params)
    results["printer_usage"] = pd.read_sql_query(printer_usage_q, conn, params=params)
    results["recent"] = pd.read_sql_query(recent_q, conn, params=params)
    return results


def render_kpis(kpis):
    col1, col2, col3 = st.columns(3)
    col1.metric("Total Pages", f"{kpis['kpi_total_pages']:,}")
    col2.metric("Active Printers", f"{kpis['kpi_active_printers']}")
    col3.metric("Total Employees", f"{kpis['kpi_total_employees']}")


def render_charts(daily, top_employees, printer_usage):
    if daily.empty:
        st.info("No print data for the selected range.")
        return

    daily["day"] = pd.to_datetime(daily["day"]).dt.date
    fig1 = px.line(daily, x="day", y="pages", title="Daily Print Trends", template="plotly_dark")
    fig1.update_layout(margin=dict(l=10, r=10, t=40, b=10))

    fig2 = px.bar(top_employees, x="employee_name", y="pages", title="Top Employees (by pages)", template="plotly_dark")
    fig2.update_layout(xaxis_tickangle=-45, margin=dict(l=10, r=10, t=40, b=80))

    fig3 = px.bar(printer_usage, x="printer_name", y="pages", title="Printer Usage", template="plotly_dark")
    fig3.update_layout(xaxis_tickangle=-45, margin=dict(l=10, r=10, t=40, b=80))

    left, right = st.columns([2, 1])
    left.plotly_chart(fig1, use_container_width=True)
    right.plotly_chart(fig2, use_container_width=True)

    st.plotly_chart(fig3, use_container_width=True)


def render_recent_table(df):
    if df.empty:
        st.write("No recent print jobs found.")
        return
    df["print_time"] = pd.to_datetime(df["print_time"]) 
    df = df.sort_values("print_time", ascending=False)
    st.dataframe(df, use_container_width=True)


def main():
    # Auto-refresh every 30 seconds
    st_autorefresh(interval=30 * 1000, key="autorefresh")

    st.markdown("### PrinterState — Real-time Dashboard")

    # Sidebar filters
    st.sidebar.header("Filters")
    try:
        conn = get_conn()
    except Exception as e:
        st.sidebar.error("Database connection error: " + str(e))
        st.stop()

    with conn:
        employees, printers = load_reference_lists(conn)

    emp_options = ["All"] + employees["employee_name"].tolist()
    pr_options = ["All"] + printers["printer_name"].tolist()

    selected_employee = st.sidebar.selectbox("Employee", emp_options, index=0)
    selected_printer = st.sidebar.selectbox("Printer", pr_options, index=0)

    default_end = dt.date.today()
    default_start = default_end - dt.timedelta(days=30)
    start_date, end_date = st.sidebar.date_input("Date range", [default_start, default_end])

    # Map names back to ids
    employee_id = "all"
    printer_id = "all"
    if selected_employee != "All":
        row = employees[employees["employee_name"] == selected_employee]
        if not row.empty:
            employee_id = int(row.iloc[0]["id"]) 
    if selected_printer != "All":
        row = printers[printers["printer_name"] == selected_printer]
        if not row.empty:
            printer_id = int(row.iloc[0]["id"]) 

    # Query data
    with conn:
        try:
            results = query_dashboard_data(conn, start_date, end_date + dt.timedelta(days=1), employee_id=employee_id, printer_id=printer_id)
        except Exception as e:
            st.error("Failed to load data: " + str(e))
            st.stop()

    # UI
    st.markdown("---")
    render_kpis(results)

    st.markdown("---")
    render_charts(results["daily"], results["top_employees"], results["printer_usage"])

    st.markdown("---")
    st.subheader("Recent Print Jobs")
    render_recent_table(results["recent"])

    st.sidebar.markdown("---")
    st.sidebar.write("Auto-refresh: every 30 seconds")


if __name__ == "__main__":
    main()
