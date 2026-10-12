"""Dated free quotes, persisted observations and current-member YTD rankings."""
from __future__ import annotations
import argparse, bisect, concurrent.futures, io, json, math, os, time
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote
import requests

ROOT=Path(__file__).resolve().parents[1]
DATA=ROOT/'site/data'
HEADERS={'User-Agent':'Mozilla/5.0 TheAnnualResearch/1.0'}
MEMBERS_URL='https://en.wikipedia.org/wiki/List_of_S%26P_500_companies'

def stamp():return datetime.now(timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def epoch(s):return int(datetime.fromisoformat(s.replace('Z','+00:00')).timestamp())
def iso(t):return datetime.fromtimestamp(t,timezone.utc).isoformat(timespec='seconds').replace('+00:00','Z')
def read(name,default):
    p=DATA/name
    return json.loads(p.read_text()) if p.exists() else default

def write(name,value):
    p=DATA/name;p.parent.mkdir(parents=True,exist_ok=True)
    tmp=p.with_suffix('.tmp');tmp.write_text(json.dumps(value,ensure_ascii=False,allow_nan=False,separators=(',',':'))+'\n');os.replace(tmp,p)

def chart(symbol,interval='5m',period='5d',start=None):
    params={'interval':interval,'includePrePost':'true','events':'div,splits'}
    if start is None:params['range']=period
    else:params.update(period1=start,period2=int(time.time())+60)
    for attempt in range(3):
        try:
            r=requests.get('https://query1.finance.yahoo.com/v8/finance/chart/'+quote(symbol,safe=''),params=params,headers=HEADERS,timeout=25)
            r.raise_for_status();j=r.json()['chart']
            if j.get('error') or not j.get('result'):raise ValueError(str(j.get('error')))
            return j['result'][0]
        except (requests.RequestException,ValueError,KeyError):
            if attempt==2:raise
            time.sleep(.5*(attempt+1))

def points(j,adjusted=False):
    ts=j.get('timestamp',[])
    q=j['indicators'].get('adjclose',[{}])[0].get('adjclose') if adjusted else None
    q=q or j['indicators']['quote'][0]['close']
    return [(int(t),float(p)) for t,p in zip(ts,q) if p is not None and math.isfinite(p) and p>0 and t<=time.time()+5]

def last_quote(j):
    a=points(j)
    if not a:raise ValueError('No positive dated quote')
    t,p=a[-1];meta=j['meta'];zone=meta.get('exchangeTimezoneName','UTC')
    from zoneinfo import ZoneInfo
    local=datetime.fromtimestamp(t,ZoneInfo(zone))
    hour=local.hour+local.minute/60
    session='regular' if 9.5<=hour<16 and local.weekday()<5 else 'extended hours'
    if zone=='Europe/London':session='FX market'
    return {'price':p,'at':iso(t),'currency':meta.get('currency'),'session':session,'source':'Yahoo Finance','interval':'5m','regular_close':meta.get('regularMarketPrice'),'regular_at':iso(meta['regularMarketTime']) if meta.get('regularMarketTime') else None}

def before(a,t):
    i=bisect.bisect_right([x[0] for x in a],t)-1
    return a[i] if i>=0 else None

def value(position,price,fx):
    actual=position['shares']*price/fx
    invested=position['invested_gbp']
    stock=invested*(price/position['entry_price_usd']-1)
    # exact reconciliation includes broker rounded fill residual.
    currency=actual-invested-stock
    return {'value_gbp':actual,'net_pnl_gbp':actual-position['capital_gbp'],'net_return':actual/position['capital_gbp']-1,'stock_pnl_gbp':stock,'fx_and_rounding_pnl_gbp':currency,'fee_gbp':position['fx_fee_gbp']}

def make_baseline(position,minute_chart):
    # Completed 1-minute bar before the fill. Never use a bar closing after entry.
    entry=epoch(position['entry_at']);a=[(t+60,p) for t,p in points(minute_chart)]
    chosen=before(a,entry)
    if not chosen or entry-chosen[0]>600:raise ValueError('No SPY completed minute within ten minutes before entry')
    t,p=chosen
    return {'price_usd':p,'at':iso(t),'entry_at':position['entry_at'],'fx':position['entry_fx_usd_per_gbp'],'capital_gbp':1000,'shares':1000*position['entry_fx_usd_per_gbp']/p,'source':'Yahoo completed 1-minute SPY bar at or before the trade','approximate':True,'fee_gbp':0}

def daily(symbol,start):return chart(symbol,interval='1d',start=start)

def fetch_live():
    old=read('live.json',{});position=read('position.json',{});errors=[]
    quotes=old.get('quotes',{})
    with concurrent.futures.ThreadPoolExecutor(max_workers=3) as pool:
        jobs={pool.submit(chart,s):s for s in ['SNDK','SPY','GBPUSD=X']}
        for f in concurrent.futures.as_completed(jobs):
            symbol=jobs[f]
            try:quotes[symbol]=last_quote(f.result())
            except Exception as exc:errors.append(symbol+': '+str(exc)[:180])
    baseline=old.get('benchmark_entry')
    if not baseline:
        try:baseline=make_baseline(position,chart('SPY',interval='1m',period='5d'))
        except Exception as exc:errors.append('Benchmark entry: '+str(exc)[:180])
    data={**old,'updated_at':stamp(),'position':position,'quotes':quotes,'benchmark_entry':baseline,'errors':errors}
    if all(s in quotes for s in ['SNDK','SPY','GBPUSD=X']):
        s,spy,fx=[quotes[s] for s in ['SNDK','SPY','GBPUSD=X']]
        data['valuation']={**value(position,s['price'],fx['price']),'as_of':s['at'],'fx_at':fx['at']}
        if baseline:
            data['benchmark_value_gbp']=baseline['shares']*spy['price']/fx['price']
        # Persist original source stamps, never label retained prices as fresh.
        obs=old.get('observations',[])
        entry_epoch=epoch(position['entry_at'])
        if not obs:obs=[{'at':position['entry_at'],'value':position['invested_gbp'],'benchmark':1000,'price':position['entry_price_usd'],'fx':position['entry_fx_usd_per_gbp']}]
        at=min(s['at'],spy['at'],fx['at'])
        if epoch(at)>=entry_epoch:
            row={'at':at,'value':data['valuation']['value_gbp'],'benchmark':data.get('benchmark_value_gbp'),'price':s['price'],'fx':fx['price'],'quote_at':s['at'],'benchmark_at':spy['at'],'fx_at':fx['at']}
            if at>obs[-1]['at']:obs.append(row)
        data['observations']=obs
        data['post_entry_high']=max(o['price'] for o in obs)
        data['stop_usd']=position['entry_price_usd']*(1-position['stop_fraction'])
        data['observed_stop_breach']=any(o['price']<=data['stop_usd'] for o in obs)
    # Entry date stays fixed. Re-read its adjusted factor after each new dividend.
    if baseline:
        try:
            j=daily('SPY',epoch('2026-10-01T00:00:00Z'))
            raw=points(j);adj=points(j,True);adj_map=dict(adj)
            from zoneinfo import ZoneInfo
            entry_day=position['entry_at'][:10]
            selected=[(t,p) for t,p in raw if datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat()==entry_day]
            if selected:
                t,p=selected[0];factor=adj_map[t]/p
                latest=raw[-1][0];latestfactor=adj_map[latest]/raw[-1][1]
                baseline['adjustment_factor']=factor
                reinvestment=latestfactor/factor
                data['benchmark_value_gbp']=baseline['shares']*quotes['SPY']['price']/quotes['GBPUSD=X']['price']*reinvestment
                if data.get('observations') and data['observations'][-1].get('benchmark_at')==quotes['SPY']['at']:data['observations'][-1]['benchmark']=data['benchmark_value_gbp']
                data['benchmark_dividend_factor']=reinvestment
        except Exception as exc:errors.append('Dividend adjustment: '+str(exc)[:180])
    try:
        j=daily('SNDK',epoch('2025-12-20T00:00:00Z'))
        q=j['indicators']['quote'][0]
        history=[]
        from zoneinfo import ZoneInfo
        for i,t in enumerate(j.get('timestamp',[])):
            if t>time.time()+5:continue
            d=datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat()
            if d<'2026-01-01':continue
            c=q['close'][i];hi=q['high'][i];lo=q['low'][i]
            if c and hi and lo:history.append({'date':d,'close':c,'high':hi,'low':lo})
        if history:
            data['price_history']=history
            data['year_high']=max(r['high'] for r in history)
            annual=read('backtest.json',{}).get('annual_position',{})
            if annual:
                breached=[r['date'] for r in history if r['low']<=annual['stop']]
                data['annual_rule']={**annual,'as_of':history[-1]['date'],'stop_date':breached[0] if breached else annual.get('stop_date'),'held':'Cash' if breached else 'SNDK'}
            # Subsequent completed daily bars supplement observed snapshots.
            later=[r for r in history if r['date']>position['entry_at'][:10]]
            data['post_entry_high']=max([data.get('post_entry_high',position['entry_price_usd'])]+[r['high'] for r in later])
            if any(r['low']<=data['stop_usd'] for r in later):data['observed_stop_breach']=True
        intraday=chart('SNDK')
        q=intraday['indicators']['quote'][0]
        lows=[q['low'][i] for i,t in enumerate(intraday.get('timestamp',[])) if t>=epoch(position['entry_at']) and t<=time.time()+5 and q['low'][i] is not None]
        highs=[q['high'][i] for i,t in enumerate(intraday.get('timestamp',[])) if t>=epoch(position['entry_at']) and t<=time.time()+5 and q['high'][i] is not None]
        if highs:data['post_entry_high']=max(data.get('post_entry_high',0),max(highs))
        if any(p<=data['stop_usd'] for p in lows):data['observed_stop_breach']=True
    except Exception as exc:errors.append('Stop history: '+str(exc)[:180])
    write('live.json',data)
    print('Live',data.get('valuation',{}).get('value_gbp'),'errors',len(errors))
    return data

def members():
    import pandas as pd
    r=requests.get(MEMBERS_URL,headers=HEADERS,timeout=30);r.raise_for_status()
    tables=pd.read_html(io.StringIO(r.text));table=next(t for t in tables if 'Symbol' in t.columns and 'Security' in t.columns)
    rows=[{'symbol':str(r['Symbol']).replace('.','-'),'name':str(r['Security']),'sector':str(r['GICS Sector'])} for _,r in table.iterrows()]
    if not 490<=len(rows)<=520:raise ValueError('Unexpected constituent count')
    return rows

def rank_candidate(member,j,year):
    from zoneinfo import ZoneInfo
    a=points(j,True)
    rows=[(datetime.fromtimestamp(t,ZoneInfo('America/New_York')).date().isoformat(),p) for t,p in a]
    baseline=[(d,p) for d,p in rows if d<str(year)+'-01-01']
    current=[(d,p) for d,p in rows if d>=str(year)+'-01-01']
    if not baseline or not current:raise ValueError('Missing previous-year close or YTD history')
    bd,bp=baseline[-1];d,p=current[-1]
    if bd<str(year-1)+'-12-28':raise ValueError('Stale year-end baseline')
    return {**member,'return':p/bp-1,'base_date':bd,'as_of':d,'basis':'Adjusted close, modelled total return','path':[{'date':d,'return':v/bp-1} for d,v in current]}

def fetch_ranking():
    old=read('leaders.json',{});year=datetime.now(timezone.utc).year
    try:universe=members()
    except Exception as exc:
        write('leaders.json',{**old,'last_attempt':stamp(),'errors':['Membership refresh: '+str(exc)[:180]]});return
    valid=[];errors=[];start=epoch(f'{year-1}-12-20T00:00:00Z')
    def get(m):return rank_candidate(m,daily(m['symbol'],start),year)
    with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
        jobs={pool.submit(get,m):m for m in universe}
        for f in concurrent.futures.as_completed(jobs):
            m=jobs[f]
            try:valid.append(f.result())
            except Exception as exc:errors.append({'symbol':m['symbol'],'reason':str(exc)[:160]})
    # A frozen date avoids comparing Friday quotes with Thursday returns.
    if not valid:
        write('leaders.json',{**old,'last_attempt':stamp(),'errors':errors});return
    from collections import Counter
    counts=Counter(v['as_of'] for v in valid);common=max(counts,key=lambda d:(counts[d],d))
    aligned=[]
    for v in valid:
        if v['as_of']!=common:errors.append({'symbol':v['symbol'],'reason':'Different latest session: '+v['as_of']});continue
        aligned.append(v)
    aligned.sort(key=lambda r:(-r['return'],r['symbol']))
    # Preserve an earlier successful scan when coverage collapses.
    if len(aligned)<int(len(universe)*.9):
        write('leaders.json',{**old,'last_attempt':stamp(),'errors':errors,'refresh_error':'Coverage below 90%, previous leaders retained'});return
    write('leaders.json',{'updated_at':stamp(),'year':year,'as_of':common,'universe_as_of':stamp(),'universe_source':MEMBERS_URL,'universe_count':len(universe),'eligible_count':len(aligned),'errors':errors,'leaders':aligned[:5],'rankings':[{k:v for k,v in a.items() if k!='path'} for a in aligned]})
    print('Ranked',len(aligned),'/',len(universe),'through',common,[(r['symbol'],round(r['return']*100,2)) for r in aligned[:5]])

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--leaders',action='store_true');args=parser.parse_args()
    fetch_live()
    old=read('leaders.json',{})
    if args.leaders or not old.get('leaders') or old.get('updated_at','')[:10]!=stamp()[:10]:fetch_ranking()
