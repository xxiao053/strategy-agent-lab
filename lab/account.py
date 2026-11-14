"""Deterministic shared-cash simulator. All orders sized before next-session prices exist."""
from decimal import Decimal, ROUND_HALF_UP, ROUND_CEILING
from math import floor


def money(value, ceiling=False):
    return float(Decimal(str(value)).quantize(Decimal('.01'), rounding=ROUND_CEILING if ceiling else ROUND_HALF_UP))


def quantity(equity, close, stop, cash, s):
    maximum = (1+s.entry_gap_limit) * close
    risk = maximum-stop+s.commission*(maximum+stop)
    if risk <= 0:
        return 0
    q = floor(min(s.risk_fraction*equity/risk, s.max_weight*equity/maximum, cash/(maximum*(1+s.commission))))
    while q > 0 and money(q*maximum*(1+s.commission), True) > cash:
        q -= 1
    return max(0, q)


class Account:
    def __init__(self, capital, state=None):
        self.cash = money(capital)
        self.positions = {}
        self.orders = []
        self.trades = []
        self.curve = []
        if state:
            self.__dict__.update(state)

    @property
    def available(self):
        reserved = sum(o['reserved'] for o in self.orders if o['side'] == 'buy' and o['status'] == 'pending')
        return money(self.cash-reserved)

    def equity(self, closes=None):
        closes = closes or {}
        return money(self.cash + sum(p['quantity']*closes.get(symbol, p['last_close']) for symbol, p in self.positions.items()))

    def entry_check(self, symbol, close, s, pattern):
        stop = pattern.get('stop') if pattern else None
        if not pattern or pattern.get('volatility_unit',0)<=0 or not stop<close<pattern.get('target',0) or not pattern.get('candidate_id'):
            raise ValueError('Entry requires fixed candidate, positive volatility and target above close')
        pending = [o for o in self.orders if o['status'] == 'pending' and o['side'] == 'buy']
        if symbol in self.positions or any(o['symbol'] == symbol for o in pending) or len(self.positions)+len(pending) >= s.max_positions:
            return dict(eligible=False, reason='position_slots', quantity=0)
        q = quantity(self.equity(), close, stop, self.available, s)
        return dict(eligible=bool(q), reason='eligible' if q else 'cash_or_sizing', quantity=q)

    def enter(self, symbol, day, close, stop, s, pattern=None):
        if pattern and pattern.get('stop') != stop:
            raise ValueError('Entry stop must match the fixed candidate')
        check = self.entry_check(symbol, close, s, pattern)
        if not check['eligible']:
            return False
        q = check['quantity']
        maximum = (1+s.entry_gap_limit)*close
        self.orders.append(dict(id=f'{day}:{symbol}:buy', symbol=symbol, side='buy', signal_date=day,
                                quantity=q, stop=stop, target=pattern['target'],volatility_unit=pattern['volatility_unit'],
                                candidate_id=pattern['candidate_id'],max_fill=maximum,
                                reserved=money(q*maximum*(1+s.commission), True), status='pending'))
        return True

    def open_day(self, day, opens, s):
        for o in sorted(self.orders, key=lambda x: (x['side'] == 'buy', x['symbol'])):
            if o['status'] != 'pending' or o['signal_date'] >= day:
                continue
            symbol, q = o['symbol'], o['quantity']
            price = opens[symbol]*(1+s.slippage if o['side'] == 'buy' else 1-s.slippage)
            fee = money(q*price*s.commission)
            if o['side'] == 'buy':
                if price > o['max_fill'] or price <= o['stop'] or price >= o['target']:
                    o.update(status='cancelled_gap', fill_date=day)
                    continue
                cost = money(q*price+fee)
                if cost > self.cash:
                    raise ValueError('Accounting invariant: cash reservation insufficient')
                self.cash = money(self.cash-cost)
                self.positions[symbol] = dict(quantity=q, entry_price=price, entry_date=day, cost=cost,
                                              stop=o['stop'],target=o['target'],volatility_unit=o['volatility_unit'],
                                              candidate_id=o['candidate_id'],progress_anchor=price,peak_close=price,stagnant_sessions=0,
                                              held_sessions=0, last_close=price)
            else:
                p = self.positions.pop(symbol)
                proceeds = money(q*price-fee)
                self.cash = money(self.cash+proceeds)
                self.trades.append(dict(symbol=symbol, quantity=q, entry_date=p['entry_date'], entry_price=p['entry_price'],
                                        exit_date=day, exit_price=price, pnl=money(proceeds-p['cost']), reason=o['reason'],
                                        candidate_id=p['candidate_id'],stop=p['stop'],target=p['target']))
            o.update(status='filled', fill_date=day, fill_price=price, fee=fee)
        if self.cash < 0:
            raise ValueError('Negative cash invariant')

    def close_day(self, day, closes, s):
        for symbol, p in self.positions.items():
            p['last_close'] = closes[symbol]
            p['held_sessions'] += 1
            close=closes[symbol]
            p['peak_close']=max(p.get('peak_close',p['entry_price']),close)
            reason='stop_close' if close<p['stop'] else ('target_close' if close>=p['target'] else None)
            if reason is None and s.trailing_stop_units>0 and close<p['peak_close']-s.trailing_stop_units*p['volatility_unit']:
                reason='trailing_stop'
            if reason is None:
                if close>=p['progress_anchor']+s.progress_units*p['volatility_unit']:
                    p['progress_anchor'],p['stagnant_sessions']=close,0
                else:p['stagnant_sessions']+=1
                if s.stagnation_sessions>0 and p['stagnant_sessions']>=s.stagnation_sessions:reason='stagnation'
            if reason and not any(o['symbol'] == symbol and o['status'] == 'pending' for o in self.orders):
                self.orders.append(dict(id=f'{day}:{symbol}:sell', symbol=symbol, side='sell', quantity=p['quantity'],
                                        signal_date=day, status='pending', reason=reason))
        self.curve.append(dict(date=day, equity=self.equity(closes), cash=self.cash, positions=len(self.positions)))

    def dump(self):
        return self.__dict__
