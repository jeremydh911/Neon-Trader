"""
Audio Alert Service
Generates bell and notification sounds for trading events
"""

import logging
import os
import tempfile
from pathlib import Path
from typing import Optional
import base64

logger = logging.getLogger(__name__)

class AudioAlerts:
    """Generate and manage trading alert sounds"""
    
    def __init__(self, audio_dir: str = "/app/data/audio"):
        self.audio_dir = Path(audio_dir)
        self.audio_dir.mkdir(parents=True, exist_ok=True)
        
        # Try to import audio libraries
        self.waveform_available = False
        try:
            import wave
            self.wave = wave
            self.waveform_available = True
            logger.info("Wave audio generation available")
        except ImportError:
            logger.warning("Wave module not available")
        
        self.numpy_available = False
        try:
            import numpy as np
            self.np = np
            self.numpy_available = True
        except ImportError:
            logger.warning("NumPy not available for audio generation")
        
        self._generate_bell_sound()
    
    def _generate_bell_sound(self):
        """Generate bell sound (bell.wav) in app/data/audio"""
        try:
            if not self.waveform_available or not self.numpy_available:
                logger.warning("Cannot generate bell sound - dependencies missing")
                return
            
            bell_file = self.audio_dir / "bell.wav"
            
            # Bell sound parameters
            sample_rate = 44100  # Hz
            duration = 0.3  # seconds
            frequency = 800  # Hz (bell-like tone)
            overtone1 = 1200  # Hz
            overtone2 = 600   # Hz
            
            # Generate samples
            t = self.np.linspace(0, duration, int(sample_rate * duration), False)
            
            # Primary tone with decay envelope
            decay = self.np.exp(-5 * t)
            primary = self.np.sin(2 * self.np.pi * frequency * t) * decay
            
            # Add overtones for bell character
            overtone1_wave = self.np.sin(2 * self.np.pi * overtone1 * t) * decay * 0.3
            overtone2_wave = self.np.sin(2 * self.np.pi * overtone2 * t) * decay * 0.2
            
            # Mix tones
            wave_data = primary + overtone1_wave + overtone2_wave
            
            # Normalize
            wave_data = wave_data / self.np.max(self.np.abs(wave_data)) * 0.8
            
            # Convert to 16-bit audio
            wave_data = (wave_data * 32767).astype(self.np.int16)
            
            # Write WAV file
            with self.wave.open(str(bell_file), 'wb') as wav_file:
                wav_file.setnchannels(1)  # Mono
                wav_file.setsampwidth(2)  # 16-bit
                wav_file.setframerate(sample_rate)
                wav_file.writeframes(wave_data.tobytes())
            
            logger.info(f"Bell sound generated: {bell_file}")
        except Exception as e:
            logger.error(f"Error generating bell sound: {e}")
    
    def get_bell_audio_base64(self) -> Optional[str]:
        """Get bell sound as base64 encoded string for HTML playback"""
        try:
            bell_file = self.audio_dir / "bell.wav"
            if not bell_file.exists():
                # Create fallback simple bell
                self._generate_bell_sound()
            
            if bell_file.exists():
                with open(bell_file, 'rb') as f:
                    audio_bytes = f.read()
                audio_base64 = base64.b64encode(audio_bytes).decode()
                return f"data:audio/wav;base64,{audio_base64}"
        except Exception as e:
            logger.error(f"Error encoding bell audio: {e}")
        return None
    
    def create_html_audio_player(self, audio_type: str = "bell") -> str:
        """Create HTML5 audio player element"""
        audio_base64 = self.get_bell_audio_base64()
        
        if not audio_base64:
            return ""
        
        html = f"""
        <audio id="alert-audio-{audio_type}" preload="auto">
            <source src="{audio_base64}" type="audio/wav">
            Your browser does not support the audio element.
        </audio>
        <script>
            function playAlertSound() {{
                var audio = document.getElementById('alert-audio-{audio_type}');
                audio.currentTime = 0;
                audio.play();
            }}
        </script>
        """
        return html
    
    def get_streamlit_audio_html(self) -> str:
        """Get HTML/JavaScript for Streamlit audio playback"""
        audio_base64 = self.get_bell_audio_base64()
        
        if not audio_base64:
            return ""
        
        return f"""
        <script>
            function playTradingBell() {{
                const audio = new Audio('{audio_base64}');
                audio.play().catch(e => console.log('Audio play failed:', e));
            }}
            window.playTradingBell = playTradingBell;
        </script>
        """
    
    def get_alert_sound_data(self) -> Optional[bytes]:
        """Get raw bell sound data"""
        try:
            bell_file = self.audio_dir / "bell.wav"
            if bell_file.exists():
                with open(bell_file, 'rb') as f:
                    return f.read()
        except Exception as e:
            logger.debug(f"Error reading bell audio: {e}")
        return None


class TradeEventNotifier:
    """Manage trade notifications and alerts"""
    
    def __init__(self, audio_alerts: Optional[AudioAlerts] = None):
        self.audio_alerts = audio_alerts or AudioAlerts()
        self.event_queue = []
        self.max_events = 50
    
    def add_trade_event(
        self,
        action: str,
        symbol: str,
        price: float,
        quantity: int = 0,
        confidence: float = 0.0,
        predicted_price: Optional[float] = None
    ) -> None:
        """Add a trade event to notification queue"""
        
        from datetime import datetime
        
        event = {
            "timestamp": datetime.utcnow().isoformat(),
            "action": action,
            "symbol": symbol,
            "price": price,
            "quantity": quantity,
            "confidence": confidence,
            "predicted_price": predicted_price,
            "should_alert": action in ["BUY", "SELL"]
        }
        
        self.event_queue.insert(0, event)
        
        # Keep queue size limited
        if len(self.event_queue) > self.max_events:
            self.event_queue = self.event_queue[:self.max_events]
        
        logger.info(f"Trade event: {action} {symbol} @ {price}")
    
    def get_recent_events(self, limit: int = 10) -> list:
        """Get recent trade events"""
        return self.event_queue[:limit]
    
    def get_events_by_symbol(self, symbol: str, limit: int = 5) -> list:
        """Get recent events for a specific symbol"""
        return [e for e in self.event_queue if e['symbol'] == symbol][:limit]
    
    def create_ticker_html(self, limit: int = 10) -> str:
        """Create HTML ticker display of recent trades"""
        
        recent_events = self.get_recent_events(limit)
        
        if not recent_events:
            return "<div style='text-align:center; color:#999;'>No trades yet</div>"
        
        ticker_html = """
        <div style='background: #1a1a1a; color: #00ff00; font-family: monospace; padding: 10px; border-radius: 5px; overflow-y: auto; max-height: 300px;'>
            <style>
                .ticker-row { display: flex; justify-content: space-between; padding: 5px 0; border-bottom: 1px solid #333; }
                .ticker-time { color: #666; font-size: 0.9em; }
                .ticker-buy { color: #00ff00; }
                .ticker-sell { color: #ff0066; }
                .ticker-hold { color: #ffaa00; }
                .ticker-symbol { font-weight: bold; }
                .ticker-price { text-align: right; }
            </style>
        """
        
        for event in recent_events:
            action = event['action']
            symbol = event['symbol']
            price = event['price']
            confidence = event['confidence']
            timestamp = event['timestamp'].split('T')[1][:8]  # HH:MM:SS
            
            # Color code by action
            action_class = f"ticker-{action.lower()}"
            
            ticker_html += f"""
            <div class='ticker-row'>
                <span class='ticker-time'>{timestamp}</span>
                <span class='ticker-symbol'>{symbol}</span>
                <span class='{action_class}'>{action}</span>
                <span class='ticker-price'>${price:.2f}</span>
                <span style='color:#888;'>{confidence:.0%}</span>
            </div>
            """
        
        ticker_html += "</div>"
        return ticker_html
    
    def create_ticker_table_data(self, limit: int = 10) -> list:
        """Create ticker data suitable for Streamlit table display"""
        
        recent_events = self.get_recent_events(limit)
        table_data = []
        
        for event in recent_events:
            table_data.append({
                "Time": event['timestamp'].split('T')[1][:8],
                "Symbol": event['symbol'],
                "Action": event['action'],
                "Price": f"${event['price']:.2f}",
                "Confidence": f"{event['confidence']:.0%}",
                "Quantity": event['quantity'],
                "Predicted": f"${event['predicted_price']:.2f}" if event['predicted_price'] else "N/A"
            })
        
        return table_data
