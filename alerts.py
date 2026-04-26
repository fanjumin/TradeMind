"""
Real-time price alert system.
Monitors stocks and triggers alerts based on price, indicator, or volume conditions.
"""
import json
import os


class AlertConfig:
    def __init__(self, symbol, alert_type, condition, threshold, message=""):
        self.symbol = symbol
        self.alert_type = alert_type  # 'price_above', 'price_below', 'rsi_oversold', 'rsi_overbought', 'volume_surge', 'break_resistance', 'break_support'
        self.condition = condition
        self.threshold = threshold
        self.message = message or f"{symbol} {alert_type}: {threshold}"
        self.triggered = False
        self.trigger_count = 0


class AlertEngine:
    def __init__(self, config_path=None):
        self.alerts = []
        self.config_path = config_path or os.path.expanduser("~/.trademind_alerts.json")
        self._load()

    def add_alert(self, symbol, alert_type, threshold, message=""):
        alert = AlertConfig(symbol, alert_type, '', threshold, message)
        self.alerts.append(alert)
        self._save()
        return alert

    def remove_alert(self, index):
        if 0 <= index < len(self.alerts):
            self.alerts.pop(index)
            self._save()

    def list_alerts(self):
        lines = ["Alert Configurations:"]
        for i, a in enumerate(self.alerts):
            status = "TRIGGERED" if a.triggered else "ACTIVE"
            lines.append(f"  [{i}] {a.symbol} | {a.alert_type} | threshold={a.threshold} | {status} (fired {a.trigger_count}x)")
        if not self.alerts:
            lines.append("  (no alerts configured)")
        return '\n'.join(lines)

    def check_alerts(self, symbol, price, indicators=None):
        """
        Check all alerts for a given stock.
        Returns list of triggered alerts.
        """
        triggered = []
        for a in self.alerts:
            if a.symbol != symbol:
                continue

            is_triggered = False

            if a.alert_type == 'price_above' and price > a.threshold:
                is_triggered = True
            elif a.alert_type == 'price_below' and price < a.threshold:
                is_triggered = True
            elif a.alert_type == 'rsi_oversold' and indicators and indicators.get('rsi', 100) < a.threshold:
                is_triggered = True
            elif a.alert_type == 'rsi_overbought' and indicators and indicators.get('rsi', 0) > a.threshold:
                is_triggered = True
            elif a.alert_type == 'volume_surge' and indicators and indicators.get('vol_ratio', 0) > a.threshold:
                is_triggered = True
            elif a.alert_type == 'break_resistance' and indicators and price > indicators.get('resistance', float('inf')):
                is_triggered = True
            elif a.alert_type == 'break_support' and indicators and price < indicators.get('support', 0):
                is_triggered = True

            if is_triggered:
                a.triggered = True
                a.trigger_count += 1
                triggered.append({
                    'symbol': a.symbol,
                    'type': a.alert_type,
                    'message': a.message,
                    'price': price,
                    'threshold': a.threshold,
                })

        self._save()
        return triggered

    def _save(self):
        data = []
        for a in self.alerts:
            data.append({
                'symbol': a.symbol,
                'alert_type': a.alert_type,
                'condition': a.condition,
                'threshold': a.threshold,
                'message': a.message,
                'triggered': a.triggered,
                'trigger_count': a.trigger_count,
            })
        with open(self.config_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                for d in data:
                    a = AlertConfig(
                        d['symbol'], d['alert_type'], d.get('condition', ''),
                        d['threshold'], d.get('message', '')
                    )
                    a.triggered = d.get('triggered', False)
                    a.trigger_count = d.get('trigger_count', 0)
                    self.alerts.append(a)
            except:
                pass


def generate_alert_report(symbol, price, indicators, alerts_triggered):
    """Format alert results"""
    lines = []
    lines.append("=" * 60)
    lines.append("  TradeMind - Alert Check")
    lines.append(f"  Symbol: {symbol}  Price: {price}")
    lines.append("=" * 60)

    if alerts_triggered:
        lines.append("")
        lines.append("TRIGGERED ALERTS:")
        for a in alerts_triggered:
            lines.append(f"  *** {a['message']} (current: {a['price']}, threshold: {a['threshold']})")
    else:
        lines.append("")
        lines.append("  No alerts triggered.")

    # Quick indicator check (built-in alerts)
    lines.append("")
    lines.append("--- Quick Health Check ---")
    rsi = indicators.get('rsi', 50)
    if rsi > 80:
        lines.append(f"  WARNING: RSI overbought ({rsi:.1f})")
    elif rsi < 20:
        lines.append(f"  NOTICE: RSI oversold ({rsi:.1f}) - potential bounce")

    kdj = indicators.get('kdj_signal', '')
    if kdj == 'overbought':
        lines.append(f"  WARNING: KDJ overbought (J={indicators.get('j', 0):.1f})")
    elif kdj == 'oversold':
        lines.append(f"  NOTICE: KDJ oversold (J={indicators.get('j', 0):.1f}) - potential bounce")

    boll = indicators.get('boll_position', '')
    if boll == 'above_upper':
        lines.append(f"  WARNING: Price above Bollinger upper band")
    elif boll == 'below_lower':
        lines.append(f"  NOTICE: Price below Bollinger lower band - potential bounce")

    vol = indicators.get('vol_ratio', 1)
    if vol > 2:
        lines.append(f"  NOTICE: Volume surge (ratio {vol:.1f}x)")

    lines.append("=" * 60)
    return '\n'.join(lines)
