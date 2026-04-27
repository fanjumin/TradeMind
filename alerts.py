"""
Multi-dimensional Alert Engine for TradeMind.
Supports 25+ alert types across 6 categories:
  - Price/Level: price break, support/resistance, pivot levels
  - Oscillator: RSI, KDJ, MACD, CCI, WR, MFI, PSY overbought/oversold
  - Trend: golden/death cross, MA cluster, ADX strength change
  - Pattern: candlestick patterns, chart patterns
  - Volume: volume surge, volume anomaly, OBV divergence
  - Resonance: multi-indicator combined signals, anomaly detection
"""
import json
import os
import numpy as np
from typing import List, Dict, Optional, Any


# ============================================================
# Alert Type Registry
# ============================================================

ALERT_CATEGORIES = {
    'price_level': [
        'price_above', 'price_below',
        'break_resistance', 'break_support',
        'near_resistance', 'near_support',
        'break_pivot_r1', 'break_pivot_s1',
    ],
    'oscillator': [
        'rsi_oversold', 'rsi_overbought',
        'kdj_oversold', 'kdj_overbought',
        'macd_golden_cross', 'macd_death_cross', 'macd_divergence',
        'cci_oversold', 'cci_overbought',
        'wr_oversold', 'wr_overbought',
        'mfi_oversold', 'mfi_overbought',
        'psy_oversold', 'psy_overbought',
    ],
    'trend': [
        'ma_golden_cross', 'ma_death_cross',
        'ma_cluster_support', 'ma_cluster_resistance',
        'adx_trend_strong', 'adx_trend_weakening',
        'bollinger_squeeze', 'bollinger_breakout_up', 'bollinger_breakout_down',
        'keltner_breakout_up', 'keltner_breakout_down',
    ],
    'pattern': [
        'doji', 'hammer', 'shooting_star',
        'engulfing_bullish', 'engulfing_bearish',
        'morning_star', 'evening_star',
        'three_white_soldiers', 'three_black_crows',
        'marubozu_bullish', 'marubozu_bearish',
    ],
    'volume': [
        'volume_surge', 'volume_dry_up',
        'volume_anomaly', 'obv_divergence',
        'vwap_breakout_up', 'vwap_breakout_down',
    ],
    'resonance': [
        'bullish_triple', 'bearish_triple',  # 3+ indicators agree
        'divergence_warning',                  # price vs indicator divergence
        'anomaly_price', 'anomaly_volume',    # z-score anomalies
        'ichimoku_signal_change',              # Ichimoku cloud signal change
    ],
}

# Flatten for validation
ALL_ALERT_TYPES = []
for cat in ALERT_CATEGORIES.values():
    ALL_ALERT_TYPES.extend(cat)


# ============================================================
# AlertConfig
# ============================================================

class AlertConfig:
    def __init__(self, symbol: str, alert_type: str, threshold: float = 0,
                 message: str = "", params: dict = None):
        self.symbol = symbol
        self.alert_type = alert_type
        self.threshold = threshold
        self.message = message or f"{symbol} {alert_type} triggered"
        self.params = params or {}
        self.triggered = False
        self.trigger_count = 0
        self.last_triggered = None

    def to_dict(self) -> dict:
        return {
            'symbol': self.symbol,
            'alert_type': self.alert_type,
            'threshold': self.threshold,
            'message': self.message,
            'params': self.params,
            'triggered': self.triggered,
            'trigger_count': self.trigger_count,
            'last_triggered': self.last_triggered,
        }

    @classmethod
    def from_dict(cls, d: dict) -> 'AlertConfig':
        a = cls(d['symbol'], d['alert_type'], d.get('threshold', 0),
                d.get('message', ''), d.get('params', {}))
        a.triggered = d.get('triggered', False)
        a.trigger_count = d.get('trigger_count', 0)
        a.last_triggered = d.get('last_triggered')
        return a


# ============================================================
# Alert Engine
# ============================================================

class AlertEngine:
    """Multi-dimensional alert checking engine."""

    def __init__(self, config_path: str = None):
        self.alerts: List[AlertConfig] = []
        self.config_path = config_path or os.path.expanduser("~/.trademind_alerts.json")
        self._load()

    # ── CRUD ──

    def add_alert(self, symbol: str, alert_type: str, threshold: float = 0,
                  message: str = "", params: dict = None) -> AlertConfig:
        """Add a new alert rule."""
        alert = AlertConfig(symbol, alert_type, threshold, message, params)
        self.alerts.append(alert)
        self._save()
        return alert

    def remove_alert(self, index: int):
        if 0 <= index < len(self.alerts):
            self.alerts.pop(index)
            self._save()

    def clear_alerts(self, symbol: str = None):
        if symbol:
            self.alerts = [a for a in self.alerts if a.symbol != symbol]
        else:
            self.alerts = []
        self._save()

    def list_alerts(self, symbol: str = None) -> str:
        lines = ["Alert Configurations:"]
        filtered = self.alerts
        if symbol:
            filtered = [a for a in self.alerts if a.symbol == symbol]
        if not filtered:
            lines.append(f"  (no alerts {'for ' + symbol if symbol else 'configured'})")
            return '\n'.join(lines)

        for i, a in enumerate(filtered):
            status = "⚠ TRIGGERED" if a.triggered else "  ACTIVE  "
            extra = f" (x{a.trigger_count})" if a.trigger_count else ""
            lines.append(f"  [{i}] {a.symbol:8s} | {a.alert_type:25s} | "
                        f"threshold={a.threshold} | {status}{extra}")
        return '\n'.join(lines)

    def reset_triggered(self):
        """Reset all triggered states (for next check cycle)."""
        for a in self.alerts:
            a.triggered = False
        self._save()

    # ── Check Engine ──

    def check_alerts(self, symbol: str, price: float, indicators: dict = None,
                     df: Any = None, patterns: dict = None,
                     anomaly: dict = None) -> List[dict]:
        """
        Check all alerts for a given stock.
        Parameters:
            symbol: stock code
            price: current price
            indicators: dict from technical.get_trend_detail()
            df: raw OHLCV DataFrame (for pattern detection)
            patterns: dict from technical.detect_candlestick_patterns()
            anomaly: dict from technical.detect_price_anomaly()
        Returns:
            List of triggered alert dicts
        """
        if indicators is None:
            indicators = {}
        triggered = []

        for alert in self.alerts:
            if alert.symbol != symbol:
                continue

            result = self._check_single(alert, price, indicators, df, patterns, anomaly)
            if result:
                alert.triggered = True
                alert.trigger_count += 1
                alert.last_triggered = result.get('date', '')
                triggered.append(result)

        self._save()
        return triggered

    def _check_single(self, alert: AlertConfig, price: float,
                      indicators: dict, df, patterns: dict, anomaly: dict) -> Optional[dict]:
        """Check a single alert rule. Returns trigger dict or None."""
        at = alert.alert_type
        th = alert.threshold
        base = {'symbol': alert.symbol, 'type': at,
                'message': alert.message, 'price': price, 'threshold': th}

        # ── Price/Level ──
        if at == 'price_above' and price > th:
            return {**base, 'detail': f'price {price:.2f} > {th:.2f}'}
        if at == 'price_below' and price < th:
            return {**base, 'detail': f'price {price:.2f} < {th:.2f}'}
        if at == 'break_resistance' and price > indicators.get('resistance', float('inf')):
            return {**base, 'detail': f'broke resistance {indicators["resistance"]:.2f}'}
        if at == 'break_support' and price < indicators.get('support', -float('inf')):
            return {**base, 'detail': f'broke support {indicators["support"]:.2f}'}
        if at == 'near_resistance':
            res = indicators.get('resistance', 0)
            if res > 0 and (res - price) / price * 100 < th:
                return {**base, 'detail': f'{((res-price)/price*100):.1f}% from resistance'}
        if at == 'near_support':
            sup = indicators.get('support', 0)
            if sup > 0 and (price - sup) / price * 100 < th:
                return {**base, 'detail': f'{((price-sup)/price*100):.1f}% from support'}
        if at == 'break_pivot_r1':
            r1 = indicators.get('r1', float('inf'))
            if price > r1:
                return {**base, 'detail': f'broke R1 {r1:.2f}'}
        if at == 'break_pivot_s1':
            s1 = indicators.get('s1', -float('inf'))
            if price < s1:
                return {**base, 'detail': f'broke S1 {s1:.2f}'}

        # ── Oscillator ──
        if at == 'rsi_oversold' and indicators.get('rsi', 100) < th:
            return {**base, 'detail': f'RSI={indicators["rsi"]:.1f}'}
        if at == 'rsi_overbought' and indicators.get('rsi', 0) > th:
            return {**base, 'detail': f'RSI={indicators["rsi"]:.1f}'}
        if at == 'kdj_oversold' and indicators.get('j', 100) < th:
            return {**base, 'detail': f'KDJ J={indicators["j"]:.1f}'}
        if at == 'kdj_overbought' and indicators.get('j', 0) > th:
            return {**base, 'detail': f'KDJ J={indicators["j"]:.1f}'}
        if at == 'macd_golden_cross' and indicators.get('macd_signal') == 'golden_cross_pending':
            return {**base, 'detail': 'MACD golden cross signal'}
        if at == 'macd_death_cross' and indicators.get('macd_signal') == 'death_cross_pending':
            return {**base, 'detail': 'MACD death cross signal'}
        if at == 'macd_divergence' and indicators.get('macd_divergence', 'none') != 'none':
            return {**base, 'detail': f'MACD {indicators["macd_divergence"]} divergence'}
        if at == 'cci_oversold' and indicators.get('cci', 0) < th:
            return {**base, 'detail': f'CCI={indicators["cci"]:.1f}'}
        if at == 'cci_overbought' and indicators.get('cci', 0) > th:
            return {**base, 'detail': f'CCI={indicators["cci"]:.1f}'}
        if at == 'wr_oversold' and indicators.get('wr', 0) < th:  # WR is inverted
            return {**base, 'detail': f'WR={indicators["wr"]:.1f}'}
        if at == 'wr_overbought' and indicators.get('wr', 0) > th:
            return {**base, 'detail': f'WR={indicators["wr"]:.1f}'}
        if at == 'mfi_oversold' and indicators.get('mfi', 100) < th:
            return {**base, 'detail': f'MFI={indicators["mfi"]:.1f}'}
        if at == 'mfi_overbought' and indicators.get('mfi', 0) > th:
            return {**base, 'detail': f'MFI={indicators["mfi"]:.1f}'}
        if at == 'psy_oversold' and indicators.get('psy', 100) < th:
            return {**base, 'detail': f'PSY={indicators["psy"]:.1f}'}
        if at == 'psy_overbought' and indicators.get('psy', 0) > th:
            return {**base, 'detail': f'PSY={indicators["psy"]:.1f}'}

        # ── Trend ──
        if at == 'ma_golden_cross':
            ma5, ma20 = indicators.get('ma5', 0), indicators.get('ma20', 0)
            if ma5 > 0 and ma20 > 0:
                prev_ratio = (ma5 - ma20) / ma20 * 100 if indicators.get('ma20_prev', ma20) else 0
                curr_ratio = (ma5 - ma20) / ma20 * 100
                if prev_ratio < 0 and curr_ratio > 0:
                    return {**base, 'detail': f'MA5({ma5:.2f}) crossed above MA20({ma20:.2f})'}
        if at == 'ma_death_cross':
            ma5, ma20 = indicators.get('ma5', 0), indicators.get('ma20', 0)
            if ma5 > 0 and ma20 > 0:
                prev_ratio = (ma5 - ma20) / ma20 * 100 if indicators.get('ma20_prev', ma20) else 0
                curr_ratio = (ma5 - ma20) / ma20 * 100
                if prev_ratio > 0 and curr_ratio < 0:
                    return {**base, 'detail': f'MA5({ma5:.2f}) crossed below MA20({ma20:.2f})'}
        if at == 'adx_trend_strong' and indicators.get('adx', 0) > 40:
            return {**base, 'detail': f'ADX={indicators["adx"]:.1f} strong trend'}
        if at == 'adx_trend_weakening' and indicators.get('adx', 100) < 20:
            return {**base, 'detail': 'ADX low — trend weakening'}
        if at == 'bollinger_squeeze' and indicators.get('boll_squeeze') == 'squeeze':
            return {**base, 'detail': f'BB width={indicators["boll_width"]:.1f}%'}
        if at == 'bollinger_breakout_up' and indicators.get('boll_position') == 'above_upper':
            return {**base, 'detail': f'price above BB upper {indicators["boll_upper"]:.2f}'}
        if at == 'bollinger_breakout_down' and indicators.get('boll_position') == 'below_lower':
            return {**base, 'detail': f'price below BB lower {indicators["boll_lower"]:.2f}'}
        if at == 'keltner_breakout_up' and indicators.get('keltner_signal') == 'above_upper':
            return {**base, 'detail': 'price above Keltner upper'}
        if at == 'keltner_breakout_down' and indicators.get('keltner_signal') == 'below_lower':
            return {**base, 'detail': 'price below Keltner lower'}

        # ── Pattern ──
        if at in ALERT_CATEGORIES['pattern'] and patterns:
            status = patterns.get(at, False)
            if isinstance(status, (bool, np.bool_)):
                is_triggered = bool(status)
            else:
                is_triggered = False
            if is_triggered:
                return {**base, 'detail': f'pattern: {at}'}

        # ── Volume ──
        if at == 'volume_surge' and indicators.get('vol_ratio', 0) > th:
            return {**base, 'detail': f'volume {indicators["vol_ratio"]:.1f}x normal'}
        if at == 'volume_dry_up' and indicators.get('vol_ratio', 1) < th:
            return {**base, 'detail': f'volume only {indicators["vol_ratio"]:.2f}x normal'}
        if at == 'volume_anomaly' and indicators.get('vol_ratio', 1) > 3:
            return {**base, 'detail': f'extreme volume {indicators["vol_ratio"]:.1f}x'}
        if at == 'obv_divergence' and indicators.get('obv_signal', '') in ['bullish_divergence', 'bearish_divergence']:
            return {**base, 'detail': f'OBV {indicators["obv_signal"]}'}
        if at == 'vwap_breakout_up':
            vwap = indicators.get('vwap_20', 0)
            if vwap > 0 and price > vwap:
                return {**base, 'detail': f'price above VWAP {vwap:.2f}'}
        if at == 'vwap_breakout_down':
            vwap = indicators.get('vwap_20', 0)
            if vwap > 0 and price < vwap:
                return {**base, 'detail': f'price below VWAP {vwap:.2f}'}

        # ── Resonance (Multi-indicator) ──
        if at == 'bullish_triple':
            score = self._bullish_score(indicators)
            if score >= th:
                return {**base, 'detail': f'{score} bullish signals'}
        if at == 'bearish_triple':
            score = self._bearish_score(indicators)
            if score >= th:
                return {**base, 'detail': f'{score} bearish signals'}
        if at == 'divergence_warning':
            divergent = self._check_divergence_warning(indicators, price)
            if divergent:
                return {**base, 'detail': divergent}
        if at == 'anomaly_price' and anomaly and anomaly.get('anomaly', False):
            return {**base, 'detail': f'price anomaly z={anomaly["anomaly_z_score"]:.1f} {anomaly["anomaly_direction"]}'}
        if at == 'anomaly_volume' and indicators.get('vol_ratio', 1) > 3:
            return {**base, 'detail': f'volume anomaly {indicators["vol_ratio"]:.1f}x'}
        if at == 'ichimoku_signal_change':
            sig = indicators.get('ichimoku_signal', '')
            if 'bullish' in sig and 'above_cloud' in sig:
                return {**base, 'detail': f'Ichimoku: {sig}'}

        return None

    # ── Scoring helpers ──

    def _bullish_score(self, ind: dict) -> int:
        score = 0
        if ind.get('rsi_signal') in ['oversold', 'weak']: score += 1
        if ind.get('kdj_signal') == 'bullish': score += 1
        if ind.get('macd_signal') in ['long', 'golden_cross_pending']: score += 1
        if ind.get('cci_signal') == 'oversold': score += 1
        if ind.get('wr_signal') == 'oversold': score += 1
        if ind.get('mfi_signal') == 'oversold': score += 1
        if ind.get('obv_signal') == 'bullish_divergence': score += 1
        if ind.get('macd_divergence') == 'bullish': score += 1
        if ind.get('dma_signal') == 'golden_cross': score += 1
        if ind.get('trix_signal') == 'golden_cross': score += 1
        return score

    def _bearish_score(self, ind: dict) -> int:
        score = 0
        if ind.get('rsi_signal') in ['overbought', 'strong']: score += 1
        if ind.get('kdj_signal') == 'bearish': score += 1
        if ind.get('macd_signal') in ['short', 'death_cross_pending']: score += 1
        if ind.get('cci_signal') == 'overbought': score += 1
        if ind.get('wr_signal') == 'overbought': score += 1
        if ind.get('mfi_signal') == 'overbought': score += 1
        if ind.get('obv_signal') == 'bearish_divergence': score += 1
        if ind.get('macd_divergence') == 'bearish': score += 1
        if ind.get('dma_signal') == 'death_cross': score += 1
        if ind.get('trix_signal') == 'death_cross': score += 1
        return score

    def _check_divergence_warning(self, ind: dict, price: float) -> Optional[str]:
        """Check for price vs indicator divergence."""
        warnings = []
        divergence = ind.get('macd_divergence', 'none')
        if divergence == 'bearish':
            warnings.append('MACD bearish divergence')
        elif divergence == 'bullish':
            warnings.append('MACD bullish divergence')
        if ind.get('obv_signal') == 'bearish_divergence':
            warnings.append('OBV bearish divergence')
        elif ind.get('obv_signal') == 'bullish_divergence':
            warnings.append('OBV bullish divergence')
        return ', '.join(warnings) if warnings else None

    # ── Persistence ──

    def _save(self):
        data = [a.to_dict() for a in self.alerts]
        os.makedirs(os.path.dirname(self.config_path) or '.', exist_ok=True)
        with open(self.config_path, 'w') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path) as f:
                    data = json.load(f)
                self.alerts = [AlertConfig.from_dict(d) for d in data]
            except Exception:
                pass


# ============================================================
# Quick Alert Presets
# ============================================================

PRESET_ALERTS = {
    'value_buy': [
        ('rsi_oversold', 30, 'RSI oversold — potential value buy'),
        ('kdj_oversold', 0, 'KDJ oversold — potential bounce'),
        ('psy_oversold', 25, 'PSY extreme fear'),
    ],
    'trend_follow': [
        ('ma_golden_cross', 0, 'MA golden cross — trend start'),
        ('macd_golden_cross', 0, 'MACD golden cross'),
        ('adx_trend_strong', 0, 'ADX > 40 — strong trend'),
    ],
    'breakout': [
        ('break_resistance', 0, 'Broke resistance level'),
        ('bollinger_breakout_up', 0, 'Bollinger breakout up'),
        ('keltner_breakout_up', 0, 'Keltner breakout up'),
    ],
    'reversal_watch': [
        ('macd_divergence', 0, 'MACD divergence — possible reversal'),
        ('bullish_triple', 4, '4+ bullish signals — potential bottom'),
        ('bearish_triple', 4, '4+ bearish signals — potential top'),
    ],
    'risk_control': [
        ('price_below', 0, 'Price alert — stop loss'),
        ('break_support', 0, 'Broke support — exit signal'),
        ('ma_death_cross', 0, 'MA death cross — trend reversal'),
    ],
}


def apply_preset(engine: AlertEngine, symbol: str, preset_name: str) -> int:
    """Apply a preset alert template to a symbol. Returns count added."""
    if preset_name not in PRESET_ALERTS:
        return 0
    count = 0
    for alert_type, threshold, message in PRESET_ALERTS[preset_name]:
        engine.add_alert(symbol, alert_type, threshold, f"[{preset_name}] {message}")
        count += 1
    return count


# ============================================================
# Report Generation
# ============================================================

def generate_alert_report(symbol: str, price: float, indicators: dict,
                          alerts_triggered: list, patterns: dict = None,
                          anomaly: dict = None) -> str:
    """Generate comprehensive alert check report."""
    lines = []
    lines.append("=" * 65)
    lines.append(f"  TradeMind Alert Check — {symbol}")
    lines.append(f"  Price: ¥{price:.2f}    Date: (latest)")
    lines.append("=" * 65)

    # Triggered alerts
    if alerts_triggered:
        lines.append("")
        lines.append(f"  ⚠ TRIGGERED ALERTS ({len(alerts_triggered)}):")
        for a in alerts_triggered:
            detail = a.get('detail', '')
            lines.append(f"  *** {a['type']}: {detail}")
            lines.append(f"      {a['message']}")
    else:
        lines.append("")
        lines.append("  ✓ No alerts triggered.")

    # Quick Health Check
    lines.append("")
    lines.append("  ── Quick Health Check ──")

    # RSI
    rsi = indicators.get('rsi', 50)
    if rsi > 80:
        lines.append(f"  ⚠ RSI={rsi:.1f} OVERBOUGHT — reversal risk")
    elif rsi > 70:
        lines.append(f"  ⚡ RSI={rsi:.1f} approaching overbought")
    elif rsi < 20:
        lines.append(f"  💡 RSI={rsi:.1f} OVERSOLD — potential bounce")
    elif rsi < 30:
        lines.append(f"  🔍 RSI={rsi:.1f} approaching oversold")

    # KDJ
    j_val = indicators.get('j', 50)
    if j_val > 100:
        lines.append(f"  ⚠ KDJ J={j_val:.1f} OVERBOUGHT")
    elif j_val < 0:
        lines.append(f"  💡 KDJ J={j_val:.1f} OVERSOLD")

    # MACD divergence
    div = indicators.get('macd_divergence', 'none')
    if div == 'bearish':
        lines.append(f"  ⚠ MACD bearish divergence — top signal")
    elif div == 'bullish':
        lines.append(f"  💡 MACD bullish divergence — bottom signal")

    # Bollinger
    boll_pos = indicators.get('boll_position', '')
    if boll_pos == 'above_upper':
        lines.append(f"  ⚠ Price above Bollinger upper band")
    elif boll_pos == 'below_lower':
        lines.append(f"  💡 Price below Bollinger lower band")

    squeeze = indicators.get('boll_squeeze', '')
    if squeeze == 'squeeze':
        lines.append(f"  🔍 Bollinger squeeze — potential breakout")

    # Volume
    vol_ratio = indicators.get('vol_ratio', 1)
    if vol_ratio > 3:
        lines.append(f"  ⚡ Extreme volume {vol_ratio:.1f}x normal")
    elif vol_ratio > 2:
        lines.append(f"  📊 High volume {vol_ratio:.1f}x normal")
    elif vol_ratio < 0.3:
        lines.append(f"  💤 Volume dried up {vol_ratio:.2f}x")

    # Anomaly
    if anomaly and anomaly.get('anomaly'):
        lines.append(f"  🚨 PRICE ANOMALY: z={anomaly['anomaly_z_score']:.1f} "
                    f"direction={anomaly['anomaly_direction']}")

    # Patterns
    if patterns:
        active = [k for k, v in patterns.items() if v]
        if active:
            lines.append(f"  📐 Candlestick patterns: {', '.join(active)}")

    # Resonance score
    bullish = _count_signals(indicators, 'bullish')
    bearish = _count_signals(indicators, 'bearish')
    if bullish >= 4:
        lines.append(f"  💪 BULLISH RESONANCE: {bullish} indicators aligned")
    if bearish >= 4:
        lines.append(f"  ⚠ BEARISH RESONANCE: {bearish} indicators aligned")

    lines.append("")
    lines.append("=" * 65)
    return '\n'.join(lines)


def _count_signals(ind: dict, direction: str) -> int:
    """Count directional signals across indicators."""
    count = 0
    if direction == 'bullish':
        if ind.get('rsi_signal') in ['oversold', 'weak']: count += 1
        if ind.get('kdj_signal') == 'bullish': count += 1
        if ind.get('macd_signal') in ['long', 'golden_cross_pending']: count += 1
        if ind.get('cci_signal') == 'oversold': count += 1
        if ind.get('wr_signal') == 'oversold': count += 1
        if ind.get('mfi_signal') == 'oversold': count += 1
        if ind.get('macd_divergence') == 'bullish': count += 1
        if ind.get('obv_signal') == 'bullish_divergence': count += 1
        if ind.get('dma_signal') == 'golden_cross': count += 1
    else:
        if ind.get('rsi_signal') in ['overbought', 'strong']: count += 1
        if ind.get('kdj_signal') == 'bearish': count += 1
        if ind.get('macd_signal') in ['short', 'death_cross_pending']: count += 1
        if ind.get('cci_signal') == 'overbought': count += 1
        if ind.get('wr_signal') == 'overbought': count += 1
        if ind.get('mfi_signal') == 'overbought': count += 1
        if ind.get('macd_divergence') == 'bearish': count += 1
        if ind.get('obv_signal') == 'bearish_divergence': count += 1
        if ind.get('dma_signal') == 'death_cross': count += 1
    return count


# ============================================================
# Convenience: run full alert check on a stock
# ============================================================

def check_stock_alerts(symbol: str, df, engine: AlertEngine = None,
                       config_path: str = None) -> dict:
    """
    Full alert check: compute indicators, patterns, anomaly,
    then check all configured alerts.
    Returns: dict with triggered, report, indicators, patterns, anomaly
    """
    from analysis.technical import get_trend_detail, detect_candlestick_patterns, detect_price_anomaly

    indicators = get_trend_detail(df)
    patterns = detect_candlestick_patterns(df)
    anomaly = detect_price_anomaly(df)
    price = indicators.get('close', 0)

    if engine is None:
        engine = AlertEngine(config_path)

    triggered = engine.check_alerts(symbol, price, indicators, df, patterns, anomaly)
    report = generate_alert_report(symbol, price, indicators, triggered, patterns, anomaly)

    return {
        'triggered': triggered,
        'report': report,
        'indicators': indicators,
        'patterns': patterns,
        'anomaly': anomaly,
        'engine': engine,
    }
