import copy
import importlib.util
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock
import pytest
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'scripts'))
import daily as d
NOW=datetime(2026,10,12,16,30,tzinfo=timezone.utc)
def data():
 p={'symbol':'SNDK','name':'Sandisk','shares':.8481779,'entry_price_usd':1557.71,'entry_at':'2026-10-12T10:47:00Z','capital_gbp':1000,'fx_fee_gbp':1.5,'stop_fraction':.35}
 live={'position':p,'quotes':{s:{'price':v,'at':'2026-10-12T16:00:00Z'} for s,v in [('SNDK',1500),('SPY',780),('GBPUSD=X',1.32)]},'valuation':{'value_gbp':963.84,'net_pnl_gbp':-36.16,'net_return':-.03616},'benchmark_value_gbp':1005,'post_entry_high':1600,'observed_stop_breach':False,'annual_rule':{'stop':154.297,'held':'SNDK','as_of':'2026-10-09','stop_date':None},'errors':[]}
 leaders={'year':2026,'as_of':'2026-10-09','updated_at':'2026-10-12T07:00:00Z','eligible_count':500,'universe_count':503,'leaders':[{'name':'Moderna','symbol':'MRNA','return':6.63},{'name':'Sandisk','symbol':'SNDK','return':5.66}]}
 return live,leaders

def test_matched_comparison_fee_stop_and_leader_cushion():
 live,leaders=data();subject,plain,_=d.compose(live,leaders,NOW)
 assert 'hold SNDK' in subject and '80d' in subject
 assert '£963.84' in plain and '£-41.16' in plain and '-3.62%' in plain
 assert '$1,012.51' in plain and '32.5%' in plain and '12.7%' in plain
 assert 'Moderna (MRNA)' in plain and '500 of 503' in plain

def test_breach_remains_visible_after_price_recovers_without_claiming_actual_sale():
 live,leaders=data();live['observed_stop_breach']=True
 subject,plain,_=d.compose(live,leaders,NOW)
 assert 'model stop breached' in subject
 assert 'Actual shares remain recorded until you report a sale' in plain
 assert 'January threshold $154.30' in plain

def test_current_price_at_stop_triggers_even_if_observation_flag_missing():
 live,leaders=data();live['quotes']['SNDK']['price']=1000
 assert 'model stop breached' in d.compose(live,leaders,NOW)[0]

def test_failed_stop_history_never_claims_complete_no_breach():
 live,leaders=data();live['errors']=['Stop history: offline']
 subject,plain,_=d.compose(live,leaders,NOW)
 assert 'data check needed' in subject and 'Stop history is incomplete' in plain

def test_old_prices_preserve_dates_and_warn():
 live,leaders=data();live['quotes']['SNDK']['at']='2026-10-01T12:00:00Z'
 subject,plain,_=d.compose(live,leaders,NOW)
 assert 'data check needed' in subject and '01 Oct 2026' in plain
 assert 'quote older than four days' in plain

def test_prior_year_ranking_cannot_be_new_year_selection():
 live,leaders=data();subject,plain,_=d.compose(live,leaders,datetime(2027,1,2,tzinfo=timezone.utc))
 assert 'Current-year ranking unavailable' in plain and 'If the year ended' not in plain

def test_html_escapes_source_text():
 live,leaders=data();leaders['leaders'][0]['name']='<script>bad</script>'
 _,_,rendered=d.compose(live,leaders,NOW)
 assert '<script>' not in rendered and '&lt;script&gt;' in rendered

def test_send_requires_credentials(monkeypatch):
 monkeypatch.delenv('GMAIL_APP_PASSWORD',raising=False)
 with pytest.raises(RuntimeError):d.send('test','plain','html')

def test_sender_and_recipient_and_alternative(monkeypatch):
 monkeypatch.setenv('GMAIL_APP_PASSWORD','example dummy')
 monkeypatch.setenv('GMAIL_USER','owner@example.test');monkeypatch.setenv('MAIL_TO','recipient@example.test')
 smtp=MagicMock();monkeypatch.setattr(d.smtplib,'SMTP_SSL',lambda *a,**k:smtp)
 d.send('The Annual','plain','<b>html</b>')
 msg=smtp.__enter__.return_value.send_message.call_args.args[0]
 assert msg['From']=='The Annual <owner@example.test>' and msg['To']=='recipient@example.test'
 assert msg.is_multipart() and len(msg.get_payload())==2

def test_receipt_suppresses_duplicate_and_failed_send_has_no_receipt(monkeypatch,tmp_path):
 monkeypatch.setattr(d,'ROOT',tmp_path)
 live,leaders=data();folder=tmp_path/'site/data';folder.mkdir(parents=True)
 (folder/'live.json').write_text(json.dumps(live));(folder/'leaders.json').write_text(json.dumps(leaders))
 monkeypatch.setattr(sys,'argv',['daily','--send'])
 send=MagicMock(side_effect=RuntimeError('offline'));monkeypatch.setattr(d,'send',send)
 with pytest.raises(RuntimeError):d.main()
 assert not (tmp_path/'.daily-mail/receipt.json').exists()
 send.side_effect=None;d.main();d.main()
 assert send.call_count==2
 assert (tmp_path/'.daily-mail/receipt.json').exists()
