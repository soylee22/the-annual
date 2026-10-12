"""Freeze verified lab outputs for the public research section. Run in SecondBrain."""
from pathlib import Path
import json
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT.parents[1]/'outputs/2026-10-12-last-year-winner'
a=pd.read_csv(SOURCE/'momentum-posted-endpoint-fixed35/daily.csv',parse_dates=['date']).set_index('date')
b=pd.read_csv(SOURCE/'momentum-posted-endpoint/daily.csv',parse_dates=['date']).set_index('date')
h=pd.read_csv(SOURCE/'momentum-posted-endpoint-fixed35/holdings.csv').fillna('')
curve=pd.DataFrame({'stopped':a.strategy,'unstopped':b.strategy,'benchmark':a.benchmark,'held':a.positions}).resample('W-FRI').last().dropna()
# retain exact initial and final dates alongside weekly display sampling.
curve=pd.concat([pd.DataFrame({'stopped':a.strategy.iloc[:1],'unstopped':b.strategy.iloc[:1],'benchmark':a.benchmark.iloc[:1],'held':a.positions.iloc[:1]}),curve])
curve=curve[curve.index<=a.index[-1]]
if curve.index[-1]!=a.index[-1]:curve.loc[a.index[-1]]=[a.strategy.iloc[-1],b.strategy.iloc[-1],a.benchmark.iloc[-1],a.positions.iloc[-1]]
scenarios=pd.read_csv(SOURCE/'momentum-comparison.csv').astype(object).where(lambda df:df.notna(),None).to_dict('records')
position=h[h.year==2026].iloc[0]
annual={'entry_price':float(position.entry_price),'entry_date':position.entry_date,'stop':float(position.entry_price)*.65,'stop_date':position.stop_date or None,'as_of':'2026-10-09','held':'SNDK'}
data={'as_of':'2026-10-09','start':'2004-12-31','initial':100,'curves':[{'date':d.date().isoformat(),'stop':round(r.stopped,4),'noStop':round(r.unstopped,4),'spy':round(r.benchmark,4),'held':r.held} for d,r in curve.iterrows()], 'holdings':h[['year','display_ticker','entry_date','entry_price','stop_date','exit_date','leg_return']].to_dict('records'),'comparisons':scenarios,'annual_position':annual,'notes':['Historical S&P membership, incomplete competitor prices. Posted winners are a checked replay, not certified all-member rankings.','Price returns through 2011, modelled total returns from 2012. SPY includes dividends throughout.','Exact stop fills, zero costs and cash interest. Taxes and inflation excluded.','Curves display weekly closes. Drawdown statistics use every daily close.','The common-pool momentum comparison excludes partial-year listings, including SNDK in 2025.']}
(ROOT/'site/data/backtest.json').write_text(json.dumps(data,allow_nan=False,separators=(',',':'))+'\n')
print('Exported',len(curve),'curve points and',len(h),'holding years')
