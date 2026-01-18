import litellm
import logging
import subprocess
from typing import Dict, Any, Optional
from core.adb_installer import ADBInstaller

logger = logging.getLogger("ag-frida.core.ai")

class AIAssistant:
    """
    AI Powerhouse for ag-frida using LiteLLM.
    Supports: OpenAI, Anthropic, Gemini, OpenRouter, etc.
    """
    
    def __init__(self, config: Dict[str, Any]):
        self.config = config
        self.model = config.get('model', 'gpt-3.5-turbo')
        self.api_key = config.get('api_key', '')
        self.api_base = config.get('api_base', '').rstrip('/')
        self.provider = config.get('provider', 'openai')
        
        # Sanitize api_base to prevent double pathing (litellm adds /chat/completions)
        if self.api_base.endswith("/chat/completions"):
            self.api_base = self.api_base.replace("/chat/completions", "")
        if self.api_base.endswith("/chat/completions/"):
            self.api_base = self.api_base.replace("/chat/completions/", "")
        self.api_base = self.api_base.rstrip('/')
        
        # Provider-specific tweaks for LiteLLM to ensure 100% compliance
        self.provider = self.provider.lower()
        
        # If model name already contains slash, assume user knows what they are doing (e.g. custom/model)
        # Otherwise, enforce prefixes based on provider documentation.
        if "/" not in self.model:
            if self.provider == 'xai':
                self.model = f"xai/{self.model}"
            elif self.provider == 'deepseek':
                self.model = f"deepseek/{self.model}"
            elif self.provider == 'anthropic':
                self.model = f"anthropic/{self.model}"
            elif self.provider == 'gemini':
                self.model = f"gemini/{self.model}"
            elif self.provider == 'openrouter':
                self.model = f"openrouter/{self.model}"
            elif self.provider == 'groq':
                self.model = f"groq/{self.model}"
            elif self.provider == 'mistral':
                self.model = f"mistral/{self.model}"
            elif self.provider == 'cohere':
                self.model = f"cohere/{self.model}"
            elif self.provider == 'ollama':
                self.model = f"ollama/{self.model}"
        
        # PPQ.ai (OpenAI Compatible)
        if self.provider == 'ppqai':
            if not self.api_base:
                self.api_base = "https://api.ppq.ai"
            # PPQ.ai needs 'openai/' prefix for litellm to treat it as OpenAI client with custom base
            if not self.model.startswith("openai/"):
                self.model = f"openai/{self.model}"
            
        # Load Advanced Roles
        self.roles = {}
        try:
            import json
            import os
            roles_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "ai_roles.json")
            if os.path.exists(roles_path):
                with open(roles_path, 'r', encoding='utf-8') as f:
                    self.roles = json.load(f)
        except Exception as e:
            logger.error(f"Failed to load AI roles: {e}")

    def test_connection(self) -> Dict[str, Any]:
        """Simple ping to check if key/model logic works."""
        if not self.api_key and self.config.get('provider') != 'ollama':
            return {"success": False, "error": "API Key is missing"}
            
        try:
            kwargs = {}
            if self.api_base: kwargs['api_base'] = self.api_base
            
            response = litellm.completion(
                model=self.model,
                messages=[{"role": "user", "content": "Hello"}],
                api_key=self.api_key,
                max_tokens=20,
                **kwargs
            )
            return {"success": True, "message": response.choices[0].message.content}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def gather_context(self, package_id: str, serial: str) -> str:
        """
        Gathers static analysis context (decompiled code / headers) for the AI.
        """
        # TODO: Integrate Jadx output directly?
        # For now, we return basic info
        return f"Package: {package_id}\nDevice Serial: {serial}\n"

    def _detect_best_role(self, prompt: str) -> tuple:
        """
        Heuristic to auto-select the best advanced role based on prompt keywords.
        Returns (category, sub_role) or (None, None).
        """
        p = prompt.lower()
        
        # Security Bypass
        if "root" in p and ("bypass" in p or "hide" in p or "detection" in p):
            return "security_bypass", "root_detection_bypass"
        if "ssl" in p or "cert" in p or "pinning" in p:
            return "security_bypass", "ssl_pinning_bypass"
        if "debug" in p and ("anti" in p or "bypass" in p):
            return "security_bypass", "anti_debug_bypass"
        if "bio" in p or "fingerprint" in p or "face" in p:
            return "security_bypass", "biometric_bypass"
            
        # Analysis
        if "vuln" in p or "weakness" in p:
            return "security_analysis", "vulnerability_analysis"
        if "decrypt" in p or "encrypt" in p or "cipher" in p:
            return "decryption_analysis", "decryption"
            
        # Tools
        if "frida" in p and "trace" in p:
            return "tools", "frida_analysis"
            
        return None, None

    def generate_script(self, prompt: str, package_context: str, role_category: str = None, sub_role: str = None) -> str:
        """
        Generates a Frida script with optimized token usage.
        """
        # Base System Prompt (Compressed)
        system_intro = "You are an expert Android security researcher using Frida."
        task_instruction = "Generate JavaScript code for Frida. NO explanations. NO markdown. JUST code."
        
        # Auto-Detect Role if not provided
        if not role_category or role_category == "auto":
             role_category, sub_role = self._detect_best_role(prompt)

        # Advanced Role Injection
        if role_category and sub_role and self.roles:
            try:
                template = self.roles.get(role_category, {}).get(sub_role, {}).get("Node", "")
                if template:
                    system_intro = f"Role: {role_category}/{sub_role}. {template}"
                    task_instruction += " Deep analysis required."
            except:
                pass

        system_prompt = f"{system_intro} {task_instruction}"
        
        # Context Optimization (Truncate if too large)
        # 1 char approx 1 byte, 4 chars approx 1 token. 
        # Limit context to ~2000 tokens (~8000 chars) to leave room for generation
        if len(package_context) > 8000:
            package_context = package_context[:8000] + "...(truncated)"

        user_msg = f"CTX:{package_context}\nREQ:{prompt}"
        
        try:
            kwargs = {}
            if self.api_base: kwargs['api_base'] = self.api_base
            
            # PERFORMANCE PRESET:
            # temperature=0.2 (Precise code, less hallucination)
            # max_tokens=2500 (Prevent infinite loops)
            # stop=["```"] (Stop if it tries to close block, usually means done)
            
            response = litellm.completion(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_msg}
                ],
                api_key=self.api_key,
                temperature=0.2, 
                max_tokens=4096,
                **kwargs
            )
            
            content = response.choices[0].message.content
            
            # Smart Cleanup
            if "```javascript" in content:
                content = content.split("```javascript")[1].split("```")[0]
            elif "```" in content:
                content = content.split("```")[1].split("```")[0]
                
            return content.strip()
        except Exception as e:
            logger.error(f"AI Generation Failed: {e}")
            return f"// Error: {e}"
