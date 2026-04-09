import streamlit as st
import gspread
from google.oauth2.service_account import Credentials
from datetime import datetime
import json
import os

st.set_page_config(
    page_title="資金調達 審査スコアリング",
    page_icon="📊",
    layout="centered"
)

st.markdown("""
<style>
.main-title { font-size: 20px; font-weight: 600; color: #0F6E56; margin-bottom: 4px; }
.sub-title { font-size: 12px; color: #888; margin-bottom: 24px; }
.route-A { background: #e1f5ee; border-left: 4px solid #1D9E75; border-radius: 8px; padding: 14px 20px; color: #085041; font-weight: 600; font-size: 16px; }
.route-B { background: #eaf3de; border-left: 4px solid #639922; border-radius: 8px; padding: 14px 20px; color: #27500A; font-weight: 600; font-size: 16px; }
.route-C { background: #fcebeb; border-left: 4px solid #E24B4A; border-radius: 8px; padding: 14px 20px; color: #791F1F; font-weight: 600; font-size: 16px; }
.flag-box { background: #FAEEDA; border-left: 4px solid #EF9F27; border-radius: 8px; padding: 10px 16px; color: #633806; font-size: 14px; margin-bottom: 8px; }
.disclaimer { font-size: 11px; color: #aaa; margin-top: 24px; border-top: 1px solid #eee; padding-top: 12px; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="main-title">📊 資金調達 審査スコアリングシステム</div>', unsafe_allow_html=True)
st.markdown('<div class="sub-title">自動振分エンジン v3 ｜ Powered by Nexccess</div>', unsafe_allow_html=True)


# ── Google Sheets接続 ──────────────────────────────────
def get_sheet():
    scope = [
        "https://spreadsheets.google.com/feeds",
        "https://www.googleapis.com/auth/drive"
    ]
    try:
        if "gcp_service_account" in st.secrets:
            creds = Credentials.from_service_account_info(
                st.secrets["gcp_service_account"], scopes=scope
            )
        else:
            json_files = [f for f in os.listdir('.') if f.endswith('.json')]
            if not json_files:
                st.error("❌ JSONファイルが見つかりません")
                return None
            creds = Credentials.from_service_account_file(json_files[0], scopes=scope)
        
        client = gspread.authorize(creds)
        sheet = client.open_by_url(
            "https://docs.google.com/spreadsheets/d/1cZLM0EVl7CkIOC_yh10_m-QhuX2q0IJeoyaqC8teRs4"
        )
        return sheet.worksheet("results")
    except Exception as e:
        st.error(f"❌ Sheets接続エラー：{e}")
        return None


def save_to_sheet(ws, d, r):
    if ws is None:
        return False
    try:
        row = [
            datetime.now().strftime("%Y-%m-%d %H:%M"),
            d["company"], d["industry"],
            d["amount"], d["repayment"],
            d["purpose"], d["tax_delinquent"],
            d["sales_prev"], d["sales_curr"],
            d["op_prev"], d["dep"], d["cash"],
            d["debt"], d["equity"],
            d["exec_loan"], d["exec_lending"],
            "有" if d["real_estate"] else "無",
            "有" if d["securities"] else "無",
            d["receivable"],
            round(r["total"], 1), r["rank"], r["route"],
            round(r["eq_ratio"] * 100, 1),
            round(min(r["debt_years"], 99), 1),
            round(r["op_rate"] * 100, 2),
            ", ".join(r["flags"]) if r["flags"] else "なし"
        ]
        ws.append_row(row)
        return True
    except Exception as e:
        st.warning(f"保存エラー：{e}")
        return False


def ensure_header(ws):
    if ws is None:
        return
    try:
        first = ws.row_values(1)
        if not first:
            ws.append_row([
                "日時", "会社名", "業種",
                "希望調達額", "希望返済期間(月)",
                "資金使途", "税金滞納",
                "年商・前期", "年商・今期予測",
                "営業利益・前期", "減価償却費", "現預金残高",
                "借入総額", "純資産",
                "役員借入金", "役員貸付金",
                "不動産担保", "証券担保", "売掛先属性",
                "総合スコア", "ランク", "推奨ルート",
                "自己資本比率(%)", "債務償還年数(年)", "営業利益率(%)",
                "警告フラグ"
            ])
    except:
        pass


# ── スコアリング関数 ──────────────────────────────────
def calc_score(d):
    sp   = max(d["sales_prev"], 1)
    op   = d["op_prev"]
    dep  = d["dep"]
    debt = d["debt"]
    eq   = d["equity"]
    exl  = d["exec_loan"]
    exld = d["exec_lending"]

    real_eq    = eq + exl - exld
    eq_ratio   = real_eq / (real_eq + debt) if (real_eq + debt) > 0 else 0
    op_rate    = op / sp
    ebitda     = op + dep
    debt_years = debt / ebitda if ebitda > 0 else 99.0

    s_safety = 40.0 if eq_ratio >= 0.20 else (0.0 if eq_ratio <= 0 else (eq_ratio / 0.20) * 40)
    s_debt   = 40.0 if debt_years <= 5 else (0.0 if debt_years >= 15 else ((15 - debt_years) / 10) * 40)
    s_profit = 20.0 if op_rate >= 0.05 else (0.0 if op_rate <= 0 else (op_rate / 0.05) * 20)
    total    = s_safety + s_debt + s_profit

    tax  = d["tax_delinquent"]
    recv = d["receivable"]
    hasRE = d["real_estate"]

    if total >= 80 and not tax:
        rank, route = "A/B（High）", "A"
        comment = "優良案件。自社融資の検討を推奨します。"
    elif total >= 40:
        rank = "C/D（Middle）"
        if tax:
            route, comment = "B", "【注意】税金滞納あり：融資ルート遮断。ファクタリング検討可。"
        elif recv in ["A", "B"]:
            route, comment = "B", "売掛先優良。ファクタリングへ格上げ。"
        else:
            route, comment = "B", "Middle層。ファクタリングが適切です。"
    else:
        rank = "E（Low）"
        if hasRE and not tax:
            route, comment = "B", "不動産担保あり：ルートC→B格上げ（担保設定条件付き）。"
        else:
            route, comment = "C", "スコア低位。外部ノンバンクへの送客を推奨します。"

    if tax and total >= 80:
        route, rank = "B", "C/D（Middle）"
        comment = "【注意】税金滞納あり：高スコアだが融資ルート遮断。ファクタリング検討可。"

    flags = []
    sc  = d["sales_curr"]
    div = abs(sc - sp) / sp if sp > 0 else 0
    if div > 0.30:
        flags.append(f"業績乖離（{div*100:.0f}%）：エビデンス確認推奨")
    if debt_years * 12 < d["repayment"]:
        flags.append(f"返済期間（{d['repayment']}ヶ月）が長すぎます（リスケリスク）")
    if d["purpose"] in ["納税", "赤字補填"]:
        flags.append(f"資金使途に要注意（{d['purpose']}）")
    if tax:
        flags.append("税金滞納あり：融資ルート強制遮断")

    return {
        "total": total, "s_safety": s_safety, "s_debt": s_debt, "s_profit": s_profit,
        "rank": rank, "route": route, "comment": comment, "flags": flags,
        "eq_ratio": eq_ratio, "debt_years": debt_years, "op_rate": op_rate
    }


# ── 入力フォーム ──────────────────────────────────
with st.expander("▼ 案件基本情報", expanded=True):
    col1, col2 = st.columns(2)
    company   = col1.text_input("会社名", placeholder="例：テスト株式会社")
    industry  = col2.selectbox("業種", ["製造業","不動産業","建設業","卸売業","小売業","サービス業","飲食業","IT・通信","医療・福祉","その他"])
    col3, col4 = st.columns(2)
    years     = col3.number_input("設立年数（年）", min_value=0, value=5)
    purpose   = col4.selectbox("資金使途", ["増加運転資金","設備投資","納税","赤字補填","その他"])
    if purpose in ["納税", "赤字補填"]:
        st.warning("▲ 要注意資金使途です。追加ヒアリングを推奨します。")
    col5, col6 = st.columns(2)
    amount    = col5.number_input("希望調達額（円）", min_value=0, value=5_000_000, step=100_000)
    repayment = col6.number_input("希望返済期間（月）", min_value=1, value=36)

with st.expander("▼ 業績情報", expanded=True):
    col1, col2 = st.columns(2)
    sales_prev = col1.number_input("年商・前期実績（円）", min_value=0, value=100_000_000, step=1_000_000)
    sales_curr = col2.number_input("年商・今期予測（円）", min_value=0, value=100_000_000, step=1_000_000)
    if sales_prev > 0 and abs(sales_curr - sales_prev) / sales_prev > 0.30:
        st.warning(f"▲ 前期との乖離 {abs(sales_curr-sales_prev)/sales_prev*100:.0f}% — エビデンス確認推奨")
    col3, col4 = st.columns(2)
    op_prev   = col3.number_input("営業利益・前期実績（円）", value=5_000_000, step=100_000)
    op_curr   = col4.number_input("営業利益・今期予測（円）", value=5_000_000, step=100_000)
    col5, col6 = st.columns(2)
    dep       = col5.number_input("減価償却費（円）", min_value=0, value=0, step=100_000)
    cash      = col6.number_input("現預金残高（円）", min_value=0, value=3_000_000, step=100_000)
    col7, col8 = st.columns(2)
    debt      = col7.number_input("借入総額・有利子負債（円）", min_value=0, value=30_000_000, step=1_000_000)
    equity    = col8.number_input("純資産・自己資本（円）", value=20_000_000, step=1_000_000)
    col9, col10 = st.columns(2)
    exec_loan = col9.number_input("役員借入金（円）", min_value=0, value=0, step=100_000)
    exec_lend = col10.number_input("役員貸付金（円）", min_value=0, value=0, step=100_000)

with st.expander("▼ 保全・属性", expanded=True):
    col1, col2 = st.columns(2)
    real_estate    = col1.selectbox("不動産担保", ["無", "有"]) == "有"
    securities     = col2.selectbox("証券担保", ["無", "有"]) == "有"
    col3, col4     = st.columns(2)
    recv_raw       = col3.selectbox("売掛先属性", ["A（上場・官公庁）","B（準優良）","C（一般）","D（不明・懸念）"])
    receivable     = recv_raw[0]
    tax_raw        = col4.selectbox("税金滞納", ["無", "有"])
    tax_delinquent = tax_raw == "有"
    if tax_delinquent:
        st.error("▲ 税金滞納あり：融資ルートが強制遮断されます。")

st.markdown("---")
run = st.button("　審査を実行する　", type="primary", use_container_width=True)

if run:
    input_data = {
        "company": company, "industry": industry, "years": years,
        "purpose": purpose, "amount": amount, "repayment": repayment,
        "sales_prev": sales_prev, "sales_curr": sales_curr,
        "op_prev": op_prev, "op_curr": op_curr,
        "dep": dep, "cash": cash, "debt": debt,
        "equity": equity, "exec_loan": exec_loan, "exec_lending": exec_lend,
        "real_estate": real_estate, "securities": securities,
        "receivable": receivable, "tax_delinquent": tax_delinquent
    }
    r = calc_score(input_data)

    # Google Sheetsに保存
    ws = get_sheet()
    ensure_header(ws)
    saved = save_to_sheet(ws, input_data, r)

    st.markdown("## 審査結果")
    st.markdown(f"**{company or '（会社名未入力）'}** ／ {industry}")
    if saved:
        st.caption("✓ データを保存しました")
    st.markdown("---")

    col1, col2, col3, col4 = st.columns(4)
    col1.metric("総合スコア", f"{r['total']:.1f} 点")
    col2.metric("総合ランク", r["rank"])
    col3.metric("自己資本比率", f"{r['eq_ratio']*100:.1f} %")
    col4.metric("債務償還年数", f"{min(r['debt_years'],99):.1f} 年" if r['debt_years'] < 99 else "99年超")

    st.markdown("---")
    route_names = {"A": "ルートA：自社融資", "B": "ルートB：自社ファクタリング", "C": "ルートC：外部ノンバンク送客"}
    route_cls   = {"A": "route-A", "B": "route-B", "C": "route-C"}
    st.markdown(f'<div class="{route_cls[r["route"]]}">{route_names[r["route"]]}</div>', unsafe_allow_html=True)
    st.caption(r["comment"])
    st.markdown("---")

    st.markdown("#### スコア内訳")
    col1, col2, col3 = st.columns(3)
    col1.metric("安全性（40点満点）", f"{r['s_safety']:.1f}")
    col1.progress(r["s_safety"] / 40)
    col1.caption(f"自己資本比率 {r['eq_ratio']*100:.1f}%")
    col2.metric("返済能力（40点満点）", f"{r['s_debt']:.1f}")
    col2.progress(r["s_debt"] / 40)
    col2.caption(f"債務償還年数 {min(r['debt_years'],99):.1f}年")
    col3.metric("収益性（20点満点）", f"{r['s_profit']:.1f}")
    col3.progress(r["s_profit"] / 20)
    col3.caption(f"営業利益率 {r['op_rate']*100:.2f}%")
    st.markdown("---")

    st.markdown("#### 警告フラグ")
    if r["flags"]:
        for f in r["flags"]:
            st.markdown(f'<div class="flag-box">▲ {f}</div>', unsafe_allow_html=True)
    else:
        st.success("警告フラグなし")

    st.markdown('<div class="disclaimer">※ 本ツールの判定は一次スクリーニング用途です。最終判断は担当者の責任において行ってください。</div>', unsafe_allow_html=True)
