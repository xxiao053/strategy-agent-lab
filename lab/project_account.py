"""Long-only trusted account; method code proposes shares, never balances or fills."""
from decimal import Decimal, ROUND_HALF_UP
from .contracts import iso
from .execution_contract import Proposal


def decimal(value):
    result=Decimal(str(value))
    if not result.is_finite():raise ValueError('Non-finite account value.')
    return result


def cents(value):return decimal(value).quantize(Decimal('.01'),rounding=ROUND_HALF_UP)


class Account:
    def __init__(self,cash,fee_rate):
        self.cash=cents(cash);self.fee_rate=decimal(fee_rate);self.positions={}
        if not 0<self.cash<=100000000 or not 0<=self.fee_rate<=Decimal('.05'):
            raise ValueError('Invalid cash or fee assumptions.')

    def amounts(self,price,shares):
        if decimal(price)<=0:raise ValueError('Invalid fill price.')
        gross=cents(decimal(price)*shares);return gross,cents(gross*self.fee_rate)

    def eligible(self,p,prices,reserved_cash=0):
        p=Proposal.model_validate(p).model_dump();shares=p['sizing']['shares']
        if p['action']=='hold':return False
        if p['action']=='sell':return self.positions.get(p['symbol'],0)>=shares
        gross,fee=self.amounts(prices[p['symbol']],shares)
        return gross+fee<=self.cash-decimal(reserved_cash)

    def order(self,p,decision_id,date):
        p=Proposal.model_validate(p).model_dump();iso(date)
        return dict(id=decision_id+'-order',decision_id=decision_id,signal_date=date,symbol=p['symbol'],
                    action=p['action'],quantity=p['sizing']['shares'],status='pending',reason='next_session_open',
                    explanation=p['explanation'])

    def fill(self,orders,opens,date):
        iso(date)
        for o in orders:
            if date<=o['signal_date']:raise ValueError('Fill must follow signal date.')
            if o['status']!='pending':continue
            symbol=o['symbol'];shares=o['quantity']
            if symbol not in opens:raise ValueError('Missing next session open data.')
            price=decimal(opens[symbol]);gross,fee=self.amounts(price,shares)
            if o['action']=='buy' and gross+fee>self.cash:
                o.update(status='cancelled',reason='insufficient_cash_at_open');continue
            if o['action']=='sell' and shares>self.positions.get(symbol,0):
                o.update(status='cancelled',reason='insufficient_shares');continue
            if o['action'] not in {'buy','sell'}:raise ValueError('Only buy/sell orders can fill.')
            if o['action']=='buy':
                self.cash-=gross+fee;self.positions[symbol]=self.positions.get(symbol,0)+shares
            else:
                self.cash+=gross-fee;self.positions[symbol]-=shares
                if not self.positions[symbol]:del self.positions[symbol]
            o.update(status='filled',reason='next_session_open',date=date,price=float(price),fee=float(fee),gross=float(gross))

    def snapshot(self,closes):
        value=self.cash+sum(cents(decimal(closes[s])*q) for s,q in self.positions.items())
        return dict(cash=float(self.cash),equity=float(value),positions=dict(self.positions))
