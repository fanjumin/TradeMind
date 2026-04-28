'''
TradeMind Simulated Trading — 模拟交易引擎
对标聚宽/米筐模拟交易 (订单管理+成交模拟+绩效分析)
'''
import os, json, time, uuid
from datetime import datetime
from dataclasses import dataclass, field
from enum import Enum
import numpy as np


DATA_DIR = os.path.join(os.path.dirname(__file__), 'data', 'simtrade')
os.makedirs(DATA_DIR, exist_ok=True)


class OrderType(Enum):
    MARKET = 'market'
    LIMIT = 'limit'

class OrderSide(Enum):
    BUY = 'buy'
    SELL = 'sell'

class OrderStatus(Enum):
    PENDING = 'pending'
    PARTIAL = 'partial'
    FILLED = 'filled'
    CANCELLED = 'cancelled'
    REJECTED = 'rejected'

@dataclass
class Order:
    order_id: str
    symbol: str
    name: str
    side: OrderSide
    order_type: OrderType
    quantity: int
    limit_price: float = 0.0
    filled_qty: int = 0
    filled_price: float = 0.0
    status: OrderStatus = OrderStatus.PENDING
    created_at: str = ''
    filled_at: str = ''
    commission: float = 0.0
    notes: str = ''
    
    def __post_init__(self):
        if not self.created_at:
            self.created_at = datetime.now().isoformat()
    
    def to_dict(self):
        return {
            'order_id': self.order_id,
            'symbol': self.symbol, 'name': self.name,
            'side': self.side.value, 'order_type': self.order_type.value,
            'quantity': self.quantity, 'limit_price': self.limit_price,
            'filled_qty': self.filled_qty, 'filled_price': self.filled_price,
            'status': self.status.value,
            'created_at': self.created_at, 'filled_at': self.filled_at,
            'commission': self.commission, 'notes': self.notes,
        }
    
    @classmethod
    def from_dict(cls, d):
        return cls(
            order_id=d['order_id'], symbol=d['symbol'], name=d.get('name',''),
            side=OrderSide(d['side']), order_type=OrderType(d['order_type']),
            quantity=d['quantity'], limit_price=d.get('limit_price',0),
            filled_qty=d.get('filled_qty',0), filled_price=d.get('filled_price',0),
            status=OrderStatus(d['status']),
            created_at=d.get('created_at',''), filled_at=d.get('filled_at',''),
            commission=d.get('commission',0), notes=d.get('notes',''),
        )

@dataclass
class Trade:
    trade_id: str
    order_id: str
    symbol: str
    name: str
    side: OrderSide
    quantity: int
    price: float
    commission: float
    stamp_tax: float
    timestamp: str
    
    def to_dict(self):
        return {
            'trade_id': self.trade_id, 'order_id': self.order_id,
            'symbol': self.symbol, 'name': self.name,
            'side': self.side.value, 'quantity': self.quantity,
            'price': self.price, 'commission': self.commission,
            'stamp_tax': self.stamp_tax, 'timestamp': self.timestamp,
        }

@dataclass
class Position:
    symbol: str
    name: str
    quantity: int
    avg_cost: float
    current_price: float = 0.0
    
    @property
    def market_value(self):
        return self.quantity * self.current_price
    
    @property
    def cost_basis(self):
        return self.quantity * self.avg_cost
    
    @property
    def pnl(self):
        return self.market_value - self.cost_basis
    
    @property
    def pnl_pct(self):
        return (self.current_price / self.avg_cost - 1) * 100 if self.avg_cost > 0 else 0
    
    def to_dict(self):
        return {
            'symbol': self.symbol, 'name': self.name,
            'quantity': self.quantity, 'avg_cost': round(self.avg_cost, 2),
            'current_price': round(self.current_price, 2),
            'market_value': round(self.market_value, 2),
            'pnl': round(self.pnl, 2), 'pnl_pct': round(self.pnl_pct, 2),
        }


class CostModel:
    def __init__(self, commission_rate=0.0003, min_commission=5.0,
                 stamp_tax_rate=0.0005, slippage=0.001):
        self.commission_rate = commission_rate
        self.min_commission = min_commission
        self.stamp_tax_rate = stamp_tax_rate
        self.slippage = slippage
    
    def buy_cost(self, price, quantity):
        amount = price * quantity
        return max(self.min_commission, amount * self.commission_rate)
    
    def sell_cost(self, price, quantity):
        amount = price * quantity
        commission = max(self.min_commission, amount * self.commission_rate)
        stamp_tax = amount * self.stamp_tax_rate
        return commission + stamp_tax
    
    def execution_price(self, price, side):
        if side == OrderSide.BUY:
            return price * (1 + self.slippage)
        else:
            return price * (1 - self.slippage)


class OrderManager:
    def __init__(self, initial_capital=1000000):
        self.initial_capital = initial_capital
        self.cash = initial_capital
        self.cost_model = CostModel()
        self.orders = {}
        self.positions = {}
        self.trades = []
        self.snapshots = []
        self._next_trade_id = 1
        self._state_file = os.path.join(DATA_DIR, 'sim_state.json')
        self._load_state()
    
    def _load_state(self):
        if os.path.exists(self._state_file):
            try:
                with open(self._state_file) as f:
                    state = json.load(f)
                self.cash = state.get('cash', self.initial_capital)
                self.initial_capital = state.get('initial_capital', self.initial_capital)
                for od in state.get('orders', []):
                    o = Order.from_dict(od)
                    self.orders[o.order_id] = o
                for pd in state.get('positions', []):
                    self.positions[pd['symbol']] = Position(
                        pd['symbol'], pd['name'], pd['quantity'],
                        pd['avg_cost'], pd.get('current_price', 0))
                self._next_trade_id = state.get('next_trade_id', 1)
            except:
                pass
    
    def _save_state(self):
        state = {
            'cash': self.cash,
            'initial_capital': self.initial_capital,
            'next_trade_id': self._next_trade_id,
            'orders': [o.to_dict() for o in self.orders.values() if o.status == OrderStatus.PENDING],
            'positions': [p.to_dict() for p in self.positions.values()],
        }
        with open(self._state_file, 'w') as f:
            json.dump(state, f, indent=2, ensure_ascii=False)
    
    def submit_order(self, symbol, name, side, order_type, quantity, limit_price=0):
        symbol = str(symbol).zfill(6)
        
        if side == OrderSide.BUY:
            estimated_cost = quantity * (limit_price or 100) * 1.01
            if estimated_cost > self.cash:
                return {'error': 'Insufficient cash'}
        
        if side == OrderSide.SELL:
            pos = self.positions.get(symbol)
            if not pos or pos.quantity < quantity:
                have = pos.quantity if pos else 0
                return {'error': 'Insufficient shares. Have %d, want %d' % (have, quantity)}
        
        if quantity < 100:
            return {'error': 'Minimum order is 100 shares'}
        if quantity % 100 != 0:
            quantity = (quantity // 100) * 100
        
        # Try to get real name from price API
        if name == symbol:
            try:
                from data.price import get_latest_price
                info = get_latest_price(symbol)
                if info and info.get('name'):
                    name = info['name']
            except:
                pass
        
        order_id = str(uuid.uuid4())[:8]
        order = Order(
            order_id=order_id, symbol=symbol, name=name,
            side=side, order_type=order_type,
            quantity=quantity, limit_price=limit_price,
        )
        self.orders[order_id] = order
        
        if order_type == OrderType.MARKET:
            self._fill_order(order)
        
        self._save_state()
        return {'success': True, 'order': order.to_dict()}
    
    def cancel_order(self, order_id):
        if order_id not in self.orders:
            return {'error': 'Order not found'}
        order = self.orders[order_id]
        if order.status != OrderStatus.PENDING:
            return {'error': 'Cannot cancel order in status ' + order.status.value}
        order.status = OrderStatus.CANCELLED
        self._save_state()
        return {'success': True, 'order': order.to_dict()}
    
    def match_orders(self, prices):
        filled = []
        for order in list(self.orders.values()):
            if order.status != OrderStatus.PENDING:
                continue
            if order.order_type != OrderType.LIMIT:
                continue
            price = prices.get(order.symbol, 0)
            if price <= 0:
                continue
            if order.side == OrderSide.BUY and price <= order.limit_price:
                self._fill_order(order, price)
                filled.append(order.order_id)
            elif order.side == OrderSide.SELL and price >= order.limit_price:
                self._fill_order(order, price)
                filled.append(order.order_id)
        return filled
    
    def _fill_order(self, order, price=None):
        if price is None:
            try:
                from data.price import get_latest_price
                info = get_latest_price(order.symbol)
                if info:
                    price = info.get('price', 0)
            except:
                price = 0
        
        if price <= 0:
            order.status = OrderStatus.REJECTED
            order.notes = 'No price data available'
            return
        
        exec_price = self.cost_model.execution_price(price, order.side)
        quantity = order.quantity
        
        if order.side == OrderSide.BUY:
            cost = exec_price * quantity
            commission = self.cost_model.buy_cost(exec_price, quantity)
            total_cost = cost + commission
            if total_cost > self.cash:
                order.status = OrderStatus.REJECTED
                order.notes = 'Insufficient cash'
                return
            self.cash -= total_cost
            order.commission = commission
            if order.symbol in self.positions:
                pos = self.positions[order.symbol]
                total_qty = pos.quantity + quantity
                pos.avg_cost = (pos.avg_cost * pos.quantity + cost) / total_qty
                pos.quantity = total_qty
            else:
                self.positions[order.symbol] = Position(
                    symbol=order.symbol, name=order.name,
                    quantity=quantity, avg_cost=exec_price,
                )
        else:
            proceeds = exec_price * quantity
            cost_info = self.cost_model.sell_cost(exec_price, quantity)
            self.cash += (proceeds - cost_info)
            pos = self.positions[order.symbol]
            pos.quantity -= quantity
            if pos.quantity <= 0:
                del self.positions[order.symbol]
        
        order.filled_qty = quantity
        order.filled_price = exec_price
        order.status = OrderStatus.FILLED
        order.filled_at = datetime.now().isoformat()
        
        trade = Trade(
            trade_id=str(self._next_trade_id),
            order_id=order.order_id,
            symbol=order.symbol, name=order.name,
            side=order.side, quantity=quantity,
            price=exec_price,
            commission=order.commission if order.side == OrderSide.BUY else self.cost_model.buy_cost(exec_price, quantity),
            stamp_tax=self.cost_model.stamp_tax_rate * exec_price * quantity if order.side == OrderSide.SELL else 0,
            timestamp=datetime.now().isoformat(),
        )
        self.trades.append(trade)
        self._next_trade_id += 1
    
    def tick(self, symbols=None):
        if symbols is None:
            symbols = list(self.positions.keys())
        prices = {}
        for sym in symbols:
            try:
                from data.price import get_latest_price
                info = get_latest_price(sym)
                if info:
                    prices[sym] = info.get('price', 0)
            except:
                pass
        for sym in self.positions:
            if sym in prices:
                self.positions[sym].current_price = prices[sym]
        self.match_orders(prices)
        pos_value = sum(p.market_value for p in self.positions.values())
        self.snapshots.append({
            'timestamp': datetime.now().isoformat(),
            'cash': round(self.cash, 2),
            'positions_value': round(pos_value, 2),
            'total': round(self.cash + pos_value, 2),
        })
        self._save_state()
        return {'prices': len(prices), 'positions': len(self.positions),
                'total_value': round(self.cash + pos_value, 2)}
    
    def get_positions(self):
        return [p.to_dict() for p in self.positions.values()]
    
    def get_orders(self, status=None):
        orders = list(self.orders.values())
        if status:
            orders = [o for o in orders if o.status == status]
        return [o.to_dict() for o in orders]
    
    def get_trades(self, limit=50):
        return [t.to_dict() for t in self.trades[-limit:]]
    
    def get_performance(self):
        pos_value = sum(p.market_value for p in self.positions.values())
        total = self.cash + pos_value
        total_return = (total - self.initial_capital) / self.initial_capital
        
        sharpe = 0
        max_dd = 0
        win_rate = 0
        avg_win = 0
        avg_loss = 0
        
        sell_trades = [t for t in self.trades if t.side == OrderSide.SELL]
        if sell_trades:
            pnls = []
            buy_map = {}
            for t in self.trades:
                if t.side == OrderSide.BUY:
                    if t.symbol not in buy_map:
                        buy_map[t.symbol] = []
                    buy_map[t.symbol].append(t)
                elif t.side == OrderSide.SELL:
                    if t.symbol in buy_map and buy_map[t.symbol]:
                        avg_buy = sum(b.price for b in buy_map[t.symbol]) / len(buy_map[t.symbol])
                        pnl = (t.price - avg_buy) * t.quantity - t.commission - t.stamp_tax
                        pnls.append(pnl)
            if pnls:
                wins = [p for p in pnls if p > 0]
                losses = [p for p in pnls if p <= 0]
                win_rate = len(wins) / len(pnls) if pnls else 0
                avg_win = np.mean(wins) if wins else 0
                avg_loss = abs(np.mean(losses)) if losses else 0
                if len(pnls) > 1:
                    returns = [p / self.initial_capital for p in pnls]
                    mean_ret = np.mean(returns)
                    std_ret = np.std(returns) if np.std(returns) > 0 else 0.0001
                    sharpe = mean_ret / std_ret * np.sqrt(len(pnls))
        
        if self.snapshots:
            values = [s['total'] for s in self.snapshots]
            peak = np.maximum.accumulate(values)
            drawdowns = (peak - np.array(values)) / np.where(peak > 0, peak, 1)
            max_dd = float(np.max(drawdowns))
        
        annualized_return = total_return
        if self.snapshots and len(self.snapshots) > 1:
            first = datetime.fromisoformat(self.snapshots[0]['timestamp'])
            last = datetime.fromisoformat(self.snapshots[-1]['timestamp'])
            days = max((last - first).days, 1)
            annualized_return = (1 + total_return) ** (365 / days) - 1 if total_return > -1 else -1
        
        return {
            'initial_capital': self.initial_capital,
            'cash': round(self.cash, 2),
            'positions_value': round(pos_value, 2),
            'total_value': round(total, 2),
            'total_return_pct': round(total_return * 100, 2),
            'annualized_return_pct': round(annualized_return * 100, 2),
            'sharpe_ratio': round(sharpe, 3),
            'max_drawdown_pct': round(max_dd * 100, 2),
            'win_rate_pct': round(win_rate * 100, 1),
            'avg_win': round(avg_win, 2),
            'avg_loss': round(avg_loss, 2),
            'total_trades': len(sell_trades),
            'snapshot_count': len(self.snapshots),
        }
    
    def get_summary(self):
        perf = self.get_performance()
        s = "=" * 60
        print(s)
        print("  TradeMind Sim Trading Account")
        print(s)
        print("  Initial:  %s" % f"{perf['initial_capital']:,.0f}")
        print("  Cash:     %s" % f"{perf['cash']:,.0f}")
        print("  Position: %s" % f"{perf['positions_value']:,.0f}")
        print("  Total:    %s" % f"{perf['total_value']:,.0f}")
        print("  Return:   %+.2f%% (annual %+.2f%%)" % (perf['total_return_pct'], perf['annualized_return_pct']))
        print("  Sharpe:   %.3f" % perf['sharpe_ratio'])
        print("  MaxDD:    %.2f%%" % perf['max_drawdown_pct'])
        print("  WinRate:  %.1f%% (%d trades)" % (perf['win_rate_pct'], perf['total_trades']))
        if self.positions:
            print()
            print("  Holdings:")
            for p in self.get_positions():
                print("    %s %s x%d @%.2f now %.2f %+.2f%%" % (
                    p['symbol'], p['name'], p['quantity'], p['avg_cost'],
                    p['current_price'], p['pnl_pct']))
        pending = self.get_orders(OrderStatus.PENDING)
        if pending:
            print()
            print("  Pending orders (%d):" % len(pending))
            for o in pending:
                print("    %s %s %s x%d limit %.2f" % (o['order_id'], o['side'], o['symbol'], o['quantity'], o['limit_price']))
        return perf


if __name__ == '__main__':
    import sys
    om = OrderManager()
    if len(sys.argv) < 2:
        om.get_summary()
        sys.exit(0)
    cmd = sys.argv[1]
    if cmd == 'init':
        capital = float(sys.argv[2]) if len(sys.argv) > 2 else 1000000
        om.cash = capital
        om.initial_capital = capital
        om.orders = {}
        om.positions = {}
        om.trades = []
        om.snapshots = []
        om._save_state()
        print("Account initialized: %,.0f" % capital)
    elif cmd == 'buy':
        symbol = sys.argv[2] if len(sys.argv) > 2 else '600519'
        qty = int(sys.argv[3]) if len(sys.argv) > 3 else 100
        result = om.submit_order(symbol, symbol, OrderSide.BUY, OrderType.MARKET, qty)
        if result.get('error'):
            print("Error:", result['error'])
        else:
            print("Bought %d %s" % (qty, symbol))
            om.tick([symbol])
        om.get_summary()
    elif cmd == 'sell':
        symbol = sys.argv[2]
        qty = int(sys.argv[3]) if len(sys.argv) > 3 else 0
        if qty == 0 and symbol in om.positions:
            qty = om.positions[symbol].quantity
        name = om.positions[symbol].name if symbol in om.positions else symbol
        result = om.submit_order(symbol, name, OrderSide.SELL, OrderType.MARKET, qty)
        if result.get('error'):
            print("Error:", result['error'])
        else:
            print("Sold %d %s" % (qty, symbol))
            om.tick([symbol])
        om.get_summary()
    elif cmd == 'positions':
        for p in om.get_positions():
            print("%s %s x%d @%.2f now %.2f %+.2f%%" % (p['symbol'], p['name'], p['quantity'], p['avg_cost'], p['current_price'], p['pnl_pct']))
    elif cmd == 'performance':
        om.get_summary()
    elif cmd == 'tick':
        r = om.tick()
        print("Tick: %d prices, total: %,.0f" % (r['prices'], r['total_value']))
    elif cmd == 'reset':
        om.cash = om.initial_capital
        om.orders = {}
        om.positions = {}
        om.trades = []
        om.snapshots = []
        om._save_state()
        print("Reset to %,.0f" % om.initial_capital)
    else:
        print("Commands: init buy sell positions performance tick reset")
