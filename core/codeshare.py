import requests
import os
import logging
from rich.console import Console
from typing import Optional

logger = logging.getLogger("ag-frida.core.codeshare")
console = Console()

class CodeShare:
    """
    Integrates with Frida CodeShare (https://codeshare.frida.re).
    Fetches raw script content.
    """
    
    BASE_URL = "https://codeshare.frida.re"
    CACHE_DIR = os.path.expanduser("~/.ag-frida/codeshare_cache")
    
    RECOMMENDED_SCRIPTS = [
        {
            "name": "Universal SSL Pinning Bypass",
            "slug": "pcipolloni/universal-android-ssl-pinning-bypass-with-frida",
            "description": "The most popular script for bypassing SSL Pinning on Android.",
            "category": "Network"
        },
        {
            "name": "Frida AntiRoot",
            "slug": "dzonerzy/fridantiroot",
            "description": "Bypass common root detection methods.",
            "category": "Security"
        },
        {
            "name": "Frida Multiple Unpinning",
            "slug": "akabe1/frida-multiple-unpinning",
            "description": "Aggressive unpinning for multiple libraries (OkHttp, TrustManager, etc).",
            "category": "Network"
        },
        {
            "name": "OkHttp3 Interceptor",
            "slug": "siefke/okhttp3-interceptor",
            "description": "Log and intercept OkHttp3 requests/responses.",
            "category": "Network"
        },
        {
            "name": "JNI Trace",
            "slug": "chame1eon/jnitrace",
            "description": "Trace JNI calls in Android apps (Heavy but powerful).",
            "category": "Analysis"
        },
        {
            "name": "Java Method Trace",
            "slug": "t0thkr1s/all-java-methods-tracer",
            "description": "Trace all Java methods in a specific class or package.",
            "category": "Analysis"
        },
        {
            "name": "AES Sniffer",
            "slug": "hluwa/frida-dexdump",
            "description": "While dexdump is for unpacking, often used with crypto sniffers. (Actually lets use a better crypto one)",
            "category": "Crypto"
        },
        {
            "name": "Crypto & Hash Sniffer",
            "slug": "monosomi/decrypt-kotlin",
            "description": "Intercepts crypto operations in Kotlin/Java apps.",
            "category": "Crypto"
        }
    ]

    ALIASES = {
        "bypass-ssl": "pcipolloni/universal-android-ssl-pinning-bypass-with-frida",
        "anti-root": "dzonerzy/fridantiroot",
        "multiple-unpinning": "akabe1/frida-multiple-unpinning"
    }

    def __init__(self):
        if not os.path.exists(self.CACHE_DIR):
            os.makedirs(self.CACHE_DIR)

    def fetch(self, project_slug: str) -> Optional[str]:
        """
        Fetches script from CodeShare. Supports aliases (e.g. 'bypass-ssl').
        """
        # Resolve Alias
        if project_slug in self.ALIASES:
            logger.info(f"Resolving alias '{project_slug}' -> '{self.ALIASES[project_slug]}'")
            project_slug = self.ALIASES[project_slug]
            
        # Clean slug (remove @ if present)
        # Standard format on website: @pcipolloni/universal-android-ssl-pinning
        # But CLI usually inputs: pcipolloni/universal-android-ssl-pinning
        
        # NOTE: CodeShare raw url structure: https://codeshare.frida.re/api/project/{slug}/source
        # slug often has slashes.
        
        cache_file = os.path.join(self.CACHE_DIR, project_slug.replace("/", "_") + ".js")
        
        # Check Cache first (optional, maybe we want fresh every time? Let's cache for speed)
        if os.path.exists(cache_file):
            logger.info(f"Using cached CodeShare script: {project_slug}")
            with open(cache_file, 'r', encoding='utf-8') as f:
                return f.read()

        logger.info(f"Fetching from CodeShare: {project_slug}...")
        try:
            url = f"{self.BASE_URL}/api/project/{project_slug}/source"
            r = requests.get(url, timeout=10)
            if r.status_code == 404:
                console.print(f"[red]CodeShare script not found: {project_slug}[/red]")
                return None
            r.raise_for_status()
            
            # API returns JSON with a "source" field
            data = r.json()
            if "source" not in data:
                logger.error(f"CodeShare response missing 'source' field for {project_slug}")
                return None
                
            content = data["source"]
            
            # Save to cache
            with open(cache_file, 'w', encoding='utf-8') as f:
                f.write(content)
            
            return content
            
        except Exception as e:
            logger.error(f"Failed to fetch from CodeShare: {e}")
            return None
