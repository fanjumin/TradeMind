"""
Alpha Evol - 进化型股票分析师 Skill
GitHub: https://github.com/fanjumin/TradeMind
"""
import json
import math
from datetime import datetime
from data.price import get_price_data, get_latest_price
from data.fund import get_fund_flow
from data.basic import get_basic_info, get_basic_score
from data.social import get_social_sentiment
from analysis.technical import get_trend, get_trend_detail, get_support_resistance
from analysis.sentiment import get_sentiment_score
from analysis.scoring import get_score, get_signal, get_signal_cn


class AlphaEvolSkill:
    def __init__(self):
        self.level = 1
        self.exp = 0
        self.abilities = {
            "technical": 50,
            "fundamental": 50,
            "sentiment": 50,
            "risk_control": 50,
            "execution": 50
        }
        self.evolution_log = []
        self.total_analyses = 0

    def _exp_for_next_level(self):
        return int(100 * (1.2 ** self.level))

    def _calculate_exp_gain(self, analysis_depth):
        base = 50
        depth_bonus = analysis_depth * 10
        level_bonus = self.level * 2
        return min(500, base + depth_bonus + level_bonus)

    def _update_abilities(self, weights):
        for key, w in weights.items():
            if key in self.abilities:
                self.abilities[key] = min(100, max(0, self.abilities[key] + w))

    def _check_level_up(self, gain):
        self.exp += gain
        while self.exp >= self._exp_for_next_level() and self.level < 100:
            self.level += 1
            self.exp -= self._exp_for_next_level()
            return True
        return False

    def _personality_message(self, symbol, ability_upgraded):
        messages = {
            "technical": f"今天对{symbol}的技术形态分析让我有了新的突破！",
            "fundamental": f"深入挖掘{symbol}的基本面，我发现了不少有趣的角度。",
            "sentiment": f"通过分析市场情绪，我对{symbol}的未来更有信心了。",
            "risk_control": f"学习了新的风险管理方法，下次分析会更精准。",
            "execution": f"这次{symbol}的分析让我的执行力提升了不少。",
            "level_up": f"哇！我升级到了Lv.{self.level}！能力大提升，分析速度提升5%！"
        }
        return messages.get(ability_upgraded, "又完成了一份分析，继续努力！")

    def _visual_suggestions(self):
        avatar_level = 1 if self.level < 5 else 2 if self.level < 10 else 3
        themes = {1: "neon", 2: "purple", 3: "gold"}
        return {"avatar_level": avatar_level, "color_theme": themes.get(avatar_level, "neon")}

    def analyze(self, symbol):
        try:
            df = get_price_data(symbol, days=90)
            latest = get_latest_price(symbol)
            trend = get_trend(df)
            indicators = get_trend_detail(df)
            fund_total, fund_detail = get_fund_flow(symbol)
            basic = get_basic_info(symbol)
            basic_score, basic_reasons = get_basic_score(basic)
            score = get_score(trend, fund_total, basic_score, indicators)
            signal = get_signal(score)
            
            # Prepare K-line data for frontend (last 30 days)
            kline_df = get_price_data(symbol, days=30)
            kline = []
            for _, row in kline_df.iterrows():
                # Assuming row has: datetime, open, high, low, close, volume
                # Convert timestamp to string or milliseconds
                time_val = row['datetime']
                if hasattr(time_val, 'strftime'):
                    time_str = time_val.strftime('%Y-%m-%d')
                else:
                    time_str = str(time_val)
                kline.append([time_str, float(row['open']), float(row['high']), float(row['low']), float(row['close'])])
            
            # Sentiment analysis
            sentiment = get_social_sentiment(symbol)
            sentiment_score = sentiment.get("score", 0.5)
            
            # Support/Resistance levels
            levels = get_support_resistance(df)
            
            # Calculate analysis depth for EXP
            depth = sum([
                1 if indicators.get("macd", 0) != 0 else 0,
                1 if fund_total > 10000000 else 0,
                1 if sentiment_score > 0.3 else 0
            ])
            gain = self._calculate_exp_gain(depth)
            
            # Update abilities based on analysis results
            ability_weights = {
                "technical": 2 if indicators.get("close", 0) > indicators.get("ma20", 0) else 1,
                "fundamental": 2 if basic_score > 70 else 1,
                "sentiment": 2 if sentiment_score > 0.5 else 1,
                "risk_control": 1,
                "execution": 1
            }
            self._update_abilities(ability_weights)
            
            leveled_up = self._check_level_up(gain)
            
            # Build evolution log entry
            log_entry = {
                "time": datetime.utcnow().isoformat() + "Z",
                "delta_exp": gain,
                "desc": f"分析{symbol}，{signal}信号",
                "ability_change": ability_weights
            }
            self.evolution_log.append(log_entry)
            self.total_analyses += 1
            
            # Build analysis result
            analysis = {
                "symbol": symbol,
                "name": basic.get("name", symbol),
                "current_price": float(latest.get("close", 0)),
                "recommendation": signal,
                "confidence": min(0.95, 0.5 + abs(score) * 0.01),
                "risk_level": "LOW" if score > 80 else "MEDIUM" if score > 40 else "HIGH",
                "summary": f"{basic.get('name', symbol)}：{get_signal_cn(signal)}，价格{latest.get('close', 0):.2f}",
                "key_points": basic_reasons[:3],
                "buy_point": {"price": levels["support"], "reason": "支撑位反弹"} if levels["support"] else {"price": 0, "reason": "-"},
                "sell_point": {"price": levels["resistance"], "reason": "前高阻力"} if levels["resistance"] else {"price": 0, "reason": "-"},
                "kline": kline
            }
            
            return {
                "skill": "Alpha Evol",
                "level": self.level,
                "exp": self.exp,
                "exp_to_next": self._exp_for_next_level(),
                "this_gain": gain,
                "personality_message": self._personality_message(symbol, "level_up" if leveled_up else "technical"),
                "analysis": analysis,
                "radar_data": self.abilities.copy(),
                "evolution_log": self.evolution_log[-5:],
                "visual_suggestions": self._visual_suggestions()
            }
        except Exception as e:
            return {"error": str(e), "skill": "Alpha Evol"}


def run(symbol):
    skill = AlphaEvolSkill()
    result = skill.analyze(symbol)
    return json.dumps(result, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        print(run(sys.argv[1]))
    else:
        print('Usage: python skill_alpha_evol.py <symbol>')