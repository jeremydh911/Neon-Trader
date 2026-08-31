"""
Chart Visualization Service
Creates interactive charts for price predictions, sentiment, and trading signals
"""

import logging
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Any
import json

logger = logging.getLogger(__name__)

class ChartVisualizer:
    """Create charts and visualizations for trading data"""
    
    def __init__(self):
        self.chart_cache = {}
        self._init_plotting_libs()
    
    def _init_plotting_libs(self):
        """Initialize plotting libraries"""
        try:
            import plotly.graph_objects as go
            import plotly.express as px
            self.go = go
            self.px = px
            self.plotly_available = True
            logger.info("Plotly available for interactive charts")
        except ImportError:
            self.plotly_available = False
            logger.warning("Plotly not available - using basic charts")
        
        try:
            import matplotlib.pyplot as plt
            self.plt = plt
            self.matplotlib_available = True
        except ImportError:
            self.matplotlib_available = False
    
    def create_price_prediction_chart(
        self,
        symbol: str,
        current_price: float,
        prediction: Dict[str, Any],
        price_history: Optional[List[float]] = None,
        take_profit: Optional[float] = None,
        stop_loss: Optional[float] = None
    ) -> Dict[str, Any]:
        """Create price chart with ML predictions and levels"""
        
        if not self.plotly_available:
            return {"error": "Plotly not available"}
        
        try:
            # Prepare data
            x_data = list(range(len(price_history))) if price_history else [0]
            y_data = price_history if price_history else [current_price]
            
            fig = self.go.Figure()
            
            # Add price history line
            fig.add_trace(self.go.Scatter(
                x=x_data,
                y=y_data,
                mode='lines',
                name='Price History',
                line=dict(color='blue', width=2)
            ))
            
            # Add current price marker
            fig.add_trace(self.go.Scatter(
                x=[len(x_data)-1],
                y=[current_price],
                mode='markers',
                name='Current Price',
                marker=dict(size=10, color='blue')
            ))
            
            # Add prediction
            if prediction.get('predicted_price'):
                pred_price = prediction['predicted_price']
                pred_direction = prediction.get('direction', 'NEUTRAL')
                pred_color = 'green' if pred_direction == 'UP' else 'red' if pred_direction == 'DOWN' else 'gray'
                
                fig.add_trace(self.go.Scatter(
                    x=[len(x_data)-1, len(x_data)],
                    y=[current_price, pred_price],
                    mode='lines+markers',
                    name=f'ML Prediction ({pred_direction})',
                    line=dict(color=pred_color, width=2, dash='dash'),
                    marker=dict(size=8)
                ))
            
            # Add take profit level
            if take_profit:
                fig.add_hline(y=take_profit, line_dash="dash", line_color="green",
                            annotation_text="Take Profit", annotation_position="right")
            
            # Add stop loss level
            if stop_loss:
                fig.add_hline(y=stop_loss, line_dash="dash", line_color="red",
                            annotation_text="Stop Loss", annotation_position="right")
            
            fig.update_layout(
                title=f"{symbol} - Price Prediction Chart",
                xaxis_title="Time",
                yaxis_title="Price",
                hovermode='x unified',
                height=500
            )
            
            return {
                "chart": fig.to_html(),
                "symbol": symbol,
                "current_price": current_price,
                "predicted_price": prediction.get('predicted_price'),
                "direction": prediction.get('direction')
            }
        except Exception as e:
            logger.error(f"Error creating price chart: {e}")
            return {"error": str(e)}
    
    def create_sentiment_gauge(
        self,
        symbol: str,
        sentiment_score: float,
        sentiment_label: str,
        components: Dict[str, float]
    ) -> Dict[str, Any]:
        """Create sentiment gauge visualization"""
        
        if not self.plotly_available:
            return {"error": "Plotly not available"}
        
        try:
            # Create gauge chart
            fig = self.go.Figure(self.go.Indicator(
                mode="gauge+number+delta",
                value=sentiment_score * 100,
                domain={'x': [0, 1], 'y': [0, 1]},
                title={'text': f"{symbol} Market Sentiment"},
                delta={'reference': 50},
                gauge={
                    'axis': {'range': [-100, 100]},
                    'bar': {'color': "darkblue"},
                    'steps': [
                        {'range': [-100, -60], 'color': "#ff4d4d"},
                        {'range': [-60, -20], 'color': "#ff9999"},
                        {'range': [-20, 20], 'color': "#cccccc"},
                        {'range': [20, 60], 'color': "#99cc99"},
                        {'range': [60, 100], 'color': "#00cc00"}
                    ],
                    'threshold': {
                        'line': {'color': "red", 'width': 4},
                        'thickness': 0.75,
                        'value': 90
                    }
                }
            ))
            
            fig.update_layout(height=400)
            
            # Create components breakdown
            components_text = "\n".join([
                f"{k}: {v:.2f}" for k, v in components.items()
            ])
            
            return {
                "chart": fig.to_html(),
                "symbol": symbol,
                "sentiment_label": sentiment_label,
                "sentiment_score": sentiment_score,
                "components": components_text
            }
        except Exception as e:
            logger.error(f"Error creating sentiment gauge: {e}")
            return {"error": str(e)}
    
    def create_indicators_chart(
        self,
        symbol: str,
        indicators: Dict[str, float],
        price_history: Optional[List[float]] = None
    ) -> Dict[str, Any]:
        """Create technical indicators visualization"""
        
        if not self.plotly_available:
            return {"error": "Plotly not available"}
        
        try:
            fig = self.go.Figure()
            
            # RSI subplot
            rsi = indicators.get('rsi', 50)
            fig.add_trace(self.go.Bar(
                y=[rsi],
                name='RSI',
                marker_color='orange',
                showlegend=True
            ))
            
            # Create HTML table for all indicators
            indicators_html = "<table style='width:100%'>"
            for key, value in indicators.items():
                if isinstance(value, (int, float)):
                    color = 'green' if value > 0 else 'red' if value < 0 else 'gray'
                    indicators_html += f"<tr><td>{key}</td><td style='color:{color}'>{value:.2f}</td></tr>"
            indicators_html += "</table>"
            
            fig.update_layout(
                title=f"{symbol} - Technical Indicators",
                height=300,
                showlegend=False
            )
            
            return {
                "chart": fig.to_html(),
                "indicators_table": indicators_html,
                "rsi": rsi,
                "macd": indicators.get('macd', 0),
                "atr": indicators.get('atr', 0)
            }
        except Exception as e:
            logger.error(f"Error creating indicators chart: {e}")
            return {"error": str(e)}
    
    def create_trade_history_chart(
        self,
        symbol: str,
        trades: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create trade history visualization"""
        
        if not self.plotly_available or not trades:
            return {"error": "Plotly not available or no trades"}
        
        try:
            # Extract trade data
            dates = [t.get('timestamp', '') for t in trades]
            profits = [t.get('profit_loss_pct', 0) for t in trades]
            colors = ['green' if p > 0 else 'red' for p in profits]
            
            fig = self.go.Figure(data=[
                self.go.Bar(
                    x=dates,
                    y=profits,
                    marker_color=colors,
                    name='Trade P&L %'
                )
            ])
            
            fig.update_layout(
                title=f"{symbol} - Trade History",
                xaxis_title="Trade Date",
                yaxis_title="Profit/Loss %",
                height=400
            )
            
            # Calculate stats
            total_trades = len(trades)
            winning_trades = sum(1 for t in trades if t.get('profit_loss_pct', 0) > 0)
            avg_profit = sum(profits) / total_trades if total_trades > 0 else 0
            
            return {
                "chart": fig.to_html(),
                "symbol": symbol,
                "total_trades": total_trades,
                "winning_trades": winning_trades,
                "win_rate": (winning_trades / total_trades * 100) if total_trades > 0 else 0,
                "avg_profit_loss_pct": avg_profit
            }
        except Exception as e:
            logger.error(f"Error creating trade history chart: {e}")
            return {"error": str(e)}
    
    def create_pattern_annotation(
        self,
        pattern: Dict[str, Any],
        confidence: float
    ) -> str:
        """Create text annotation for detected patterns"""
        
        pattern_name = pattern.get('pattern', 'UNKNOWN')
        description = pattern.get('description', '')
        
        annotation = f"""
        <div style='padding:10px; border-radius:5px; background-color:#f0f0f0;'>
            <b>Pattern Detected:</b> {pattern_name}<br>
            <b>Confidence:</b> {confidence:.1%}<br>
            <b>Description:</b> {description}
        </div>
        """
        
        return annotation
    
    def create_ml_decision_summary(
        self,
        decision: Dict[str, Any]
    ) -> str:
        """Create summary card for ML trading decision"""
        
        action = decision.get('action', 'HOLD')
        confidence = decision.get('confidence', 0)
        symbol = decision.get('symbol', 'N/A')
        reasoning = decision.get('reasoning', '')
        
        action_color = 'green' if action == 'BUY' else 'red' if action == 'SELL' else 'gray'
        
        summary = f"""
        <div style='border-left: 5px solid {action_color}; padding:15px; background:#f9f9f9; border-radius:5px;'>
            <h3>{symbol} - {action}</h3>
            <p><b>Confidence:</b> {confidence:.1%}</p>
            <p><b>ML Prediction:</b> {decision.get('ml_prediction', 'N/A')}</p>
            <p><b>Sentiment:</b> {decision.get('market_sentiment', 'neutral')}</p>
            <p><b>Pattern:</b> {decision.get('pattern_detected', 'None')}</p>
            <p><b>Reasoning:</b> {reasoning}</p>
            <p><b>Take Profit:</b> {decision.get('take_profit', 'N/A')}</p>
            <p><b>Stop Loss:</b> {decision.get('stop_loss', 'N/A')}</p>
        </div>
        """
        
        return summary


    def create_desk_chart(self, symbol, bars, overlays=None, title=None):
        """Candlestick desk chart with VWAP, OR, PM 7:00–9:20, holdings peak/valley, and invalidation."""
        if not self.plotly_available:
            return {"error": "Plotly not available"}
        overlays = overlays or {}
        rows = []
        if hasattr(bars, "to_dict") and callable(getattr(bars, "reset_index", None)):
            try:
                recs = bars.reset_index().to_dict("records")
                for rec in recs:
                    item = {str(k).lower(): v for k, v in rec.items()}
                    item["ts"] = item.get("datetime") or item.get("date") or item.get("timestamp") or item.get("index")
                    rows.append(item)
            except Exception:
                rows = []
        elif isinstance(bars, list):
            for bar in bars:
                if isinstance(bar, dict):
                    item = {str(k).lower(): v for k, v in bar.items()}
                    item.setdefault("ts", item.get("datetime") or item.get("date") or item.get("timestamp"))
                    rows.append(item)
        if not rows:
            return {"error": "no bars"}
        xs, o, h, l, c = [], [], [], [], []
        for bar in rows:
            xs.append(bar.get("ts"))
            o.append(float(bar.get("open") or bar.get("o") or 0))
            h.append(float(bar.get("high") or bar.get("h") or 0))
            l.append(float(bar.get("low") or bar.get("l") or 0))
            c.append(float(bar.get("close") or bar.get("c") or 0))
        fig = self.go.Figure()
        fig.add_trace(self.go.Candlestick(x=xs, open=o, high=h, low=l, close=c, name=symbol, increasing_line_color="#3dccc7", decreasing_line_color="#e07a5f"))
        levels = [
            ("vwap", overlays.get("vwap"), "#c9a227", "dash", "VWAP"),
            ("or_high", overlays.get("or_high"), "#7bdff2", "dot", "OR high"),
            ("or_low", overlays.get("or_low"), "#7bdff2", "dot", "OR low"),
            ("pm_high", overlays.get("pm_high"), "#9b8ec4", "dashdot", "PM 7:00–9:20 high"),
            ("pm_low", overlays.get("pm_low"), "#9b8ec4", "dashdot", "PM 7:00–9:20 low"),
            ("peak", overlays.get("peak"), "#f2cc8f", "dot", "Holdings peak"),
            ("valley", overlays.get("valley"), "#81b29a", "dot", "Holdings valley"),
            ("invalidation", overlays.get("invalidation"), "#e07a5f", "dash", "Invalidation"),
        ]
        for _key, val, color, dash, label in levels:
            if val is None or val == "":
                continue
            try:
                y = float(val)
            except (TypeError, ValueError):
                continue
            fig.add_hline(y=y, line_dash=dash, line_color=color, annotation_text=label, annotation_position="right")
        fig.update_layout(
            title=title or f"{symbol} desk",
            template="plotly_dark",
            height=460,
            paper_bgcolor="#07090f",
            plot_bgcolor="#0c1220",
            xaxis_rangeslider_visible=False,
            margin=dict(l=10, r=10, t=40, b=10),
        )
        return {"figure": fig, "symbol": symbol, "overlays": overlays}
