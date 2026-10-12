import sys,copy
from pathlib import Path
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import refresh as r
P={'shares':.8481779,'entry_price_usd':1557.71,'entry_fx_usd_per_gbp':1.32319999,'capital_gbp':1000,'invested_gbp':998.5,'fx_fee_gbp':1.5,'entry_at':'2026-10-12T10:47:00Z'}
def sample(ts,prices):return {'timestamp':ts,'indicators':{'quote':[{'close':prices}], 'adjclose':[{'adjclose':prices}]},'meta':{'currency':'USD','exchangeTimezoneName':'America/New_York','regularMarketTime':ts[-1],'regularMarketPrice':prices[-1]}}
def test_confirmed_fill_and_fee_reconcile():
 v=r.value(P,1557.71,1.32319999)
 assert v['value_gbp']==pytest.approx(998.50000498,abs=.0001)
 assert v['net_pnl_gbp']==pytest.approx(-1.49999502,abs=.0001)
 assert P['entry_price_usd']*.65==pytest.approx(1012.5115)
 assert v['stock_pnl_gbp']+v['fx_and_rounding_pnl_gbp']-1.5==pytest.approx(v['net_pnl_gbp'])
def test_fx_is_not_ignored():
 assert r.value(P,1557.71,1.4)['value_gbp']<r.value(P,1557.71,1.3)['value_gbp']
def test_benchmark_uses_completed_bar_without_future_price():
 t=r.epoch(P['entry_at']);j=sample([t-120,t-60,t,t+60],[770,780,999,1000]);b=r.make_baseline(P,j)
 assert b['price_usd']==780
 assert b['shares']*b['price_usd']/b['fx']==pytest.approx(1000)
 assert r.epoch(b['at'])<=t
 assert b['approximate']
def test_benchmark_refuses_stale_baseline():
 t=r.epoch(P['entry_at'])
 with pytest.raises(ValueError):r.make_baseline(P,sample([t-3600],[780]))
def test_quote_uses_last_positive_dated_observation():
 t=r.epoch('2026-10-12T10:55:00Z');j=sample([t-60,t,t+60],[1540,1557,None]);q=r.last_quote(j)
 assert q['price']==1557 and q['at']==r.iso(t)
 assert q['session']=='extended hours'
def test_empty_or_invalid_quotes_refuse():
 with pytest.raises(ValueError):r.last_quote(sample([1,2],[None,-1]))
def test_rank_uses_adjusted_december_close():
 j=sample([r.epoch(d+'T15:00:00Z') for d in ['2025-12-30','2025-12-31','2026-01-02','2026-10-09']],[10,12,15,18]);j['indicators']['adjclose'][0]['adjclose']=[8,10,12,20]
 row=r.rank_candidate({'symbol':'X'},j,2026)
 assert row['return']==1 and row['base_date']=='2025-12-31' and row['as_of']=='2026-10-09'
def test_partial_listing_excluded():
 j=sample([r.epoch('2026-02-01T15:00:00Z')],[10])
 with pytest.raises(ValueError):r.rank_candidate({'symbol':'X'},j,2026)
def test_failed_quotes_keep_original_timestamps(monkeypatch,tmp_path):
 monkeypatch.setattr(r,'DATA',tmp_path)
 p={**P,'stop_fraction':.35};r.write('position.json',p)
 t=r.epoch('2026-10-12T10:55:00Z');quotes={s:r.last_quote(sample([t],[v])) for s,v in [('SNDK',1557),('SPY',779),('GBPUSD=X',1.3232)]}
 baseline={'price_usd':779,'at':P['entry_at'],'entry_at':P['entry_at'],'fx':P['entry_fx_usd_per_gbp'],'shares':1000*P['entry_fx_usd_per_gbp']/779}
 r.write('live.json',{'quotes':quotes,'benchmark_entry':baseline,'observations':[]})
 monkeypatch.setattr(r,'chart',lambda *a,**k:(_ for _ in ()).throw(RuntimeError('feed unavailable')))
 data=r.fetch_live()
 assert data['quotes']==quotes
 assert len(data['errors'])>=3
 assert all(q['at']==r.iso(t) for q in data['quotes'].values())
def test_membership_failure_retains_leaders(monkeypatch,tmp_path):
 monkeypatch.setattr(r,'DATA',tmp_path)
 r.write('leaders.json',{'leaders':[{'symbol':'MRNA'}],'updated_at':'2026-10-09T00:00:00Z'})
 monkeypatch.setattr(r,'members',lambda:(_ for _ in ()).throw(RuntimeError('offline')))
 r.fetch_ranking();j=r.read('leaders.json',{})
 assert j['leaders'][0]['symbol']=='MRNA' and j['updated_at']=='2026-10-09T00:00:00Z'
 assert j['errors']

def test_dividend_factor_updates_with_entry_adjustment(monkeypatch,tmp_path):
 monkeypatch.setattr(r,'DATA',tmp_path);r.write('position.json',{**P,'stop_fraction':.35})
 t=r.epoch('2026-10-15T15:00:00Z');monkeypatch.setattr(r.time,'time',lambda:t+60);quotes={s:r.last_quote(sample([t],[v])) for s,v in [('SNDK',1557.71),('SPY',780),('GBPUSD=X',P['entry_fx_usd_per_gbp'])]}
 b={'price_usd':780,'at':P['entry_at'],'entry_at':P['entry_at'],'fx':P['entry_fx_usd_per_gbp'],'shares':1000*P['entry_fx_usd_per_gbp']/780,'adjustment_factor':1.0}
 r.write('live.json',{'quotes':quotes,'benchmark_entry':b})
 daily_spy=sample([r.epoch('2026-10-12T13:30:00Z'),t],[780,780]);daily_spy['indicators']['adjclose'][0]['adjclose']=[764.4,780]
 def mocked(symbol,**kw):
  if symbol=='SPY' and kw.get('interval')=='1d':return daily_spy
  if symbol=='SNDK' and kw.get('interval')=='1d':raise RuntimeError('No fixture for price risk history')
  return sample([t],[quotes[symbol]['price']])
 monkeypatch.setattr(r,'chart',mocked)
 data=r.fetch_live()
 assert data['benchmark_dividend_factor']==pytest.approx(1/.98)
 assert data['benchmark_value_gbp']==pytest.approx(1000/.98)
 assert data['benchmark_entry']['adjustment_factor']==pytest.approx(.98)
