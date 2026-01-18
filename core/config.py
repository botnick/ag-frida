import yaml
import os
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger("ag-frida.core.config")

class ConfigManager:
    """
    Manages 'ag-frida.yaml' for Usage Profiles.
    """
    
    CONFIG_NAME = "ag-frida.yaml"
    
    def __init__(self):
        # Look in current directory (where user runs it) or script dir?
        # Current dir is better for flexibility.
        self.config_path = os.path.join(os.getcwd(), self.CONFIG_NAME)
        # Fallback to module dir if not in cwd
        if not os.path.exists(self.config_path):
             bg = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), self.CONFIG_NAME)
             if os.path.exists(bg):
                 self.config_path = bg

    def load_full_config(self) -> Dict[str, Any]:
        """Loads the entire config file, not just profiles."""
        if not os.path.exists(self.config_path):
            return {}
        try:
            with open(self.config_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Failed to load config: {e}")
            return {}

    def save_config(self, data: Dict[str, Any]):
        try:
            # Merge with existing
            existing = self.load_full_config()
            existing.update(data)
            with open(self.config_path, 'w', encoding='utf-8') as f:
                yaml.dump(existing, f, default_flow_style=False)
        except Exception as e:
            logger.error(f"Failed to save config: {e}")

    def load_profiles(self) -> Dict[str, Any]:
        data = self.load_full_config()
        return data.get('profiles', {})

    def get_ai_config(self) -> Dict[str, Any]:
        """Returns the AI configuration section."""
        full_config = self.load_full_config()
        # Default structure if missing
        return full_config.get('ai_config', {
            "active_provider": "openai",
            "providers": {}
        })

    def save_ai_config(self, active_provider: str, provider_config: Dict[str, Any]):
        """
        Updates AI config for a specific provider and sets it as active.
        Persists strictly to disk.
        """
        try:
            full = self.load_full_config()
            ai = full.get('ai_config', {
                "active_provider": "openai",
                "providers": {}
            })
            
            # 1. Update Active
            if active_provider:
                ai['active_provider'] = active_provider
                
            # 2. Update Provider Config (Deep Merge safe)
            if active_provider and provider_config:
                if 'providers' not in ai: ai['providers'] = {}
                # Ensure we don't wipe existing keys if not provided (partial update)
                # But usually frontend sends full config for that provider.
                # Let's simple merge:
                current_prov = ai['providers'].get(active_provider, {})
                current_prov.update(provider_config)
                ai['providers'][active_provider] = current_prov

            full['ai_config'] = ai
            self.save_config(full)
            logger.info(f"Saved AI Config for {active_provider}")
        except Exception as e:
            logger.error(f"Failed to save AI config: {e}")
