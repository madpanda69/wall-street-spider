import streamlit as st
import requests
import pandas as pd
import plotly.express as px
from datetime import datetime

st.set_page_config(page_title='Wall Street Spider', page_icon='🕷️', layout='wide')
st.markdown('''<style>.stApp{background:#0b1220;color:#f8fafc}div.stButton>button[kind="primary"]{background:#16a34a;border:0;font-weight:700}h1,h2,h3{color:#e2e8f0}</style>''', unsafe_allow_html=True)
st.title('🕷️ Wall Street Spider')
st.caption('Your one-button SEC financial report crawler • Free public filings • No trading or investment advice')

HEADERS={'User-Agent':'WallStreetSpider Personal Research contact spider-research@example.com','Accept-Encoding':'gzip, deflate','Host':'www.sec.gov'}

@st.cache_data(ttl=86400, show_spinner=False)
def tickers():
    r=requests.get('https://www.sec.gov/files/company_tickers.json',headers={k:v for k,v in HEADERS.items() if k!='Host'},timeout=25)
    r.raise_for_status()
    return {x['ticker'].upper():x for x in r.json().values()}

@st.cache_data(ttl=3600, show_spinner=False)
def company_facts(cik):
    r=requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{cik:010d}.json',headers={k:v for k,v in HEADERS.items() if k!='Host'},timeout=30)
    r.raise_for_status()
    return r.json()

FIELDS={
'Revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','Revenues','SalesRevenueNet','RevenueFromContractWithCustomerIncludingAssessedTax'],
'Net income':['NetIncomeLoss'],
'Operating income':['OperatingIncomeLoss'],
'Operating cash flow':['NetCashProvidedByUsedInOperatingActivities'],
'Capital expenditures':['PaymentsToAcquirePropertyPlantAndEquipment'],
'Total assets':['Assets'],
'Total liabilities':['Liabilities'],
'Cash':['CashAndCashEquivalentsAtCarryingValue'],
'Long-term debt':['LongTermDebtCurrent','LongTermDebtNoncurrent','LongTermDebt'],
}
FLOW={'Revenue','Net income','Operating income','Operating cash flow','Capital expenditures'}

def extract(facts, label, form):
    us=facts.get('facts',{}).get('us-gaap',{})
    for tag in FIELDS[label]:
        obj=us.get(tag)
        if not obj: continue
        vals=obj.get('units',{}).get('USD',[])
        records=[]
        for x in vals:
            if x.get('form') not in (['10-K'] if form=='Annual' else ['10-Q']): continue
            if not all(k in x for k in ('start','end','val','filed')) and label in FLOW: continue
            if 'end' not in x or 'val' not in x or 'filed' not in x: continue
            if label in FLOW:
                days=(pd.Timestamp(x['end'])-pd.Timestamp(x['start'])).days
                if form=='Annual' and not 330<=days<=380:continue
                if form=='Quarterly' and not 70<=days<=110:continue
            records.append(x)
        if records:
            records.sort(key=lambda x:(x['end'],x['filed']))
            latest={}
            for x in records:latest[x['end']]=x['val']
            return pd.Series(latest,dtype='float64').sort_index().tail(8)
    return pd.Series(dtype='float64')

with st.form('analyze'):
    a,b=st.columns([3,1])
    with a: symbol=st.text_input('Stock ticker',value='COST',placeholder='e.g. COST, AAPL, NVDA').strip().upper()
    with b: period=st.selectbox('Report type',['Annual','Quarterly'])
    clicked=st.form_submit_button('🕷️ ANALYZE STOCK',type='primary',use_container_width=True)

if clicked:
    if not symbol or not symbol.replace('-','').replace('.','').isalnum():
        st.error('Enter a valid stock ticker, like COST or AAPL.')
    else:
        try:
            with st.spinner('Spider is collecting official SEC filings…'):
                directory=tickers()
                match=directory.get(symbol) or directory.get(symbol.replace('.','-'))
                if not match:
                    st.error(f'No SEC company found for {symbol}. Check the ticker and try again.')
                    st.stop()
                facts=company_facts(match['cik_str'])
            st.success(f"Report ready: {match['title']} ({symbol})")
            st.caption(f"Source: SEC EDGAR XBRL company facts • CIK {match['cik_str']:010d} • Accessed {datetime.now().strftime('%Y-%m-%d %H:%M')} • USD")
            series={k:extract(facts,k,period) for k in FIELDS}
            metrics=['Revenue','Net income','Operating cash flow','Total assets']
            cols=st.columns(4)
            for col,name in zip(cols,metrics):
                s=series[name]
                col.metric(name, f'${s.iloc[-1]/1e9:,.2f}B' if not s.empty else 'N/A')
            st.subheader('Financial trends')
            for name in ['Revenue','Net income','Operating cash flow']:
                s=series[name]
                if not s.empty:
                    df=pd.DataFrame({'Period':s.index,'USD billions':s.values/1e9})
                    fig=px.bar(df,x='Period',y='USD billions',title=name,template='plotly_dark')
                    fig.update_layout(paper_bgcolor='#0b1220',plot_bgcolor='#0b1220',margin=dict(t=55,b=25))
                    st.plotly_chart(fig,use_container_width=True)
            st.subheader('Latest reported figures')
            rows=[]
            for name,s in series.items():
                if not s.empty:rows.append({'Metric':name,'Period ending':s.index[-1],'USD':int(s.iloc[-1])})
            if rows:
                table=pd.DataFrame(rows)
                st.dataframe(table,hide_index=True,use_container_width=True,column_config={'USD':st.column_config.NumberColumn(format='$%d')})
                st.download_button('⬇️ Download report (CSV)',data=table.to_csv(index=False).encode(),file_name=f'{symbol}_{period.lower()}_spider.csv',mime='text/csv')
            else:st.warning('This company does not provide compatible standard SEC XBRL figures for this report type.')
            st.info('Figures may be missing or differ from company presentations because SEC XBRL tags and reporting periods vary. Quarterly charts use standalone three-month periods only. This is research data, not a buy/sell signal.')
            st.markdown(f"[View official SEC company filings](https://www.sec.gov/edgar/browse/?CIK={match['cik_str']}&owner=exclude)")
        except requests.HTTPError as e:
            st.error(f'SEC data request was blocked or unavailable ({e.response.status_code}). Try again later. Some hosting services are restricted by SEC.')
        except (requests.RequestException,ValueError,KeyError) as e:
            st.error(f'Could not load the report: {e}. Check your connection and retry.')
else:
    st.markdown('### How it works')
    st.write('Type a ticker, choose annual or quarterly, and press **ANALYZE STOCK**. The spider collects financial facts from official US SEC filings, creates charts, and lets you download the numbers.')
    st.caption('Best for US-listed companies that file standard SEC XBRL statements. No login or brokerage account needed.')
