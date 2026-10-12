"""One dated daily email for The Annual. No trade execution."""
from __future__ import annotations
import argparse
import html
import json
import os
import smtplib
from datetime import datetime, date, timezone
from email.message import EmailMessage
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
LONDON = ZoneInfo('Europe/London')
SITE = 'https://soylee22.github.io/the-annual/'

def moment(value):
    return datetime.fromisoformat(value.replace('Z', '+00:00'))

def dated(value):
    if not value:
        return 'unavailable'
    return moment(value).astimezone(LONDON).strftime('%d %b %Y, %H:%M %Z')

def pct(value):
    return f'{value:+.2%}'

def compose(live, leaders, now):
    today = now.astimezone(LONDON).date()
    position = live['position']
    symbol = position['symbol']
    quotes = live.get('quotes', {})
    price = quotes.get(symbol, {}).get('price')
    stop = position['entry_price_usd'] * (1-position['stop_fraction'])
    breached = bool(live.get('observed_stop_breach')) or (price is not None and price <= stop)
    warnings = list(live.get('errors', []))
    for key in (symbol, 'SPY', 'GBPUSD=X'):
        at = quotes.get(key, {}).get('at')
        if not at:
            warnings.append(f'{key}: quote unavailable')
        elif (now - moment(at)).total_seconds() > 96*3600:
            warnings.append(f'{key}: quote older than four days')
    history_known = 'observed_stop_breach' in live and not any('Stop history' in str(e) for e in warnings)
    status = 'MODEL STOP BREACHED' if breached else ('DATA CHECK NEEDED' if warnings or not history_known else f'HOLD {symbol}')
    end = date(today.year, 12, 31)
    days = (end-today).days
    subject_state = f'hold {symbol}' if status.startswith('HOLD ') else status.lower()
    subject = f'The Annual: {subject_state}, {days}d to year-end'
    lines = [f'The Annual · personal rule: {status}', '',
        f'Holding now: {position["name"]} ({symbol}), {position["shares"]:.7f} shares.',
        f'Bought {dated(position["entry_at"])} at ${position["entry_price_usd"]:,.2f}.',
        f'£{position["capital_gbp"]:,.2f} paid, including £{position["fx_fee_gbp"]:.2f} FX fee.', '', 'Since your purchase']
    val = live.get('valuation', {})
    if val:
        lines.append(f'Your holding: £{val["value_gbp"]:,.2f} · £{val["net_pnl_gbp"]:+,.2f} ({pct(val["net_return"])}), including the entry fee.')
    else:
        lines.append('Your holding: valuation unavailable.')
    benchmark = live.get('benchmark_value_gbp')
    capital = live.get('benchmark_entry', {}).get('capital_gbp', 1000)
    if benchmark is not None:
        lines.append(f'Hypothetical S&P 500 (SPY): £{benchmark:,.2f} · {pct(benchmark/capital-1)} from £{capital:,.0f}.')
        if val:
            lines.append(f'Difference: £{val["value_gbp"]-benchmark:+,.2f} versus SPY.')
    else:
        lines.append('Hypothetical S&P 500: valuation unavailable.')
    lines += ['', 'Fixed entry stop', f'35% below your purchase: ${stop:,.2f}. This threshold does not trail the high.']
    if price is not None:
        room = 1-stop/price
        peak = max(position['entry_price_usd'], live.get('post_entry_high', position['entry_price_usd']))
        lines += [f'Observed price: ${price:,.2f} · {pct(price/position["entry_price_usd"]-1)} versus entry.',
                  f'Drawdown from the observed post-entry high: {pct(price/peak-1)}.']
        lines.append(f'Price can fall a further {room:.1%} to the stop.' if room > 0 else 'Current observed price is at or below the stop.')
    if breached:
        lines.append('An observed breach has occurred. The model moves to cash until January. Actual shares remain recorded until you report a sale.')
    elif not history_known:
        lines.append('Stop history is incomplete. A missed observation could hide a breach.')
    else:
        lines.append('No breach found in available observations. A stop sale would leave cash until January.')
    annual = live.get('annual_rule', {})
    lines += ['', 'January strategy, separate from your October entry']
    if annual:
        state = f'Cash after the {annual["stop_date"]} stop' if annual.get('stop_date') else f'{annual.get("held", symbol)} held'
        lines.append(f'{state} · January threshold ${annual["stop"]:,.2f} · data through {annual.get("as_of", "unavailable")}.')
    else:
        lines.append('January model unavailable.')
    lines += ['', f'{days} calendar days until the {today.year} year-end close.',
              'The December signal selects the stock for the first trading session of January.', '',
              f'Next-year candidates · YTD total return through {leaders.get("as_of", "unavailable")}']
    ranking = leaders.get('leaders', []) if leaders.get('year') == today.year else []
    if not ranking:
        lines.append('Current-year ranking unavailable. No provisional replacement can be stated.')
    for i, row in enumerate(ranking[:5], 1):
        lines.append(f'{i}. {row["name"]} ({row["symbol"]}) · {pct(row["return"])}')
    if ranking:
        leader = ranking[0]
        lines.append(f'If the year ended at that close: {leader["name"]} ({leader["symbol"]}). Provisional, not a trade today.')
        if len(ranking)>1:
            runner = ranking[1]
            cushion = 1-(1+runner['return'])/(1+leader['return'])
            lines.append(f'With {runner["symbol"]} unchanged, {leader["symbol"]} could fall {cushion:.1%} before they tie.')
    lines.append(f'Ranking coverage: {leaders.get("eligible_count", 0)} of {leaders.get("universe_count", 0)} current constituent lines. Missing endpoints are excluded.')
    if leaders.get('refresh_error') or leaders.get('last_attempt'):
        lines.append('Ranking refresh failed. Previous successful rankings may be retained.')
    lines += ['', 'Source dates',
        f'{symbol}: {dated(quotes.get(symbol, {}).get("at"))}. SPY: {dated(quotes.get("SPY", {}).get("at"))}.',
        f'GBP/USD: {dated(quotes.get("GBPUSD=X", {}).get("at"))}.',
        f'Ranking scan: {dated(leaders.get("updated_at"))}.']
    if warnings:
        lines += ['Data warnings: '+' | '.join(str(e) for e in warnings)]
    lines += ['', 'Indicative free exchange quotes can differ from your broker. SPY entry is an approximate minute proxy with no fees. No orders are placed. Stop observations are not continuous.', SITE]
    plain = '\n'.join(lines)
    rendered = '<div style="font-family:Arial,sans-serif;font-size:15px;line-height:1.55;max-width:660px">'+html.escape(plain).replace('\n','<br>')+'</div>'
    for heading in (lines[0], 'Since your purchase', 'Fixed entry stop', 'January strategy, separate from your October entry', 'Source dates'):
        rendered = rendered.replace(html.escape(heading), '<b>'+html.escape(heading)+'</b>')
    rendered = rendered.replace(html.escape(SITE), f'<a href="{SITE}">Open The Annual</a>')
    return subject, plain, rendered

def send(subject, plain, rendered):
    password = os.environ.get('GMAIL_APP_PASSWORD')
    if not password:
        raise RuntimeError('GMAIL_APP_PASSWORD is required for --send')
    user = os.environ.get('GMAIL_USER', 'leeslater1992@gmail.com')
    recipient = os.environ.get('MAIL_TO', user)
    msg = EmailMessage()
    msg['Subject'] = subject
    msg['From'] = f'The Annual <{user}>'
    msg['To'] = recipient
    msg.set_content(plain)
    msg.add_alternative(rendered, subtype='html')
    with smtplib.SMTP_SSL('smtp.gmail.com', 465, timeout=30) as smtp:
        smtp.login(user, password.replace(' ', ''))
        smtp.send_message(msg)

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--send', action='store_true')
    parser.add_argument('--preview-dir', type=Path, default=ROOT/'daily-preview')
    parser.add_argument('--receipt', type=Path, default=ROOT/'.daily-mail/receipt.json')
    args = parser.parse_args()
    now = datetime.now(timezone.utc)
    day = now.astimezone(LONDON).date().isoformat()
    if args.send and args.receipt.exists():
        receipt = json.loads(args.receipt.read_text())
        if receipt.get('day') == day:
            print('Daily email already sent for this London date. Skipped.')
            return
    live = json.loads((ROOT/'site/data/live.json').read_text())
    leaders = json.loads((ROOT/'site/data/leaders.json').read_text())
    subject, plain, rendered = compose(live, leaders, now)
    args.preview_dir.mkdir(parents=True, exist_ok=True)
    (args.preview_dir/'daily.txt').write_text(subject+'\n\n'+plain)
    (args.preview_dir/'daily.html').write_text(rendered)
    print(subject+'\n\n'+plain)
    if args.send:
        send(subject, plain, rendered)
        args.receipt.parent.mkdir(parents=True, exist_ok=True)
        args.receipt.write_text(json.dumps({'day':day, 'sent_at':now.isoformat(), 'subject':subject})+'\n')
        print('Email accepted by Gmail SMTP.')

if __name__ == '__main__':
    main()
