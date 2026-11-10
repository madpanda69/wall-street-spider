import re
from datetime import datetime, timezone
import requests
import pandas as pd
import streamlit as st
import plotly.express as px

st.set_page_config(page_title='Wall Street Spider PRO',page_icon='🕷️',layout='wide',initial_sidebar_state='collapsed')
st.markdown('''<style>.stApp{background:#0b1220;color:#eef2ff}.block-container{max-width:1050px;padding-top:1.4rem}div.stButton>button[kind="primary"],div.stFormSubmitButton>button[kind="primary"]{background:#e34b65;color:white;border:0;font-weight:800;min-height:3rem}h1,h2,h3{color:#f1f5f9}div[data-testid="stMetric"]{background:#172338;padding:14px;border-radius:12px}div[data-testid="stMetricLabel"]{color:#cbd5e1}</style>''',unsafe_allow_html=True)
st.title('🕷️ Wall Street Spider PRO')
st.caption('⚡ Quantum Intelligence Edition · SEC-powered research · No account, API key, or paid AI required')
st.info('Quantum Intelligence is a brand name for transparent, rule-based financial analysis — not quantum computing, generative AI, price prediction, or investment advice.')
HEAD={'User-Agent':'Personal WallStreetSpider Research support contact: wallstreetspider-research@example.com','Accept-Encoding':'gzip, deflate'}
@st.cache_data(ttl=86400,show_spinner=False)
def directory():
 r=requests.get('https://www.sec.gov/files/company_tickers.json',headers=HEAD,timeout=25);r.raise_for_status()
 return {v['ticker'].upper():v for v in r.json().values()}
@st.cache_data(ttl=3600,show_spinner=False)
def facts_for(cik):
 r=requests.get(f'https://data.sec.gov/api/xbrl/companyfacts/CIK{int(cik):010d}.json',headers=HEAD,timeout=30);r.raise_for_status();return r.json()
TAGS={
 'Revenue':['RevenueFromContractWithCustomerExcludingAssessedTax','RevenueFromContractWithCustomerIncludingAssessedTax','Revenues','SalesRevenueNet'],
 'Net income':['NetIncomeLoss'],'Operating income':['OperatingIncomeLoss'],
 'Operating cash flow':['NetCashProvidedByUsedInOperatingActivities'],
 'Capital expenditures':['PaymentsToAcquirePropertyPlantAndEquipment'],
 'Assets':['Assets'],'Liabilities':['Liabilities'],
 'Cash':['CashAndCashEquivalentsAtCarryingValue'],
 'Long-term debt':['LongTermDebtNoncurrent','LongTermDebt'],
}
FLOWS={'Revenue','Net income','Operating income','Operating cash flow','Capital expenditures'}
def series_for(facts,label,period):
 us=facts.get('facts',{}).get('us-gaap',{})
 today=pd.Timestamp.now(tz='UTC').tz_localize(None).normalize()
 for tag in TAGS[label]:
  obj=us.get(tag,{});vals=obj.get('units',{}).get('USD',[]);rows=[]
  for x in vals:
   if x.get('form') not in (('10-K',) if period=='Annual' else ('10-Q',)):continue
   if not all(k in x for k in ('end','filed','val')):continue
   try:end=pd.Timestamp(x['end']);filed=pd.Timestamp(x['filed'])
   except (ValueError,TypeError):continue
   if end>today or filed>today:continue
   if label in FLOWS:
    if 'start' not in x:continue
    days=(end-pd.Timestamp(x['start'])).days
    if not ((330<=days<=380) if period=='Annual' else (70<=days<=110)):continue
   elif period=='Annual' and x.get('form')!='10-K':continue
   rows.append((end,filed,float(x['val'])))
  if rows:
   best={}
   for end,filed,value in rows:
    if end not in best or filed>best[end][0]:best[end]=(filed,value)
   return pd.Series({d:v[1] for d,v in sorted(best.items())},dtype=float).tail(8)
 return pd.Series(dtype=float)
def load(ticker,period):
 symbol=ticker.strip().upper()
 if not re.fullmatch(r'[A-Z0-9.\-]{1,12}',symbol):raise ValueError('Enter a ticker such as COST or NVDA.')
 entry=directory().get(symbol) or directory().get(symbol.replace('.','-'))
 if not entry:raise ValueError(f'{symbol} was not found in the SEC ticker directory.')
 facts=facts_for(entry['cik_str'])
 return entry,{key:series_for(facts,key,period) for key in TAGS}
def last(s):return None if s.empty else float(s.iloc[-1])
def aligned_ratio(a,b):
 common=a.index.intersection(b.index)
 if len(common)==0:return None
 x=float(a.loc[common[-1]]);y=float(b.loc[common[-1]])
 return x/y if y else None
def growth(s):
 if len(s)<2:return None
 a,b=float(s.iloc[-2]),float(s.iloc[-1]);return (b/a-1) if a>0 else None
def fmt(v):
 if v is None:return 'N/A'
 if abs(v)>=1e12:return f'${v/1e12:,.2f}T'
 if abs(v)>=1e9:return f'${v/1e9:,.2f}B'
 if abs(v)>=1e6:return f'${v/1e6:,.1f}M'
 return f'${v:,.0f}'
def pct(v):return 'N/A' if v is None else f'{v:.1%}'
def assessment(s):
 rg=growth(s['Revenue']);margin=aligned_ratio(s['Net income'],s['Revenue']);liab=aligned_ratio(s['Liabilities'],s['Assets']);cash=last(s['Operating cash flow']);capex=last(s['Capital expenditures'])
 fcf=cash-abs(capex) if cash is not None and capex is not None else None
 checks=[('Revenue growth',rg,lambda x:x>0,'Growing revenue','Revenue not growing'),('Profit margin',margin,lambda x:x>0.10,'Margin above 10%','Margin at or below 10%'),('Liabilities / assets',liab,lambda x:x<0.65,'Liabilities below 65% of assets','Liabilities at least 65% of assets'),('Operating cash flow',cash,lambda x:x>0,'Positive operating cash flow','Nonpositive operating cash flow'),('Free cash flow proxy',fcf,lambda x:x>0,'Positive operating cash flow less capex','Nonpositive operating cash flow less capex')]
 valid=[(name,value,test,good,bad) for name,value,test,good,bad in checks if value is not None]
 score=None if len(valid)<3 else round(100*sum(test(value) for _,value,test,_,_ in valid)/len(valid))
 notes=[('✅ ' if test(value) else '⚠️ ')+(good if test(value) else bad) for _,value,test,good,bad in valid]
 return score,notes,{'Revenue growth':rg,'Net margin':margin,'Liabilities / assets':liab,'Free cash flow proxy':fcf},len(valid)
def draw_report(symbol,entry,s,period):
 st.success(f"Report ready: {entry['title']} ({symbol})")
 st.caption(f"SEC EDGAR company facts · CIK {int(entry['cik_str']):010d} · Retrieved {datetime.now(timezone.utc):%Y-%m-%d %H:%M} UTC · USD")
 cols=st.columns(2)
 for i,key in enumerate(['Revenue','Net income','Operating cash flow','Assets']):cols[i%2].metric(key,fmt(last(s[key])))
 score,notes,ratios,count=assessment(s)
 st.subheader('⚡ Quantum Intelligence health check')
 if score is None:st.warning('Insufficient comparable figures for a score. No score is better than a misleading score.')
 else:
  st.metric('Financial checklist score',f'{score}/100');st.progress(score/100)
  st.caption(f'Equal-weight checklist: {count} available tests, each pass earns equal points. Not a buy/sell rating. Thresholds are illustrative and may not fit banks, insurers, or every industry.')
 for note in notes:st.write(note)
 a,b,c=st.columns(3);a.metric('Revenue growth',pct(ratios['Revenue growth']));b.metric('Net margin',pct(ratios['Net margin']));c.metric('Liabilities / assets',pct(ratios['Liabilities / assets']))
 st.caption('Growth compares the last two available periods, not necessarily the same fiscal period. Ratios only use matching period-end dates; missing values remain N/A.')
 st.subheader('📊 Financial trends')
 for key in ['Revenue','Net income','Operating cash flow']:
  data=s[key]
  if not data.empty:
   df=pd.DataFrame({'Period':data.index.strftime('%Y-%m-%d'),'USD billions':data.values/1e9})
   fig=px.bar(df,x='Period',y='USD billions',title=key,template='plotly_dark',color_discrete_sequence=['#7184ff'])
   fig.update_layout(paper_bgcolor='#0b1220',plot_bgcolor='#0b1220',margin=dict(t=55,b=20),xaxis_tickangle=-35)
   st.plotly_chart(fig,use_container_width=True)
 st.subheader('📥 Export the numbers')
 rows=[{'Metric':k,'Period end':v.index[-1].date().isoformat(),'USD':round(float(v.iloc[-1]),2)} for k,v in s.items() if not v.empty]
 if rows:
  df=pd.DataFrame(rows);st.dataframe(df,hide_index=True,use_container_width=True)
  st.download_button('Download CSV report',df.to_csv(index=False).encode(),file_name=f'{symbol}_{period.lower()}_spider_pro.csv',mime='text/csv')
 st.markdown(f"[Open original SEC filings](https://www.sec.gov/edgar/browse/?CIK={int(entry['cik_str'])}&owner=exclude)")
 st.caption('XBRL tags can vary by issuer. Debt here is long-term debt only, not total borrowings. Free cash flow is a simple proxy. Quarterly figures use standalone ~3-month periods and may be missing. Figures are not independently audited by this app.')
mode=st.radio('Choose what Spider should do',['🕷️ Analyze','⚖️ Compare','🔎 Scan'],horizontal=True)
if mode=='🕷️ Analyze':
 with st.form('analyze'):
  symbol=st.text_input('Stock ticker',value='COST',placeholder='COST, AAPL, NVDA').strip().upper()
  period=st.selectbox('Financial report',['Annual','Quarterly'])
  run=st.form_submit_button('🕷️ ANALYZE STOCK',type='primary',use_container_width=True)
 if run:
  try:
   with st.spinner('Reading official SEC data…'):entry,s=load(symbol,period)
   draw_report(symbol,entry,s,period)
  except requests.HTTPError as e:st.error(f'SEC returned HTTP {e.response.status_code}. SEC may block cloud hosting; retry later.')
  except (requests.RequestException,ValueError,KeyError,TypeError) as e:st.error(f'Could not complete analysis: {e}')
elif mode=='⚖️ Compare':
 with st.form('compare'):
  symbols=st.text_input('Compare tickers (2–3, separated by commas)','COST,WMT').upper()
  run=st.form_submit_button('⚖️ COMPARE COMPANIES',type='primary',use_container_width=True)
 if run:
  picks=list(dict.fromkeys(x.strip() for x in symbols.split(',') if x.strip()))
  if not 2<=len(picks)<=3:st.warning('Enter 2 or 3 different tickers.')
  else:
   rows=[]
   for symbol in picks:
    try:
     with st.spinner(f'Reading {symbol}…'):entry,s=load(symbol,'Annual')
     score,notes,ratios,count=assessment(s)
     rows.append({'Ticker':symbol,'Company':entry['title'],'Revenue':fmt(last(s['Revenue'])),'Net income':fmt(last(s['Net income'])),'Revenue growth':pct(ratios['Revenue growth']),'Net margin':pct(ratios['Net margin']),'Checklist score':score if score is not None else 'N/A'})
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:st.warning(f'{symbol}: {e}')
   if rows:
    st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
    st.caption('Comparisons are based on latest available annual filings, which may have different fiscal year ends. Scores are educational checklists, not investment recommendations.')
else:
 st.write('Scan a small starter watchlist for companies with positive revenue growth and operating cash flow. This is not a full-market scanner.')
 with st.form('scan'):
  watch=st.text_input('Watchlist (up to 5 tickers, comma-separated)','AAPL,MSFT,NVDA,COST,WMT').upper()
  run=st.form_submit_button('🔎 SCAN WATCHLIST',type='primary',use_container_width=True)
 if run:
  picks=list(dict.fromkeys(x.strip() for x in watch.split(',') if x.strip()))
  if not 1<=len(picks)<=5:st.warning('Choose 1 to 5 tickers to avoid overloading SEC servers.')
  else:
   rows=[]
   for symbol in picks:
    try:
     with st.spinner(f'Scanning {symbol}…'):entry,s=load(symbol,'Annual')
     rg=growth(s['Revenue']);cash=last(s['Operating cash flow']);score,_,_,_=assessment(s)
     rows.append({'Ticker':symbol,'Company':entry['title'],'Revenue growth':pct(rg),'Operating cash flow':fmt(cash),'Checklist score':score if score is not None else 'N/A','Passes scan':('Yes' if rg is not None and cash is not None and rg>0 and cash>0 else 'No / unknown')})
    except (requests.RequestException,ValueError,KeyError,TypeError) as e:st.warning(f'{symbol}: {e}')
   if rows:st.dataframe(pd.DataFrame(rows),hide_index=True,use_container_width=True)
   st.caption('Scan rules are simplistic and not proof of quality or future returns. SEC data may be delayed and issuers report on different schedules.')
st.divider()
st.caption('Personal research only · Public SEC EDGAR data · Not financial advice · No brokerage connection or automatic trading')
