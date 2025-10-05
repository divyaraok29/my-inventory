# fun_inventory_supabase.py
"""
Fun Inventory App with Supabase backend.
Features:
- Cloud-backed inventory & transactions
- Automatic table creation
- Add/edit/delete items
- Sell/restock actions
- Low-stock alerts & charts
- CSV backup/export
Run:
pip install streamlit pandas altair supabase
streamlit run fun_inventory_supabase.py
"""

import streamlit as st
import pandas as pd
import altair as alt
import io
from datetime import datetime
import random
from supabase import create_client

# -----------------------------
# Supabase setup
# -----------------------------
SUPABASE_URL = st.secrets["SUPABASE_URL"]
SUPABASE_KEY = st.secrets["SUPABASE_KEY"]
supabase = create_client(SUPABASE_URL, SUPABASE_KEY)

# -----------------------------
# CRUD helpers
# -----------------------------
def add_item(name, category, qty, price, restock_threshold):
    try:
        res = supabase.table("items").insert({
            "name": name,
            "category": category,
            "qty": qty,
            "price": price,
            "restock_threshold": restock_threshold
        }).execute()
        item_id = res.data[0]["id"]
        supabase.table("transactions").insert({
            "item_id": item_id,
            "change": qty,
            "note": f"Initial stock: {qty}"
        }).execute()
    except Exception as e:
        st.error(f"Failed to add item: {e}")

def update_quantity(item_id, delta, note=""):
    try:
        # Step 1: get current qty
        res = supabase.table("items").select("qty").eq("id", item_id).single().execute()
        if res.data:
            current_qty = res.data["qty"]
            new_qty = max(current_qty + delta, 0)  # prevent negative qty

            # Step 2: update new qty
            supabase.table("items").update({"qty": new_qty}).eq("id", item_id).execute()

            # Step 3: add transaction log
            supabase.table("transactions").insert({
                "item_id": item_id,
                "change": delta,
                "note": note
            }).execute()
        else:
            st.error("Item not found")
    except Exception as e:
        st.error(f"Failed to update quantity: {e}")

def delete_item(item_id):
    supabase.table("items").delete().eq("id", item_id).execute()
    supabase.table("transactions").delete().eq("item_id", item_id).execute()

def get_inventory_df():
    res = supabase.table("items").select("*").execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

def get_transactions_df(limit=500):
    res = supabase.table("transactions").select("*").order("timestamp", desc=True).limit(limit).execute()
    return pd.DataFrame(res.data) if res.data else pd.DataFrame()

# -----------------------------
# Streamlit UI
# -----------------------------
st.markdown("""
<meta name="viewport" content="width=1024">
<style>
    /* Always use desktop-like layout */
    [data-testid="stAppViewContainer"] {
        min-width: 1024px !important;
        zoom: 0.9; /* optional - fit better on small phones */
    }
    [data-testid="stHeader"] {
        position: sticky;
        top: 0;
        z-index: 100;
    }
</style>
""", unsafe_allow_html=True)

st.set_page_config(page_title="Fun Inventory 🧸", layout="wide")
st.title("🧺 Fun Inventory Manager")
st.write("Cloud-backed inventory system — add items, sell, restock, and watch charts dance!")
st.info("For best experience, view in Desktop Mode 🌐")

# Load inventory
inv = get_inventory_df()

# Sidebar: add item
with st.sidebar.expander("Quick add an item 🧾", expanded=True):
    na = st.text_input("Item name", key="s_name")

    # Generate category options dynamically from your inventory
    categories = sorted(inv['category'].unique().tolist()) if not inv.empty else []
    
    # Use selectbox with option to type custom category
    ca = st.selectbox(
        "Category (choose or type new)",
        options=categories + ["Other (Type New Category)"],
        index=0 if categories else None,
        key="s_cat_select"
    )

    # If user chooses "Add new", show a text input field
    if ca == "Other (Type New Category)":
        new_ca = st.text_input("Type New Category", key="s_new_cat")
        if new_ca.strip():
            ca = new_ca.strip()
    # ca = st.text_input("Category", value="Misc", key="s_cat")

    qt = st.number_input("Quantity", min_value=0, value=5, step=1, key="s_qty")
    pr = st.number_input("Price (per unit)", min_value=0.0, value=9.99, step=0.01, format="%.2f", key="s_price")
    rt = st.number_input("Restock threshold", min_value=0, value=3, step=1, key="s_restock")
    if st.button("Add item ✨", key="s_add"):
        if na.strip() == "":
            st.error("Please provide an item name.")
        else:
            add_item(na.strip(), ca.strip(), int(qt), float(pr), int(rt))
            st.success(f"Added '{na.strip()}' with {int(qt)} units.")

# Filters
col1, col2, col3 = st.columns([2,1,1])
with col1:
    q = st.text_input("Search items (name or category)", value="", key="search")
with col2:
    cat_filter = st.selectbox("Filter by category", options=["All"] + (sorted(inv['category'].unique().tolist()) if not inv.empty else []))
with col3:
    show_only_low = st.checkbox("Show low-stock only 🔴", value=False)

df = inv.copy()
if q:
    ql = q.lower()
    df = df[df['name'].str.lower().str.contains(ql) | df['category'].str.lower().str.contains(ql)]
if cat_filter != "All":
    df = df[df['category'] == cat_filter]
if show_only_low:
    df = df[df['qty'] <= df['restock_threshold']]

# Inventory table
st.subheader("Inventory")
if df.empty:
    st.info("No items yet — add one from the sidebar or generate demo items below.")
else:
    low_mask = df['qty'] <= df['restock_threshold']
    if low_mask.any():
        st.warning(f"{low_mask.sum()} item(s) low in stock 🔔")

    table_cols = st.columns([3,2,1,1,1,1])
    hdr = ["Name","Category","Use","Qty","Buy","Delete"]
    for i, h in enumerate(hdr):
        table_cols[i].markdown(f"**{h}**")

    for _, row in df.sort_values('name').iterrows():
        c1,c2,c8,c3,c7,c6 = st.columns([3,2,1,1,1,1])
        c1.write(row['name'])
        c2.write(row['category'])

        with c8:
            if st.button("", icon="➖", key=f"sell_{row['id']}", help="Use Item", disabled=bool(row['qty'] <= 0)):
                if row['qty'] <= 0:
                    st.warning("No stock to use — restock first! ⚠️")
                else:
                    update_quantity(int(row['id']), -1, note="Used 1")
                    st.rerun()

        c3.write(int(row['qty']))

        with c7:
            if st.button("", icon="➕", key=f"restock_{row['id']}", help="Buy Item"):
                update_quantity(int(row['id']), 1, note="Bought +1")
                st.rerun()
        # c4.write(f"£{row['price']:.2f}")
        # c5.write(int(row['restock_threshold']))
        with c6:
            if st.button("", icon=":material/delete:", key=f"del_{row['id']}", help="Remove Item"):
                delete_item(int(row['id']))
                st.rerun()

# Sidebar utilities
st.sidebar.markdown("---")
with st.sidebar.expander("Playground & utilities 🎛️"):
    if st.button("Generate demo items ✨"):
        demo_items = [
            ("Retro Robot Toy","Toys",12,14.99,3),
            ("Eco Notebook","Stationery",30,3.50,5),
            ("Coffee Beans 250g","Food",8,6.99,4),
            ("Wireless Dongle","Electronics",4,19.99,2),
            ("Herbal Tea","Food",20,2.99,5),
        ]
        for it in demo_items:
            add_item(*it)
        st.success("Demo items added! 🎉")
        st.rerun()

    if st.button("Simulate random sales (10 events) 🎲"):
        live = get_inventory_df()
        if live.empty:
            st.warning("No items to simulate — add some first.")
        else:
            choices = live['id'].tolist()
            for _ in range(10):
                iid = random.choice(choices)
                change = -random.randint(1,3)
                update_quantity(int(iid), change, note="Simulated sale")
        st.success("Simulation complete!")
        st.rerun()

    if st.button("Clear all data 🧨"):
        supabase.table("transactions").delete().neq("id", 0).execute()
        supabase.table("items").delete().neq("id", 0).execute()
        st.warning("All data cleared.")
        st.rerun()

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
    st.info("No data to show charts yet.")

# Transactions
st.subheader("Activity log")
trans = get_transactions_df(200)
if trans.empty:
    st.write("No transactions yet — they'll appear here when you add, sell, or restock items.")
else:
    items_map = inv_full.set_index('id')['name'].to_dict() if not inv_full.empty else {}
    trans['item_name'] = trans['item_id'].apply(lambda x: items_map.get(x,f"(id:{x})"))
    st.dataframe(trans[['timestamp','item_name','change','note']].rename(
        columns={'timestamp':'When','item_name':'Item','change':'Change','note':'Note'}))

# Export utilities
st.sidebar.markdown("---")
with st.sidebar.expander("Export / Backup 💾"):
    invb = get_inventory_df()
    towrite = io.StringIO()
    invb.to_csv(towrite,index=False)
    b = towrite.getvalue().encode()
    st.download_button("Download inventory CSV",data=b,file_name="inventory.csv",mime="text/csv")

    tr = get_transactions_df(1000)
    towrite = io.StringIO()
    tr.to_csv(towrite,index=False)
    b = towrite.getvalue().encode()
    st.download_button("Download transactions CSV",data=b,file_name="transactions.csv",mime="text/csv")

# Sidebar: Import inventory CSV
st.sidebar.markdown("---")
with st.sidebar.expander("Import inventory CSV 📥"):
    uploaded_file = st.file_uploader("Choose a CSV file", type=["csv"])
    if uploaded_file is not None:
        try:
            df_import = pd.read_csv(uploaded_file)
            st.write("Preview of uploaded file:")
            st.dataframe(df_import.head())

            if st.button("Import CSV into inventory"):
                for _, row in df_import.iterrows():
                    name = row.get("name")
                    category = row.get("category", "Misc")
                    qty = int(row.get("qty", 0))
                    price = float(row.get("price", 0.0))
                    restock_threshold = int(row.get("restock_threshold", 3))

                    # Check if item already exists
                    existing = supabase.table("items").select("id, qty").eq("name", name).maybe_single().execute()
                    if existing and existing.data:
                        # Update existing qty
                        item_id = existing.data["id"]
                        update_quantity(item_id, qty, note="Imported from CSV")
                    else:
                        # Add new item
                        add_item(name, category, qty, price, restock_threshold)

                st.success("CSV imported successfully!")
                st.rerun()
        except Exception as e:
            st.error(f"Failed to import CSV: {e}")

st.markdown("---")
st.caption("Built with ❤️ using Supabase for cloud sync — works across laptop and mobile!")

# https://divyaraok29.github.io/my-inventory/
# https://my-inventory.streamlit.app/
# streamlit run main.py