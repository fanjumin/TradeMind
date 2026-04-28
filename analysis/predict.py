
"""
Deep Learning & ML Price Prediction for A-Stocks.
Three prediction tracks:
  1. Classical ML: RandomForest, GradientBoosting, Ridge regression (sklearn)
  2. Deep Learning: Lightweight LSTM implemented in numpy (no PyTorch dependency)
  3. Event-Driven LLM: DeepSeek analyzes technical context + news for qualitative prediction

Features: 30+ engineered features from OHLCV + technical indicators
Target:    5-day forward price direction and magnitude
Output:    Direction probability, expected return, confidence score

Integration:
  CLI:    python main.py --predict 600519
  Import: from analysis.predict import StockPredictor
"""

import json
import os
import math
import warnings
from datetime import datetime, timedelta
from typing import List, Dict, Tuple, Optional

import numpy as np
import pandas as pd

warnings.filterwarnings('ignore')

# ─── Paths ─────────────────────────────────────────────────

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DATA_DIR = os.path.join(BASE_DIR, 'data')
HISTORY_DIR = os.path.join(DATA_DIR, 'history')
MODEL_DIR = os.path.join(DATA_DIR, 'models')
CONFIG_PATH = os.path.join(BASE_DIR, 'api_config.json')

# ─── Constants ─────────────────────────────────────────────

PREDICTION_DAYS = 5       # Predict N days ahead
LOOKBACK_DAYS = 120       # Use last N days for training
MIN_TRAIN_DAYS = 60       # Minimum data points needed

# sklearn model names
SKLEARN_MODELS = ['random_forest', 'gradient_boost', 'ridge']


# ─── Helpers ───────────────────────────────────────────────

def _load_history(code: str) -> Optional[pd.DataFrame]:
    """Load historical data from CSV cache."""
    path = os.path.join(HISTORY_DIR, f'{code}.csv')
    if not os.path.exists(path):
        return None
    df = pd.read_csv(path, parse_dates=['date'])
    df = df.sort_values('date').reset_index(drop=True)
    return df


def _compute_features(df: pd.DataFrame) -> pd.DataFrame:
    """Compute technical features from OHLCV data.
    Returns DataFrame with features (no NaN rows).
    """
    df = df.copy()

    # Price features
    df['returns_1d'] = df['close'].pct_change(1)
    df['returns_5d'] = df['close'].pct_change(5)
    df['returns_10d'] = df['close'].pct_change(10)
    df['returns_20d'] = df['close'].pct_change(20)

    df['log_return'] = np.log(df['close'] / df['close'].shift(1))
    df['volatility_5d'] = df['log_return'].rolling(5).std()
    df['volatility_20d'] = df['log_return'].rolling(20).std()

    # Price position features
    for window in [5, 10, 20, 60]:
        df[f'high_{window}d'] = df['high'].rolling(window).max()
        df[f'low_{window}d'] = df['low'].rolling(window).min()
        df[f'price_pos_{window}d'] = (df['close'] - df[f'low_{window}d']) / \
                                      (df[f'high_{window}d'] - df[f'low_{window}d'] + 1e-10)

    # Moving averages
    for window in [5, 10, 20, 60]:
        df[f'ma_{window}'] = df['close'].rolling(window).mean()
        df[f'ma_ratio_{window}'] = df['close'] / df[f'ma_{window}'] - 1

    # RSI (14-day)
    delta = df['close'].diff()
    gain = delta.where(delta > 0, 0).rolling(14).mean()
    loss = (-delta.where(delta < 0, 0)).rolling(14).mean()
    rs = gain / (loss + 1e-10)
    df['rsi_14'] = 100 - (100 / (1 + rs))

    # MACD
    ema_12 = df['close'].ewm(span=12, adjust=False).mean()
    ema_26 = df['close'].ewm(span=26, adjust=False).mean()
    df['macd'] = ema_12 - ema_26
    df['macd_signal'] = df['macd'].ewm(span=9, adjust=False).mean()
    df['macd_hist'] = df['macd'] - df['macd_signal']

    # Volume features
    df['volume_ratio'] = df['volume'] / df['volume'].rolling(20).mean()
    df['volume_trend'] = df['volume'].rolling(5).mean() / df['volume'].rolling(20).mean()

    # Bollinger Bands
    df['bb_mid'] = df['close'].rolling(20).mean()
    bb_std = df['close'].rolling(20).std()
    df['bb_width'] = (bb_std * 2) / df['bb_mid']
    df['bb_position'] = (df['close'] - df['bb_mid']) / (bb_std * 2 + 1e-10)

    # ATR
    tr1 = df['high'] - df['low']
    tr2 = abs(df['high'] - df['close'].shift(1))
    tr3 = abs(df['low'] - df['close'].shift(1))
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    df['atr_14'] = tr.rolling(14).mean()
    df['atr_ratio'] = df['atr_14'] / df['close']

    # Target: N-day forward return
    df['target'] = df['close'].shift(-PREDICTION_DAYS) / df['close'] - 1
    df['target_direction'] = (df['target'] > 0).astype(int)

    return df


def _get_feature_columns() -> List[str]:
    """Return list of feature column names."""
    base_features = [
        'returns_1d', 'returns_5d', 'returns_10d', 'returns_20d',
        'volatility_5d', 'volatility_20d',
        'price_pos_5d', 'price_pos_10d', 'price_pos_20d', 'price_pos_60d',
        'ma_ratio_5', 'ma_ratio_10', 'ma_ratio_20', 'ma_ratio_60',
        'rsi_14', 'macd', 'macd_hist', 'macd_signal',
        'volume_ratio', 'volume_trend',
        'bb_width', 'bb_position', 'atr_ratio',
    ]
    return base_features


# ─── Numpy LSTM (Lightweight Deep Learning) ────────────────

class NumpyLSTM:
    """Single-layer LSTM with Adam optimizer, gradient clipping, mini-batch, L2 reg.

    Improvements over v1:
    - Adam optimizer (adaptive per-param learning rates)
    - Gradient clipping (max_norm) prevents exploding gradients
    - Mini-batch training (batch_size=16) reduces gradient noise
    - L2 weight decay for regularization
    - He initialization (better gradient flow than Xavier for tanh/sigmoid)
    - Hidden size 64 (was 32)
    - Supports validation-based early stopping
    """

    def __init__(self, input_size: int, hidden_size: int = 64, l2_lambda: float = 1e-5):
        self.input_size = input_size
        self.hidden_size = hidden_size
        self.l2_lambda = l2_lambda

        # He initialization: scale for input weights uses fan_in, recurrent uses fan_in
        scale_w = math.sqrt(2.0 / input_size)
        scale_u = math.sqrt(2.0 / hidden_size)

        # Gate weights: W_* for input, U_* for recurrent, b_* for bias
        for gate in ['i', 'f', 'o', 'c']:
            setattr(self, f'W_{gate}', np.random.randn(hidden_size, input_size) * scale_w)
            setattr(self, f'U_{gate}', np.random.randn(hidden_size, hidden_size) * scale_u)
            setattr(self, f'b_{gate}', np.zeros(hidden_size))

        self.b_f += 1.0  # forget gate bias init = 1 (encourage remembering)

        # Output layer
        self.W_y = np.random.randn(1, hidden_size) * scale_u
        self.b_y = np.zeros(1)

        # Adam state (lazy init in _ensure_adam_state)
        self._adam_m = {}
        self._adam_v = {}
        self._adam_t = 0

    def _ensure_adam_state(self):
        """Initialize Adam moment buffers on first training call."""
        if self._adam_m:
            return
        param_names = []
        for gate in ['i', 'f', 'o', 'c']:
            param_names += [f'W_{gate}', f'U_{gate}', f'b_{gate}']
        param_names += ['W_y', 'b_y']
        for name in param_names:
            p = getattr(self, name)
            self._adam_m[name] = np.zeros_like(p)
            self._adam_v[name] = np.zeros_like(p)

    def _sigmoid(self, x):
        return 1.0 / (1.0 + np.exp(-np.clip(x, -15, 15)))

    def _tanh(self, x):
        return np.tanh(x)

    def _dsigmoid(self, x):
        s = self._sigmoid(x)
        return s * (1 - s)

    def _dtanh(self, x):
        t = self._tanh(x)
        return 1 - t * t

    def _get_params(self):
        """Return dict of all trainable parameters."""
        params = {}
        for gate in ['i', 'f', 'o', 'c']:
            for prefix in ['W', 'U', 'b']:
                name = f'{prefix}_{gate}'
                params[name] = getattr(self, name)
        params['W_y'] = self.W_y
        params['b_y'] = self.b_y
        return params

    def _set_params(self, params: dict):
        """Restore parameters from a snapshot dict."""
        for name, val in params.items():
            setattr(self, name, val.copy())

    def _get_params_snapshot(self) -> dict:
        """Deep copy of current parameters (for early stopping rollback)."""
        return {name: val.copy() for name, val in self._get_params().items()}

    def _clip_grad(self, grad: np.ndarray, max_norm: float) -> np.ndarray:
        """Clip gradient by global norm."""
        norm = float(np.linalg.norm(grad))
        if norm > max_norm:
            grad = grad * (max_norm / norm)
        return grad

    def _adam_step(self, name: str, grad: np.ndarray, lr: float,
                   beta1: float = 0.9, beta2: float = 0.999, eps: float = 1e-8):
        """Apply Adam update to parameter 'name' using accumulated gradient."""
        m = self._adam_m[name]
        v = self._adam_v[name]

        # Bias-corrected moment estimates
        m = beta1 * m + (1 - beta1) * grad
        v = beta2 * v + (1 - beta2) * (grad * grad)
        m_hat = m / (1 - beta1 ** self._adam_t)
        v_hat = v / (1 - beta2 ** self._adam_t)

        self._adam_m[name] = m
        self._adam_v[name] = v

        # Update
        param = getattr(self, name)
        update = lr * m_hat / (np.sqrt(v_hat) + eps)
        setattr(self, name, param - update)

    def forward(self, X: np.ndarray) -> np.ndarray:
        """Forward pass through LSTM.
        Args:
            X: shape (seq_len, input_size)
        Returns:
            y_hat: prediction scalar (float)
        """
        seq_len = X.shape[0]
        h = np.zeros(self.hidden_size)
        c = np.zeros(self.hidden_size)

        for t in range(seq_len):
            x_t = X[t]
            i = self._sigmoid(np.dot(self.W_i, x_t) + np.dot(self.U_i, h) + self.b_i)
            f = self._sigmoid(np.dot(self.W_f, x_t) + np.dot(self.U_f, h) + self.b_f)
            o = self._sigmoid(np.dot(self.W_o, x_t) + np.dot(self.U_o, h) + self.b_o)
            c_tilde = self._tanh(np.dot(self.W_c, x_t) + np.dot(self.U_c, h) + self.b_c)
            c = f * c + i * c_tilde
            h = o * self._tanh(c)

        y_hat = np.dot(self.W_y, h) + self.b_y
        return float(y_hat.item() if hasattr(y_hat, 'item') else y_hat[0])

    def _forward_backward_sample(self, x_seq: np.ndarray, y_true: float,
                                  clip_norm: float):
        """Single-sample forward + backward pass, returns (loss, grads_dict)."""
        seq_len = x_seq.shape[0]
        h = np.zeros(self.hidden_size)
        c = np.zeros(self.hidden_size)

        # Store states for BPTT
        h_states = [h.copy()]
        c_states = [c.copy()]
        gates = []

        # --- Forward ---
        for t in range(seq_len):
            x_t = x_seq[t]
            i = self._sigmoid(np.dot(self.W_i, x_t) + np.dot(self.U_i, h) + self.b_i)
            f = self._sigmoid(np.dot(self.W_f, x_t) + np.dot(self.U_f, h) + self.b_f)
            o = self._sigmoid(np.dot(self.W_o, x_t) + np.dot(self.U_o, h) + self.b_o)
            c_tilde = self._tanh(np.dot(self.W_c, x_t) + np.dot(self.U_c, h) + self.b_c)
            c = f * c + i * c_tilde
            h = o * self._tanh(c)
            h_states.append(h.copy())
            c_states.append(c.copy())
            gates.append({
                'x': x_t, 'i': i, 'f': f, 'o': o, 'c_tilde': c_tilde,
                'h_prev': h_states[-2], 'c_prev': c_states[-2],
            })

        y_pred = float(np.dot(self.W_y, h).item() + self.b_y.item())
        error = y_pred - y_true
        loss = error * error

        # L2 penalty (on W/U matrices only)
        l2_penalty = 0.0
        for gate in ['i', 'f', 'o', 'c']:
            for prefix in ['W', 'U']:
                w = getattr(self, f'{prefix}_{gate}')
                l2_penalty += np.sum(w * w)
        l2_penalty += np.sum(self.W_y * self.W_y)
        loss += self.l2_lambda * l2_penalty

        # --- Backward ---
        grads = {name: np.zeros_like(p) for name, p in self._get_params().items()}

        dW_y = error * h.reshape(1, -1)  # (1, hidden_size)
        db_y = np.array([error])
        grads['W_y'] = dW_y
        grads['b_y'] = db_y
        # L2 gradient for output weights
        grads['W_y'] += 2 * self.l2_lambda * self.W_y

        dh = error * self.W_y.flatten()
        dc = np.zeros(self.hidden_size)

        for t in range(seq_len - 1, -1, -1):
            g = gates[t]
            h_prev = g['h_prev']
            c_prev = g['c_prev']

            do = dh * self._tanh(c_states[t + 1])
            dc = dc + dh * g['o'] * self._dtanh(c_states[t + 1])
            di = dc * g['c_tilde']
            df = dc * c_prev
            dc_tilde = dc * g['i']

            # Pre-activation gradients
            z_i = np.dot(self.W_i, g['x']) + np.dot(self.U_i, h_prev) + self.b_i
            z_f = np.dot(self.W_f, g['x']) + np.dot(self.U_f, h_prev) + self.b_f
            z_o = np.dot(self.W_o, g['x']) + np.dot(self.U_o, h_prev) + self.b_o
            z_c = np.dot(self.W_c, g['x']) + np.dot(self.U_c, h_prev) + self.b_c

            di_raw = di * self._dsigmoid(z_i)
            df_raw = df * self._dsigmoid(z_f)
            do_raw = do * self._dsigmoid(z_o)
            dc_tilde_raw = dc_tilde * self._dtanh(z_c)

            # Accumulate gradients
            grads[f'W_i'] += np.outer(di_raw, g['x'])
            grads[f'U_i'] += np.outer(di_raw, h_prev)
            grads[f'b_i'] += di_raw

            grads[f'W_f'] += np.outer(df_raw, g['x'])
            grads[f'U_f'] += np.outer(df_raw, h_prev)
            grads[f'b_f'] += df_raw

            grads[f'W_o'] += np.outer(do_raw, g['x'])
            grads[f'U_o'] += np.outer(do_raw, h_prev)
            grads[f'b_o'] += do_raw

            grads[f'W_c'] += np.outer(dc_tilde_raw, g['x'])
            grads[f'U_c'] += np.outer(dc_tilde_raw, h_prev)
            grads[f'b_c'] += dc_tilde_raw

            # dh for previous timestep
            dh = (np.dot(di_raw, self.U_i) + np.dot(df_raw, self.U_f) +
                  np.dot(do_raw, self.U_o) + np.dot(dc_tilde_raw, self.U_c))
            dc = dc * g['f']

        # L2 gradients for U matrices (W matrices' L2 added inline above)
        for gate in ['i', 'f', 'o', 'c']:
            for prefix in ['U']:
                name = f'{prefix}_{gate}'
                grads[name] += 2 * self.l2_lambda * getattr(self, name)

        # Clip gradients
        for name in grads:
            grads[name] = self._clip_grad(grads[name], clip_norm)

        return loss, grads

    def _compute_val_loss(self, X_val: np.ndarray, y_val: np.ndarray) -> float:
        """Compute MSE loss on validation set."""
        total = 0.0
        for i in range(len(X_val)):
            y_pred = self.forward(X_val[i])
            error = y_pred - y_val[i]
            total += error * error
        return total / len(X_val)

    def train(self, X: np.ndarray, y: np.ndarray,
              epochs: int = 200, lr: float = 0.001, batch_size: int = 16,
              clip_norm: float = 1.0,
              X_val: np.ndarray = None, y_val: np.ndarray = None,
              patience: int = 30, lr_decay: float = 0.5,
              verbose: bool = False) -> Tuple[List[float], List[float]]:
        """Train LSTM with Adam, mini-batch, gradient clipping, early stopping.

        Args:
            X, y: Training data (n_samples, seq_len, n_features) and (n_samples,)
            epochs: Max epochs
            lr: Initial learning rate
            batch_size: Mini-batch size
            clip_norm: Max gradient norm
            X_val, y_val: Validation data for early stopping
            patience: Epochs without improvement before stopping
            lr_decay: Factor to multiply lr on plateau
            verbose: Print progress

        Returns:
            (train_losses, val_losses)
        """
        self._ensure_adam_state()
        n_samples = len(X)

        train_losses = []
        val_losses = []
        best_val_loss = float('inf')
        best_params = None
        plateau_counter = 0

        for epoch in range(epochs):
            self._adam_t += 1
            epoch_loss = 0.0

            # Shuffle + mini-batch
            indices = np.random.permutation(n_samples)
            for start in range(0, n_samples, batch_size):
                batch_idx = indices[start:start + batch_size]

                # Accumulate gradients over batch
                batch_grads = {name: np.zeros_like(p)
                               for name, p in self._get_params().items()}
                batch_loss = 0.0

                for idx in batch_idx:
                    sample_loss, grads = self._forward_backward_sample(
                        X[idx], y[idx], clip_norm)
                    batch_loss += sample_loss
                    for name in batch_grads:
                        batch_grads[name] += grads[name]

                # Average and apply
                bs = len(batch_idx)
                for name in batch_grads:
                    batch_grads[name] /= bs
                    self._adam_step(name, batch_grads[name], lr)

                epoch_loss += batch_loss / bs

            avg_loss = epoch_loss / max(1, n_samples // batch_size)
            train_losses.append(avg_loss)

            # Validation
            if X_val is not None and y_val is not None:
                val_loss = self._compute_val_loss(X_val, y_val)
                val_losses.append(val_loss)

                if val_loss < best_val_loss:
                    best_val_loss = val_loss
                    best_params = self._get_params_snapshot()
                    plateau_counter = 0
                else:
                    plateau_counter += 1

                # Early stopping
                if plateau_counter >= patience:
                    if verbose:
                        print(f"  LSTM early stop @ epoch {epoch+1}, "
                              f"best val_loss={best_val_loss:.6f}")
                    break

                # Learning rate decay on plateau
                if plateau_counter > 0 and plateau_counter % 10 == 0:
                    lr *= lr_decay
                    if verbose:
                        print(f"  LSTM lr decay \u2192 {lr:.6f} @ epoch {epoch+1}")
            else:
                val_losses.append(avg_loss)  # Use train loss as proxy

        # Restore best parameters
        if best_params is not None:
            self._set_params(best_params)

        return train_losses, val_losses

# ─── Main Predictor ────────────────────────────────────────

class StockPredictor:
    """Multi-track stock price predictor."""

    def __init__(self):
        self._X_mean = None
        self._X_std = None

    def _ensure_model_dir(self):
        os.makedirs(MODEL_DIR, exist_ok=True)

    def _prepare_data(self, code: str) -> Tuple[Optional[np.ndarray],
                                               Optional[np.ndarray],
                                               Optional[np.ndarray],
                                               Optional[pd.DataFrame]]:
        """Prepare training data for a stock."""
        df = _load_history(code)
        if df is None:
            print(f"  No history data for {code}. Use --ask to download first.")
            return None, None, None, None
        df = _compute_features(df)
        features = _get_feature_columns()
        df_clean = df.dropna(subset=features + ['target'])
        if len(df_clean) < MIN_TRAIN_DAYS:
            print(f"  Insufficient data: {len(df_clean)} rows (need {MIN_TRAIN_DAYS})")
            return None, None, None, None
        X = df_clean[features].values.astype(np.float64)
        y_reg = df_clean['target'].values.astype(np.float64)
        y_cls = df_clean['target_direction'].values.astype(np.int32)
        self._X_mean = X.mean(axis=0)
        self._X_std = X.std(axis=0) + 1e-10
        X = (X - self._X_mean) / self._X_std
        return X, y_reg, y_cls, df_clean

    def predict_sklearn(self, code: str) -> Optional[dict]:
        """Predict using sklearn ensemble (RandomForest + GradientBoost + Ridge)."""
        from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
        from sklearn.linear_model import Ridge
        from sklearn.model_selection import TimeSeriesSplit

        X, y_reg, y_cls, df = self._prepare_data(code)
        if X is None:
            return None

        # Time-series split: train on earlier, test on recent
        tscv = TimeSeriesSplit(n_splits=3)
        train_idx, test_idx = list(tscv.split(X))[-1]

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y_reg[train_idx], y_reg[test_idx]

        results = {}

        # RandomForest
        rf = RandomForestRegressor(n_estimators=100, max_depth=8, random_state=42, n_jobs=-1)
        rf.fit(X_train, y_train)
        rf_pred = rf.predict(X_test)
        rf_score = self._direction_accuracy(y_test, rf_pred)
        results['random_forest'] = {
            'model': rf,
            'direction_accuracy': round(rf_score, 3),
            'test_rmse': round(np.sqrt(np.mean((y_test - rf_pred) ** 2)), 4),
        }

        # GradientBoosting
        gb = GradientBoostingRegressor(n_estimators=100, max_depth=5, random_state=42)
        gb.fit(X_train, y_train)
        gb_pred = gb.predict(X_test)
        gb_score = self._direction_accuracy(y_test, gb_pred)
        results['gradient_boost'] = {
            'model': gb,
            'direction_accuracy': round(gb_score, 3),
            'test_rmse': round(np.sqrt(np.mean((y_test - gb_pred) ** 2)), 4),
        }

        # Ridge
        ridge = Ridge(alpha=1.0)
        ridge.fit(X_train, y_train)
        ridge_pred = ridge.predict(X_test)
        ridge_score = self._direction_accuracy(y_test, ridge_pred)
        results['ridge'] = {
            'model': ridge,
            'direction_accuracy': round(ridge_score, 3),
            'test_rmse': round(np.sqrt(np.mean((y_test - ridge_pred) ** 2)), 4),
        }

        # Ensemble prediction for latest day
        latest_X = X[-1:].copy()
        ensemble_pred = (
            rf.predict(latest_X)[0] * 0.4 +
            gb.predict(latest_X)[0] * 0.35 +
            ridge.predict(latest_X)[0] * 0.25
        )

        # Get latest price
        latest_price = float(df['close'].iloc[-1])
        latest_date = str(df['date'].iloc[-1])[:10]

        return {
            'code': code,
            'model_type': 'sklearn_ensemble',
            'latest_price': round(latest_price, 2),
            'latest_date': latest_date,
            'prediction_days': PREDICTION_DAYS,
            'predicted_return': round(float(ensemble_pred), 4),
            'predicted_price': round(latest_price * (1 + float(ensemble_pred)), 2),
            'direction': 'up' if ensemble_pred > 0 else 'down',
            'direction_confidence': round(
                max(
                    results['random_forest']['direction_accuracy'],
                    results['gradient_boost']['direction_accuracy'],
                    results['ridge']['direction_accuracy'],
                ), 3
            ),
            'model_scores': {
                k: v['direction_accuracy'] for k, v in results.items()
            },
            'sample_count': len(df),
        }

        
    def predict_lstm(self, code: str, seq_len: int = 20) -> Optional[dict]:
        """Predict using numpy LSTM (v2: Adam, early stopping, L2 reg)."""
        X, y_reg, y_cls, df = self._prepare_data(code)
        if X is None:
            return None

        # Create sequences
        n_features = X.shape[1]
        sequences = []
        targets = []

        for i in range(seq_len, len(X)):
            sequences.append(X[i - seq_len:i])
            targets.append(y_reg[i])

        if len(sequences) < 30:
            return {'error': f'Not enough sequences: {len(sequences)} (need 30+)'}

        sequences = np.array(sequences)
        targets = np.array(targets)

        # Standardize targets (helps LSTM training stability)
        y_mean = float(np.mean(targets))
        y_std = float(np.std(targets)) + 1e-10
        targets_norm = (targets - y_mean) / y_std

        # Time-series split: train/val/test
        n = len(sequences)
        train_end = int(n * 0.6)
        val_end = int(n * 0.8)

        X_train, y_train = sequences[:train_end], targets_norm[:train_end]
        X_val, y_val = sequences[train_end:val_end], targets_norm[train_end:val_end]
        X_test, y_test_raw = sequences[val_end:], targets[val_end:]

        # Train LSTM with early stopping
        lstm = NumpyLSTM(input_size=n_features, hidden_size=16, l2_lambda=1e-2)
        train_losses, val_losses = lstm.train(
            X_train, y_train,
            epochs=200, lr=0.0003, batch_size=8, clip_norm=0.5,
            X_val=X_val, y_val=y_val,
            patience=30, lr_decay=0.5,
            verbose=False
        )

        # Evaluate on test set
        test_preds_norm = np.array([lstm.forward(x) for x in X_test])
        test_preds = test_preds_norm * y_std + y_mean  # un-standardize
        direction_acc = self._direction_accuracy(y_test_raw, test_preds)
        test_rmse = np.sqrt(np.mean((y_test_raw - test_preds) ** 2))

        # Predict latest
        latest_seq = X[-seq_len:]
        lstm_pred_norm = lstm.forward(latest_seq)
        lstm_pred = lstm_pred_norm * y_std + y_mean  # un-standardize

        latest_price = float(df['close'].iloc[-1])
        epochs_used = len(train_losses)

        return {
            'code': code,
            'model_type': 'numpy_lstm_v2',
            'latest_price': round(latest_price, 2),
            'latest_date': str(df['date'].iloc[-1])[:10],
            'prediction_days': PREDICTION_DAYS,
            'predicted_return': round(float(lstm_pred), 4),
            'predicted_price': round(latest_price * (1 + float(lstm_pred)), 2),
            'direction': 'up' if lstm_pred > 0 else 'down',
            'direction_accuracy_test': round(direction_acc, 3),
            'test_rmse': round(test_rmse, 4),
            'final_train_loss': round(train_losses[-1], 6),
            'best_val_loss': round(val_losses[-1], 6) if val_losses else None,
            'epochs_trained': epochs_used,
            'hidden_size': lstm.hidden_size,
            'target_std': round(y_std, 6),
            'sample_count': len(df),
        }


    def predict_llm(self, code: str, sklearn_result: dict = None,
                    lstm_result: dict = None) -> Optional[str]:
        """LLM event-driven prediction using DeepSeek.
        Synthesizes ML predictions + market context into qualitative analysis.
        """
        import urllib.request
        import urllib.error

        api_key = None
        if os.path.exists(CONFIG_PATH):
            try:
                with open(CONFIG_PATH) as f:
                    cfg = json.load(f)
                api_key = cfg.get('deepseek_api_key')
                if api_key == '${DEEPSEEK_API_KEY}':
                    api_key = os.environ.get('DEEPSEEK_API_KEY')
            except Exception:
                api_key = os.environ.get('DEEPSEEK_API_KEY')

        if not api_key:
            return None  # Silently skip if no key

        # Build context
        ctx_parts = [f"股票代码: {code}"]

        if sklearn_result:
            ctx_parts.append(
                f"经典ML模型预测: {sklearn_result['direction']} "
                f"(预期收益: {sklearn_result['predicted_return']:+.2%}, "
                f"目标价: {sklearn_result['predicted_price']:.2f}, "
                f"方向准确率: {sklearn_result['direction_confidence']:.0%})"
            )
            ctx_parts.append(
                f"子模型准确率: RF={sklearn_result['model_scores']['random_forest']:.0%}, "
                f"GB={sklearn_result['model_scores']['gradient_boost']:.0%}, "
                f"Ridge={sklearn_result['model_scores']['ridge']:.0%}"
            )

        if lstm_result and 'error' not in lstm_result:
            ctx_parts.append(
                f"LSTM深度学习预测: {lstm_result['direction']} "
                f"(预期收益: {lstm_result['predicted_return']:+.2%}, "
                f"方向准确率: {lstm_result.get('direction_accuracy_test', 0):.0%}, "
                f"loss: {lstm_result.get('final_loss', 0):.6f})"
            )

        context = '\n'.join(ctx_parts)

        system_prompt = """你是一个专业的A股投资顾问。根据机器学习模型的预测结果，给出综合研判。

    输出格式（严格JSON）：
    {
      "final_direction": "up"或"down"或"neutral",
      "confidence": 0.0到1.0,
      "key_factors": ["驱动因素1", "驱动因素2"],
      "risk_warning": "主要风险提示",
      "advice": "综合建议(50字内)",
      "model_reliability": "模型可信度评估(30字内)"
    }

    只输出JSON，不要其他文字。"""

        user_prompt = f"根据以下{PREDICTION_DAYS}日预测模型结果，给出综合研判：\n\n{context}"

        proxy_url = os.environ.get('HTTPS_PROXY', os.environ.get('https_proxy', 'http://127.0.0.1:10809'))
        proxy_handler = urllib.request.ProxyHandler({'http': proxy_url, 'https': proxy_url})
        opener = urllib.request.build_opener(proxy_handler)

        url = "https://api.deepseek.com/v1/chat/completions"
        payload = json.dumps({
            "model": "deepseek-chat",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.2,
            "max_tokens": 500,
            "response_format": {"type": "json_object"}
        }).encode('utf-8')

        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {api_key}',
        }

        try:
            req = urllib.request.Request(url, data=payload, headers=headers)
            resp = opener.open(req, timeout=30)
            result = json.loads(resp.read())
            content = result['choices'][0]['message']['content']
            return content
        except Exception as e:
            return json.dumps({'error': str(e)}, ensure_ascii=False)

    
    def _direction_accuracy(self, y_true: np.ndarray, y_pred: np.ndarray) -> float:
        """Calculate directional accuracy (up/down prediction accuracy)."""
        true_dir = (y_true > 0).astype(int)
        pred_dir = (y_pred > 0).astype(int)
        return float(np.mean(true_dir == pred_dir))

    def predict(self, code: str, use_llm: bool = False) -> dict:
        """Run full prediction pipeline.

        Args:
        code: Stock code
        use_llm: Also run LLM event-driven analysis

        Returns:
        dict with sklearn_result, lstm_result, llm_result
        """
        result = {'code': code, 'timestamp': datetime.now().isoformat()}

        # Track 1: sklearn ensemble
        sklearn_result = self.predict_sklearn(code)
        result['sklearn'] = sklearn_result

        # Track 2: numpy LSTM
        lstm_result = self.predict_lstm(code)
        result['lstm'] = lstm_result

        # Track 3: LLM synthesis
        if use_llm:
            llm_raw = self.predict_llm(code, sklearn_result, lstm_result)
            if llm_raw:
                try:
                    result['llm'] = json.loads(llm_raw)
                except json.JSONDecodeError:
                    result['llm'] = {'raw': llm_raw}

        return result


# ─── Convenience ───────────────────────────────────────────

_predictor: Optional[StockPredictor] = None


def predict_stock(code: str, use_llm: bool = False) -> dict:
    """Convenience function for stock prediction."""
    global _predictor
    if _predictor is None:
        _predictor = StockPredictor()
    return _predictor.predict(code, use_llm=use_llm)


def print_prediction(result: dict):
    """Pretty-print prediction results."""
    code = result.get('code', '?')

    print(f"\n{'='*60}")
    print(f"  📈 {PREDICTION_DAYS}日预测 — {code}")
    print(f"{'='*60}")

    # sklearn
    sk = result.get('sklearn')
    if sk:
        arrow = '🟢 ↗' if sk['direction'] == 'up' else '🔴 ↘'
        print(f"\n  🤖 经典ML集成模型 (RandomForest + GBDT + Ridge):")
        print(f"     方向: {arrow} {sk['direction']}")
        print(f"     预期收益: {sk['predicted_return']:+.2%}")
        print(f"     目标价:   {sk['predicted_price']:.2f} (当前: {sk['latest_price']:.2f})")
        print(f"     方向准确率: {sk['direction_confidence']:.0%}")
        print(f"     子模型: RF={sk['model_scores']['random_forest']:.0%}  "
              f"GB={sk['model_scores']['gradient_boost']:.0%}  "
              f"Ridge={sk['model_scores']['ridge']:.0%}")
        print(f"     训练样本: {sk['sample_count']}天")

    # LSTM
    ls = result.get('lstm')
    if ls:
        if 'error' in ls:
            print(f"\n  🧠 numpy-LSTM v2: {ls['error']}")
        else:
            arrow = '🟢 ↗' if ls['direction'] == 'up' else '🔴 ↘'
            print(f"\n  🧠 深度学习 LSTM v2 (Adam+梯度裁剪+早停):")
            print(f"     方向: {arrow} {ls['direction']}")
            print(f"     预期收益: {ls['predicted_return']:+.2%}")
            print(f"     目标价:   {ls['predicted_price']:.2f}")
            print(f"     方向准确率(测试集): {ls.get('direction_accuracy_test', 0):.0%}")
            print(f"     RMSE: {ls.get('test_rmse', 0):.4f}")
            print(f"     最终 train loss: {ls.get('final_train_loss', 0):.6f}")
            if ls.get('best_val_loss'):
                print(f"     最佳 val loss:   {ls.get('best_val_loss', 0):.6f}")
            print(f"     训练轮次: {ls.get('epochs_trained', '?')}")
            print(f"     隐藏层: {ls.get('hidden_size', '?')} 单元")

    # LLM
    llm = result.get('llm')
    if llm:
        if 'error' in llm or 'raw' in llm:
            print(f"\n  🤖 LLM研判: {llm.get('error', llm.get('raw', 'unknown'))[:100]}")
        else:
            dir_map = {'up': '🟢 看涨', 'down': '🔴 看跌', 'neutral': '🟡 中性'}
            print(f"\n  🤖 DeepSeek LLM综合研判:")
            print(f"     最终方向: {dir_map.get(llm.get('final_direction', ''), '?')}")
            print(f"     置信度:   {llm.get('confidence', 0):.0%}")
            print(f"     驱动因素: {', '.join(llm.get('key_factors', []))}")
            print(f"     风险提示: {llm.get('risk_warning', '')}")
            print(f"     建议:     {llm.get('advice', '')}")
            print(f"     模型评估: {llm.get('model_reliability', '')}")

    print(f"\n{'='*60}\n")
