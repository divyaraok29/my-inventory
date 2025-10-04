# fun_inventory_app.py
"""
A playful, single-file Streamlit inventory management app.
Features:
- SQLite persistence (inventory + transactions)
- Add / edit / delete items
- Sell and restock actions
- Low-stock alerts and restock suggestions
- Search, filter, and category grouping
- Export inventory / transactions to CSV
- Simple "market simulator" to generate random sales for demo

Run: pip install streamlit pandas altair
Then: streamlit run fun_inventory_app.py
"""

import sqlite3
import pandas as pd
import streamlit as st
import altair as alt
from datetime import datetime
import random
import io

DB_PATH = "inventory.db"

# -----------------------------
# Database helpers
# -----------------------------

def get_conn():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    return conn


def init_db():
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS items (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            category TEXT DEFAULT 'Misc',
            qty INTEGER DEFAULT 0,
            price REAL DEFAULT 0.0,
            restock_threshold INTEGER DEFAULT 5,
            created_at TEXT
        )
        """
    )
    cur.execute(
        """
        CREATE TABLE IF NOT EXISTS transactions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            item_id INTEGER,
            change INTEGER,
            note TEXT,
            timestamp TEXT
        )
        """
    )
    conn.commit()
    conn.close()


def add_item(name, category, qty, price, restock_threshold):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO items (name, category, qty, price, restock_threshold, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (name, category, qty, price, restock_threshold, datetime.utcnow().isoformat()),
    )
    item_id = cur.lastrowid
    cur.execute(
        "INSERT INTO transactions (item_id, change, note, timestamp) VALUES (?, ?, ?, ?)",
        (item_id, qty, f"Initial stock: {qty}", datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def update_quantity(item_id, delta, note=""):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("UPDATE items SET qty = qty + ? WHERE id = ?", (delta, item_id))
    cur.execute(
        "INSERT INTO transactions (item_id, change, note, timestamp) VALUES (?, ?, ?, ?)",
        (item_id, delta, note, datetime.utcnow().isoformat()),
    )
    conn.commit()
    conn.close()


def delete_item(item_id):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM items WHERE id = ?", (item_id,))
    cur.execute("DELETE FROM transactions WHERE item_id = ?", (item_id,))
    conn.commit()
    conn.close()


def get_inventory_df():
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM items", conn)
    conn.close()
    return df


def get_transactions_df(limit=500):
    conn = get_conn()
    df = pd.read_sql_query("SELECT * FROM transactions ORDER BY timestamp DESC LIMIT ?", conn, params=(limit,))
    conn.close()
    return df


# -----------------------------
# Utility / UI helpers
# -----------------------------

st.set_page_config(page_title="Fun Inventory 🧸", layout="wide")

init_db()

st.title("🧺 Fun Inventory Manager")
st.write("A playful, minimal inventory system — add items, sell, restock, and watch charts dance.")

# Sidebar: quick add
with st.sidebar.expander("Quick add an item 🧾", expanded=True):
    na = st.text_input("Item name", key="s_name")
    ca = st.text_input("Category", value="General", key="s_cat")
    qt = st.number_input("Quantity", min_value=0, value=5, step=1, key="s_qty")
    pr = st.number_input("Price (per unit)", min_value=0.0, value=9.99, step=0.01, format="%.2f", key="s_price")
    rt = st.number_input("Restock threshold", min_value=0, value=3, step=1, key="s_restock")
    if st.button("Add item ✨", key="s_add"):
        if na.strip() == "":
            st.error("Please provide an item name.")
        else:
            add_item(na.strip(), ca.strip(), int(qt), float(pr), int(rt))
            st.success(f"Added '{na.strip()}' with {int(qt)} units.")

# Load inventory
inv = get_inventory_df()

# Top controls
col1, col2, col3 = st.columns([2, 1, 1])
with col1:
    q = st.text_input("Search items (name or category)", value="", key="search")
with col2:
    cat_filter = st.selectbox("Filter by category", options=["All"] + (sorted(inv['category'].unique().tolist()) if not inv.empty else []))
with col3:
    show_only_low = st.checkbox("Show low-stock only 🔴", value=False)

# Apply filters
df = inv.copy()
if q:
    ql = q.lower()
    df = df[df['name'].str.lower().str.contains(ql) | df['category'].str.lower().str.contains(ql)]
if cat_filter != "All":
    df = df[df['category'] == cat_filter]
if show_only_low:
    df = df[df['qty'] <= df['restock_threshold']]

# Main area: inventory table and actions
st.subheader("Inventory")
if df.empty:
    st.info("No items yet — add one from the sidebar or try the demo generator below.")
else:
    # Show low stock badges
    low_mask = df['qty'] <= df['restock_threshold']
    if low_mask.any():
        low_ct = low_mask.sum()
        st.warning(f"{low_ct} item(s) low in stock — consider restocking! 🔔")

    # Table with action buttons
    table_cols = st.columns([3, 1, 1, 1, 1, 2])
    hdr = ["Name", "Category", "Qty", "Price", "Threshold", "Actions"]
    for i, h in enumerate(hdr):
        table_cols[i].markdown(f"**{h}**")

    for _, row in df.sort_values('name').iterrows():
        c1, c2, c3, c4, c5, c6 = st.columns([3, 1, 1, 1, 1, 2])
        c1.write(row['name'])
        c2.write(row['category'])
        c3.write(int(row['qty']))
        c4.write(f"£{row['price']:.2f}")
        c5.write(int(row['restock_threshold']))

        with c6:
            if st.button(f"Sell 1 🛒 (id:{row['id']})", key=f"sell_{row['id']}"):
                if row['qty'] <= 0:
                    st.warning("No stock to sell — restock first! ⚠️")
                else:
                    update_quantity(int(row['id']), -1, note="Sold 1")
                    st.experimental_rerun()
            if st.button(f"Restock +5 📦 (id:{row['id']})", key=f"restock_{row['id']}"):
                update_quantity(int(row['id']), 5, note="Restocked +5")
                st.experimental_rerun()
            if st.button(f"Delete 🗑 (id:{row['id']})", key=f"del_{row['id']}"):
                delete_item(int(row['id']))
                st.experimental_rerun()

# Actions / utilities
st.sidebar.markdown("---")
with st.sidebar.expander("Playground & utilities 🎛️"):
    if st.button("Generate demo items ✨"):
        demo_items = [
            ("Retro Robot Toy", "Toys", 12, 14.99, 3),
            ("Eco Notebook", "Stationery", 30, 3.50, 5),
            ("Coffee Beans 250g", "Food", 8, 6.99, 4),
            ("Wireless Dongle", "Electronics", 4, 19.99, 2),
            ("Herbal Tea", "Food", 20, 2.99, 5),
        ]
        for it in demo_items:
            add_item(*it)
        st.success("Demo items added — enjoy! 🎉")
        st.experimental_rerun()

    if st.button("Simulate random sales (10 events) 🎲"):
        live = get_inventory_df()
        if live.empty:
            st.warning("No items to simulate — add some first.")
        else:
            choices = live['id'].tolist()
            for _ in range(10):
                iid = random.choice(choices)
                change = -random.randint(1, 3)
                update_quantity(int(iid), change, note="Simulated sale")
        st.success("Simulation complete — check transactions!")
        st.experimental_rerun()

    if st.button("Clear all data (danger!) 🧨"):
        conn = get_conn()
        cur = conn.cursor()
        cur.execute("DELETE FROM transactions")
        cur.execute("DELETE FROM items")
        conn.commit()
        conn.close()
        st.warning("All data cleared.")
        st.experimental_rerun()

# Visualizations
st.subheader("Insights 📊")
inv_full = get_inventory_df()
if not inv_full.empty:
    chart_df = inv_full.groupby('category', as_index=False).agg({'qty':'sum'})
    chart = alt.Chart(chart_df).mark_bar().encode(
        x=alt.X('category:N', sort='-y', title='Category'),
        y=alt.Y('qty:Q', title='Total Quantity')
    ).properties(height=300, width=700)
    st.altair_chart(chart, use_container_width=True)

    # Top low-stock items
    low = inv_full[inv_full['qty'] <= inv_full['restock_threshold']].sort_values('qty')
    if not low.empty:
        st.markdown("**Low-stock items**")
        st.table(low[['name','category','qty','restock_threshold']].head(10))
else:
    st.info("No data to show charts yet — add items to see insights.")

# Transactions
st.subheader("Activity log")
trans = get_transactions_df(200)
if trans.empty:
    st.write("No transactions yet — they'll appear here when you add, sell, or restock items.")
else:
    # Join item names for clarity
    items_map = inv_full.set_index('id')['name'].to_dict() if not inv_full.empty else {}
    trans['item_name'] = trans['item_id'].apply(lambda x: items_map.get(x, f"(id:{x})"))
    st.dataframe(trans[['timestamp','item_name','change','note']].rename(columns={'timestamp':'When','item_name':'Item','change':'Change','note':'Note'}))

# Export utilities
st.sidebar.markdown("---")
with st.sidebar.expander("Export / Backup 💾"):
    if st.button("Download inventory CSV"):
        invb = get_inventory_df()
        towrite = io.StringIO()
        invb.to_csv(towrite, index=False)
        b = towrite.getvalue().encode()
        st.download_button("Download inventory.csv", data=b, file_name="inventory.csv", mime="text/csv")

    if st.button("Download transactions CSV"):
        tr = get_transactions_df(1000)
        towrite = io.StringIO()
        tr.to_csv(towrite, index=False)
        b = towrite.getvalue().encode()
        st.download_button("Download transactions.csv", data=b, file_name="transactions.csv", mime="text/csv")

st.markdown("---")
st.caption("Built with ❤️ for practicing inventory flows. Want extra features? Ask for barcode scanning, multi-user, or cloud sync!")

# https://divyaraok29.github.io/my-inventory/