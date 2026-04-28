"""
TradeMind Portfolio Management System
======================================
Features:
- Portfolio creation and management (multiple portfolios)
- Position tracking (buy/sell simulation)
- P&L calculation (real-time)
- Portfolio analysis (sector distribution, risk metrics, correlation)
- Watchlist management with groups
- Persistent storage (JSON file)
"""

import json
import os
import time
from datetime import datetime
from collections import defaultdict


# ============================================================
# Data Models
# ============================================================

class Position:
    def __init__(self, code, name, shares, cost_price, buy_date=""):
        self.code = code
        self.name = name
        self.shares = shares
        self.cost_price = cost_price
        self.buy_date = buy_date or datetime.now().strftime("%Y-%m-%d")
        self.current_price = 0
        self.change_pct = 0

    @property
    def cost_total(self):
        return self.cost_price * self.shares

    @property
    def market_value(self):
        return self.current_price * self.shares

    @property
    def pnl(self):
        return self.market_value - self.cost_total

    @property
    def pnl_pct(self):
        return ((self.current_price - self.cost_price) / self.cost_price * 100) if self.cost_price > 0 else 0

    def to_dict(self):
        return {
            "code": self.code,
            "name": self.name,
            "shares": self.shares,
            "cost_price": self.cost_price,
            "buy_date": self.buy_date,
            "current_price": self.current_price,
            "change_pct": self.change_pct,
            "pnl": round(self.pnl, 2),
            "pnl_pct": round(self.pnl_pct, 2),
            "cost_total": round(self.cost_total, 2),
            "market_value": round(self.market_value, 2),
        }

    @staticmethod
    def from_dict(d):
        p = Position(d["code"], d["name"], d["shares"], d["cost_price"], d.get("buy_date", ""))
        p.current_price = d.get("current_price", 0)
        p.change_pct = d.get("change_pct", 0)
        return p


class Portfolio:
    def __init__(self, name, initial_capital=1000000, description=""):
        self.id = name.lower().replace(" ", "_")
        self.name = name
        self.description = description
        self.initial_capital = initial_capital
        self.positions = []
        self.history = []  # Trade history
        self.created_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    @property
    def total_market_value(self):
        return sum(p.market_value for p in self.positions)

    @property
    def total_cost(self):
        return sum(p.cost_total for p in self.positions)

    @property
    def cash(self):
        return self.initial_capital - self.total_cost

    @property
    def total_pnl(self):
        return self.total_market_value - self.total_cost

    @property
    def total_pnl_pct(self):
        return (self.total_pnl / self.total_cost * 100) if self.total_cost > 0 else 0

    @property
    def total_value(self):
        return self.total_market_value + self.cash

    def add_position(self, code, name, shares, price, date=""):
        # Check if position already exists
        for p in self.positions:
            if p.code == code:
                # Average up
                total_shares = p.shares + shares
                total_cost = p.cost_total + (price * shares)
                p.cost_price = total_cost / total_shares
                p.shares = total_shares
                self.history.append({
                    "action": "add",
                    "code": code,
                    "name": name,
                    "shares": shares,
                    "price": price,
                    "date": date or datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                return

        pos = Position(code, name, shares, price, date)
        self.positions.append(pos)
        self.history.append({
            "action": "buy",
            "code": code,
            "name": name,
            "shares": shares,
            "price": price,
            "date": date or datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    def remove_position(self, code, price=None):
        for i, p in enumerate(self.positions):
            if p.code == code:
                sell_price = price or p.current_price
                pnl = (sell_price - p.cost_price) * p.shares
                self.positions.pop(i)
                self.history.append({
                    "action": "sell",
                    "code": code,
                    "name": p.name,
                    "shares": p.shares,
                    "price": sell_price,
                    "pnl": round(pnl, 2),
                    "date": datetime.now().strftime("%Y-%m-%d %H:%M"),
                })
                return True
        return False

    def update_prices(self, price_data):
        """Update current prices from dict {code: {price, change_pct}}"""
        for p in self.positions:
            if p.code in price_data:
                p.current_price = price_data[p.code].get("price", 0)
                p.change_pct = price_data[p.code].get("change_pct", 0)

    def get_analysis(self):
        """Get portfolio analysis metrics"""
        if not self.positions:
            return {"error": "No positions"}

        # Position weights
        total_mv = self.total_market_value
        weights = []
        for p in self.positions:
            w = (p.market_value / total_mv * 100) if total_mv > 0 else 0
            weights.append({
                "code": p.code,
                "name": p.name,
                "weight": round(w, 1),
                "pnl_pct": round(p.pnl_pct, 2),
            })

        # Sort by weight
        weights.sort(key=lambda x: x["weight"], reverse=True)

        # Risk metrics
        pnls = [p.pnl_pct for p in self.positions]
        avg_pnl = sum(pnls) / len(pnls) if pnls else 0
        max_pnl = max(pnls) if pnls else 0
        min_pnl = min(pnls) if pnls else 0

        # Concentration (top 3 weight)
        top3_weight = sum(w["weight"] for w in weights[:3])

        return {
            "total_positions": len(self.positions),
            "total_market_value": round(total_mv, 2),
            "total_cost": round(self.total_cost, 2),
            "cash": round(self.cash, 2),
            "total_pnl": round(self.total_pnl, 2),
            "total_pnl_pct": round(self.total_pnl_pct, 2),
            "total_value": round(self.total_value, 2),
            "avg_pnl_pct": round(avg_pnl, 2),
            "best_stock": max(weights, key=lambda x: x["pnl_pct"]) if weights else None,
            "worst_stock": min(weights, key=lambda x: x["pnl_pct"]) if weights else None,
            "concentration_top3": round(top3_weight, 1),
            "weights": weights,
        }

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "description": self.description,
            "initial_capital": self.initial_capital,
            "positions": [p.to_dict() for p in self.positions],
            "history": self.history,
            "created_at": self.created_at,
        }

    @staticmethod
    def from_dict(d):
        p = Portfolio(d["name"], d.get("initial_capital", 1000000), d.get("description", ""))
        p.id = d.get("id", p.id)
        p.created_at = d.get("created_at", "")
        p.history = d.get("history", [])
        for pd in d.get("positions", []):
            pos = Position.from_dict(pd)
            p.positions.append(pos)
        return p


# ============================================================
# Portfolio Manager
# ============================================================

class PortfolioManager:
    def __init__(self, config_path=None):
        self.config_path = config_path or os.path.expanduser("~/.trademind_portfolios.json")
        self.portfolios = {}
        self.watchlists = {}
        self._load()

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r") as f:
                    data = json.load(f)
                for pd in data.get("portfolios", []):
                    p = Portfolio.from_dict(pd)
                    self.portfolios[p.id] = p
                self.watchlists = data.get("watchlists", {})
            except:
                pass

    def _save(self):
        data = {
            "portfolios": [p.to_dict() for p in self.portfolios.values()],
            "watchlists": self.watchlists,
        }
        with open(self.config_path, "w") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def create_portfolio(self, name, initial_capital=1000000, description=""):
        p = Portfolio(name, initial_capital, description)
        self.portfolios[p.id] = p
        self._save()
        return p

    def delete_portfolio(self, portfolio_id):
        if portfolio_id in self.portfolios:
            del self.portfolios[portfolio_id]
            self._save()
            return True
        return False

    def buy(self, portfolio_id, code, name, shares, price, date=""):
        if portfolio_id not in self.portfolios:
            return {"error": "Portfolio not found"}
        p = self.portfolios[portfolio_id]
        p.add_position(code, name, shares, price, date)
        self._save()
        return {"success": True, "portfolio": p.to_dict()}

    def sell(self, portfolio_id, code, price=None):
        if portfolio_id not in self.portfolios:
            return {"error": "Portfolio not found"}
        p = self.portfolios[portfolio_id]
        if p.remove_position(code, price):
            self._save()
            return {"success": True}
        return {"error": "Position not found"}

    def update_prices(self, portfolio_id, price_data):
        if portfolio_id not in self.portfolios:
            return
        self.portfolios[portfolio_id].update_prices(price_data)

    def get_portfolio(self, portfolio_id):
        if portfolio_id not in self.portfolios:
            return {"error": "Portfolio not found"}
        p = self.portfolios[portfolio_id]
        return p.to_dict()

    def list_portfolios(self):
        results = []
        for pid, p in self.portfolios.items():
            results.append({
                "id": pid,
                "name": p.name,
                "description": p.description,
                "positions": len(p.positions),
                "total_value": round(p.total_value, 2),
                "total_pnl": round(p.total_pnl, 2),
                "total_pnl_pct": round(p.total_pnl_pct, 2),
                "created_at": p.created_at,
            })
        return results

    # Watchlist management
    def create_watchlist(self, name, description=""):
        if name not in self.watchlists:
            self.watchlists[name] = {
                "description": description,
                "stocks": [],
                "created_at": datetime.now().strftime("%Y-%m-%d"),
            }
            self._save()
        return self.watchlists[name]

    def add_to_watchlist(self, name, code, stock_name=""):
        if name not in self.watchlists:
            self.create_watchlist(name)
        wl = self.watchlists[name]
        # Check if already exists
        for s in wl["stocks"]:
            if s["code"] == code:
                return {"success": True, "already_exists": True}
        wl["stocks"].append({"code": code, "name": stock_name, "added_at": datetime.now().strftime("%Y-%m-%d")})
        self._save()
        return {"success": True}

    def remove_from_watchlist(self, name, code):
        if name in self.watchlists:
            self.watchlists[name]["stocks"] = [
                s for s in self.watchlists[name]["stocks"] if s["code"] != code
            ]
            self._save()
            return True
        return False

    def get_watchlist(self, name):
        return self.watchlists.get(name, {"error": "Watchlist not found"})

    def list_watchlists(self):
        results = []
        for name, wl in self.watchlists.items():
            results.append({
                "name": name,
                "description": wl.get("description", ""),
                "count": len(wl.get("stocks", [])),
                "created_at": wl.get("created_at", ""),
            })
        return results


# ============================================================
# Default portfolio
# ============================================================

def get_default_portfolio(manager):
    """Ensure a default portfolio exists"""
    if not manager.portfolios:
        manager.create_portfolio("默认组合", initial_capital=1000000, description="TradeMind 默认模拟组合")
    return list(manager.portfolios.values())[0]


if __name__ == "__main__":
    import sys
    pm = PortfolioManager()

    if len(sys.argv) < 2:
        print("Usage:")
        print("  python portfolio.py list              - List portfolios")
        print("  python portfolio.py create <name>     - Create portfolio")
        print("  python portfolio.py show <id>         - Show portfolio detail")
        print("  python portfolio.py buy <id> <code> <shares> <price>")
        print("  python portfolio.py sell <id> <code>")
        print("  python portfolio.py wl-list           - List watchlists")
        print("  python portfolio.py wl-create <name>")
        print("  python portfolio.py wl-add <name> <code>")
        sys.exit(0)

    cmd = sys.argv[1]

    if cmd == "list":
        for p in pm.list_portfolios():
            print(f"  {p['id']} | {p['name']} | {p['positions']} positions | Value: {p['total_value']:,.0f} | P&L: {p['total_pnl_pct']:+.2f}%")

    elif cmd == "create":
        name = sys.argv[2] if len(sys.argv) > 2 else "New Portfolio"
        p = pm.create_portfolio(name)
        print(f"Created portfolio: {p.name} (id: {p.id})")

    elif cmd == "show":
        pid = sys.argv[2] if len(sys.argv) > 2 else "default"
        result = pm.get_portfolio(pid)
        if "error" in result:
            print(result["error"])
        else:
            print(f"Portfolio: {result['name']}")
            print(f"Initial Capital: {result['initial_capital']:,.0f}")
            print(f"Cash: {result.get('cash', 0):,.0f}")
            print(f"Positions:")
            for pos in result.get("positions", []):
                print(f"  {pos['code']} {pos['name']} | {pos['shares']} shares @ {pos['cost_price']:.2f} | Current: {pos['current_price']:.2f} | P&L: {pos['pnl_pct']:+.2f}%")

    elif cmd == "buy":
        if len(sys.argv) < 6:
            print("Usage: python portfolio.py buy <id> <code> <shares> <price>")
            sys.exit(1)
        result = pm.buy(sys.argv[2], sys.argv[3], sys.argv[3], int(sys.argv[4]), float(sys.argv[5]))
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "sell":
        if len(sys.argv) < 4:
            print("Usage: python portfolio.py sell <id> <code>")
            sys.exit(1)
        result = pm.sell(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False))

    elif cmd == "wl-list":
        for wl in pm.list_watchlists():
            print(f"  {wl['name']} | {wl['count']} stocks | {wl['description']}")

    elif cmd == "wl-create":
        name = sys.argv[2] if len(sys.argv) > 2 else "default"
        pm.create_watchlist(name)
        print(f"Created watchlist: {name}")

    elif cmd == "wl-add":
        if len(sys.argv) < 4:
            print("Usage: python portfolio.py wl-add <name> <code>")
            sys.exit(1)
        result = pm.add_to_watchlist(sys.argv[2], sys.argv[3])
        print(json.dumps(result, ensure_ascii=False))
