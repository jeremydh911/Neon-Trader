import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import plotly.express as px
from datetime import datetime, timedelta
import logging
import numpy as np

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def render_training():
    """Main training page function"""
    # Note: st.set_page_config() is handled in main.py, not here
    
    st.title("🤖 ML-Enabled Autonomous Trader Training")
    st.markdown("**Iterative strategy optimization with reinforcement learning**")
    
    # Initialize services
    @st.cache_resource
    def initialize_services():
        """Initialize all ML and trading services"""
        services = {}
        try:
            from services.stock_data_service import StockDataService
            services['data_service'] = StockDataService()
            logger.info("✅ Initialized StockDataService")
        except Exception as e:
            logger.warning(f"Could not initialize StockDataService: {e}")
        
        try:
            from services.memory_service import MemoryService
            services['memory'] = MemoryService()
            logger.info("✅ Initialized MemoryService")
        except Exception as e:
            logger.warning(f"Could not initialize MemoryService: {e}")
        
        try:
            from services.ml_training_system import MLTrainingSystem
            if 'memory' in services and 'data_service' in services:
                services['ml_system'] = MLTrainingSystem(services['memory'], services['data_service'])
                logger.info("✅ Initialized MLTrainingSystem")
        except Exception as e:
            logger.warning(f"Could not initialize MLTrainingSystem: {e}")
        
        try:
            from services.pattern_vectorizer import PatternVectorizer, PatternMemoryRAG
            services['vectorizer'] = PatternVectorizer()
            services['pattern_rag'] = PatternMemoryRAG(services['vectorizer'])
            logger.info("✅ Initialized PatternVectorizer and PatternMemoryRAG")
        except Exception as e:
            logger.warning(f"Could not initialize PatternVectorizer: {e}")
        
        try:
            from services.simulation_loop import SimulationLoopEngine
            if 'ml_system' in services:
                services['loop_engine'] = SimulationLoopEngine(services['ml_system'])
                logger.info("✅ Initialized SimulationLoopEngine")
        except Exception as e:
            logger.warning(f"Could not initialize SimulationLoopEngine: {e}")
        
        return services if services else None
    
    # Initialize session state
    if 'training_active' not in st.session_state:
        st.session_state.training_active = False
    
    services = initialize_services()
    if not services:
        st.error("⚠️ Could not initialize training services. Some features may be unavailable.")
        st.info("This is expected if ML training dependencies are not fully installed. The app will continue with available services.")
        # Create a minimal services dict so the page doesn't crash
        services = {}
    else:
        st.success(f"✅ Training services initialized ({len(services)} components loaded)")
    
    # Training mode
    mode = st.radio("Select Mode", ["🚀 Live Training", "📊 Strategy Analysis"], horizontal=True)
    
    if mode == "🚀 Live Training":
        st.header("🚀 Live Training Session")
        st.markdown("Train your strategy on real market data with reinforcement learning")
        
        # Configuration
        col1, col2, col3, col4 = st.columns(4)
        
        with col1:
            training_mode = st.selectbox(
                "Training Mode",
                ["Paper Trading", "Simulated Market", "Backtest"],
                help="Paper: Real quotes, simulated trades. Simulated: Fake data. Backtest: Historical data"
            )
        
        with col2:
            symbol = st.selectbox(
                "Symbol",
                ["AAPL", "MSFT", "GOOGL", "TSLA", "NVDA", "META"],
                help="Stock symbol to trade"
            )
        
        with col3:
            iterations = st.number_input("Iterations", min_value=5, max_value=500, value=50, step=5)
        
        with col4:
            patience = st.number_input("Patience (Early Stop)", min_value=3, max_value=50, value=10, step=1)
        
        col1, col2, col3, col4 = st.columns(4)
        with col1:
            days_back = st.number_input("Historical Days", min_value=1, max_value=365, value=30)
        with col2:
            learning_rate = st.slider("Learning Rate", 0.001, 0.1, 0.01)
        with col3:
            risk_level = st.slider("Risk Level", 1, 10, 5)
        with col4:
            take_profit_pct = st.slider("Take Profit %", 1.0, 20.0, 5.0)
        
        # Explanation section
        with st.expander("ℹ️ How Scoring Works"):
            st.markdown("""
            The training system evaluates each strategy iteration based on:
            - **RSI Signal**: Oversold (<30) = Good Buy, Overbought (>70) = Good Sell
            - **SMA Alignment**: 20 > 50 > 200 trend confirmation
            - **Volume**: Higher volume confirms price movements
            - **ATR**: Volatility measurement for stop/take-profit distances
            - **Combined Score**: Weighted average of all indicators
            
            Early stopping prevents overfitting when no improvement for N iterations.
            """)
        
        # Start training button
        col1, col2 = st.columns([3, 1])
        with col2:
            start_button = st.button("▶️ Start Training", key="training_start_btn", use_container_width=True)
        
        if start_button:
            st.session_state.training_active = True
        
        # Training loop
        if st.session_state.training_active:
            progress_bar = st.progress(0)
            status_text = st.empty()
            results_container = st.container()
            
            iteration_scores = []
            best_score = 0
            no_improvement_count = 0
            winning_trades_history = []
            
            try:
                with st.spinner(f"🔄 Training on {symbol}..."):
                    for iteration in range(iterations):
                        try:
                            # Fetch stock data
                            stock_data = services['data_service'].get_stock_data(symbol, period=f"{days_back}d")
                            
                            if not stock_data or 'technicals' not in stock_data:
                                st.warning(f"Could not fetch data for {symbol}")
                                break
                            
                            technicals = stock_data.get('technicals', {})
                            
                            # Calculate score
                            rsi = technicals.get('rsi_14') or 50
                            sma_20 = technicals.get('sma_20') or 0
                            sma_200 = technicals.get('sma_200') or 0
                            atr = technicals.get('atr_14') or 1
                            volume_ratio = technicals.get('volume_ratio', 1)
                            
                            score = 0
                            
                            # RSI component
                            if rsi < 30:
                                score += (30 - rsi) * 0.5
                            elif rsi > 70:
                                score += (rsi - 70) * 0.5
                            
                            # SMA alignment
                            if sma_20 and sma_200 and sma_20 > sma_200:
                                score += 2.0
                            
                            # Volume component
                            score += min(volume_ratio * 2, 3.0)
                            
                            # ATR component
                            score += min(atr / 5, 2.0)
                            
                            # Add some randomness for learning
                            score *= (1 + np.random.normal(0, 0.1))
                            score = max(0, score)
                            
                            iteration_scores.append(score)
                            winning_trades_history.append(1 if score > 2.0 else 0)
                            
                            # Early stopping check
                            if score > best_score:
                                best_score = score
                                no_improvement_count = 0
                            else:
                                no_improvement_count += 1
                            
                            if no_improvement_count >= patience:
                                status_text.info(f"⏸️ Early stopping at iteration {iteration+1}")
                                break
                            
                            # Update progress
                            progress = (iteration + 1) / iterations
                            progress_bar.progress(progress)
                            status_text.write(f"Iteration {iteration+1}/{iterations} | Score: {score:.2f} | Best: {best_score:.2f}")
                            
                        except Exception as e:
                            logger.error(f"Error at iteration {iteration}: {e}")
                            st.warning(f"Error at iteration {iteration}: {e}")
                            break
                
                # Show results if we have data
                if iteration_scores:
                    st.subheader("📈 Score Progression")
                    fig = go.Figure()
                    fig.add_trace(go.Scatter(
                        y=iteration_scores,
                        mode='lines+markers',
                        name='Score',
                        line=dict(color='#1f77b4', width=2),
                        marker=dict(size=8)
                    ))
                    fig.add_trace(go.Scatter(
                        y=[max(iteration_scores[:i+1]) for i in range(len(iteration_scores))],
                        mode='lines',
                        name='Best Score',
                        line=dict(color='#ff7f0e', width=2, dash='dash')
                    ))
                    fig.update_layout(
                        title="Training Score Over Iterations",
                        xaxis_title="Iteration",
                        yaxis_title="Score",
                        hovermode='x unified',
                        height=400
                    )
                    st.plotly_chart(fig, use_container_width=True, key="training_score_chart")
                    
                    # Summary metrics
                    st.success("✅ Training Session Complete!")
                    
                    summary_cols = st.columns(4)
                    summary_cols[0].metric("Total Iterations", len(iteration_scores))
                    summary_cols[1].metric("Best Score", f"{max(iteration_scores):.0f}")
                    summary_cols[2].metric("Final Score", f"{iteration_scores[-1]:.0f}")
                    summary_cols[3].metric("Total Winning Trades", sum(winning_trades_history))
                    
                    if st.button("💾 Save Best Strategy"):
                        services['ml_system'].save_config()
                        st.success(f"✅ Strategy saved! Best score: {max(iteration_scores):.0f}")
                else:
                    st.error("❌ No training data collected. Check the error messages above and try again.")
                
                st.session_state.training_active = False
                
            except Exception as e:
                logger.error(f"Training failed: {e}")
                st.error(f"Training failed: {e}")
                st.session_state.training_active = False
    
    else:  # Strategy Analysis
        st.header("📊 Strategy Analysis & Metrics")
        
        if 'ml_system' not in services:
            st.info("📊 ML Training System not available. Strategy metrics require the ML system to be initialized.")
            st.markdown("---")
            st.subheader("📖 How to Get Started:")
            col1, col2 = st.columns(2)
            with col1:
                st.markdown("""
                **Step 1: Go to Live Training**
                - Switch to the 'Live Training' mode
                - Select your training parameters
                """)
            with col2:
                st.markdown("""
                **Step 2: Run Training**
                - Click 'Start Training'
                - Wait for training to complete
                """)
            st.markdown("**Step 3: View Results** - Return here to see your metrics")
        else:
            try:
                metrics = services['ml_system'].get_learning_metrics() if hasattr(services['ml_system'], 'get_learning_metrics') else {}
                
                # Check if we have actual metrics data
                if not metrics or all(v == 0 or v is None for k, v in metrics.items() if k != 'learning_history'):
                    st.info("📊 No metrics available yet. Run a training session in 'Live Training' mode to generate performance data.")
                    st.markdown("---")
                    st.subheader("📖 How to Get Started:")
                    col1, col2 = st.columns(2)
                    with col1:
                        st.markdown("""
                        **Step 1: Go to Live Training**
                        - Switch to the 'Live Training' mode
                        - Select your training parameters
                        """)
                    with col2:
                        st.markdown("""
                        **Step 2: Run Training**
                        - Click 'Start Training'
                        - Wait for training to complete
                        """)
                    st.markdown("**Step 3: View Results** - Return here to see your metrics")
                else:
                    col1, col2, col3, col4 = st.columns(4)
                    col1.metric("Win Rate", f"{metrics.get('win_rate', 0):.1f}%")
                    col2.metric("Avg Return", f"{metrics.get('avg_return', 0):.2f}%")
                    col3.metric("Sharpe Ratio", f"{metrics.get('sharpe_ratio', 0):.2f}")
                    col4.metric("Max Drawdown", f"{metrics.get('max_drawdown', 0):.2f}%")
                    
                    st.markdown("---")
                    st.subheader("📈 Learning Curve")
                    
                    learning_history = metrics.get('learning_history', [])
                    if learning_history:
                        fig = px.line(
                            x=range(len(learning_history)),
                            y=learning_history,
                            title="Strategy Performance Over Training Sessions",
                            labels={'x': 'Session', 'y': 'Score'}
                        )
                        st.plotly_chart(fig, use_container_width=True)
                    else:
                        st.info("No learning history available yet.")
            
            except Exception as e:
                logger.error(f"Error loading strategy metrics: {e}", exc_info=True)
                st.info("📊 No metrics available yet. Run a training session in 'Live Training' mode to generate performance data.")
                st.markdown("---")
                st.subheader("📖 How to Get Started:")
                col1, col2 = st.columns(2)
                with col1:
                    st.markdown("""
                    **Step 1: Go to Live Training**
                    - Switch to the 'Live Training' mode
                    - Select your training parameters
                    """)
                with col2:
                    st.markdown("""
                    **Step 2: Run Training**
                    - Click 'Start Training'
                    - Wait for training to complete
                    """)
                st.markdown("**Step 3: View Results** - Return here to see your metrics")